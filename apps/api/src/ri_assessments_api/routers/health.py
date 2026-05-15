"""Liveness + readiness probes (spec §18 non-functional).

Three endpoints with intentionally different semantics:

  GET /health         Liveness. Returns 200 always. Orchestrator uses
                      this to decide whether to restart the pod. It
                      MUST NOT depend on any external service; if
                      Postgres or Redis is down we don't want our pod
                      culled, we want our pod to stay up and surface
                      503 on /health/ready until the dependency recovers.

  GET /health/live    Alias for /health. Matches the convention used by
                      Kubernetes manifests / many infra templates.

  GET /health/ready   Readiness. Probes the dependencies the API needs
                      to serve traffic: Supabase Postgres, Redis (if
                      configured), E2B (if configured). Returns 503 with
                      a per-check breakdown when any required dep fails.
                      Anthropic is intentionally NOT probed: a synthetic
                      generation call would burn quota on every probe.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Literal

from fastapi import APIRouter, Response, status

from .. import __version__
from ..config import get_settings
from ..services import queue as scoring_queue

router = APIRouter(tags=["health"])

log = logging.getLogger(__name__)

CheckStatus = Literal["ok", "fail", "skipped"]


def _check_supabase() -> CheckStatus:
    """SELECT 1 against the Postgres backing Supabase. We use the
    service-role REST endpoint via the shared client because that is
    exactly the channel admin endpoints use; a direct psycopg ping
    might succeed while RLS-routed reads fail."""

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return "skipped"
    try:
        from ..db import get_supabase

        client = get_supabase()
        # `competencies` is seeded at migration time; LIMIT 1 is cheap.
        # Any 2xx response (including empty rows) counts as healthy.
        client.table("competencies").select("id").limit(1).execute()
        return "ok"
    except Exception as exc:
        log.warning("readiness: supabase check failed: %s", exc)
        return "fail"


def _check_redis() -> CheckStatus:
    settings = get_settings()
    if not settings.upstash_redis_url:
        return "skipped"
    try:
        return "ok" if scoring_queue.ping_with_timeout(timeout_seconds=2.0) else "fail"
    except Exception as exc:
        log.warning("readiness: redis check failed: %s", exc)
        return "fail"


def _check_e2b() -> CheckStatus:
    """E2B reachability check. We avoid the SDK's heavier list / spawn
    paths and just confirm the API answers with a short HTTP timeout.
    No sandbox is provisioned. Skipped entirely when no key is set."""

    settings = get_settings()
    if not settings.e2b_api_key:
        return "skipped"
    try:
        import httpx

        # E2B's public API root is api.e2b.dev; an unauthenticated GET
        # returns a small JSON payload quickly. We attach the API key
        # so the response also confirms credentials are accepted.
        resp = httpx.get(
            "https://api.e2b.dev/sandboxes",
            headers={"X-API-Key": settings.e2b_api_key},
            timeout=2.0,
        )
        # 200/401/403 all prove reachability. 5xx is the only true fail.
        if resp.status_code >= 500:
            log.warning(
                "readiness: e2b returned %s on health probe", resp.status_code
            )
            return "fail"
        return "ok"
    except Exception as exc:
        log.warning("readiness: e2b check failed: %s", exc)
        return "fail"


def _run_with_timeout(fn, timeout_s: float, default: CheckStatus = "fail") -> CheckStatus:
    """Run a synchronous check in a worker thread with a hard wall-clock
    cap. Without this, a hung TCP connect would let one check pin the
    probe past whatever timeout the orchestrator uses, which causes the
    pod to be marked unready for the wrong reason."""

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeout:
            log.warning("readiness: check %s exceeded %ss budget", fn.__name__, timeout_s)
            return default
        except Exception as exc:
            log.warning("readiness: check %s raised: %s", fn.__name__, exc)
            return default


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns 200 unconditionally. Includes `status`
    and `version` keys so existing health monitors keep parsing the
    response unchanged."""

    return {"status": "ok", "version": __version__}


@router.get("/health/live")
def health_live() -> dict[str, str]:
    """Alias for /health to match the live/ready Kubernetes convention."""

    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
def health_ready(response: Response) -> dict[str, object]:
    """Readiness probe. Each external dependency reports `ok`,
    `skipped`, or `fail`. The aggregate returns 503 when any non-skipped
    check fails so the orchestrator can take the pod out of rotation
    without killing it."""

    checks: dict[str, CheckStatus] = {
        "supabase": _run_with_timeout(_check_supabase, timeout_s=3.0),
        "redis": _run_with_timeout(_check_redis, timeout_s=3.0),
        "e2b": _run_with_timeout(_check_e2b, timeout_s=3.0),
    }
    ok = all(value != "fail" for value in checks.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ok": ok, "version": __version__, "checks": checks}
