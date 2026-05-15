"""Smoke test for slowapi rate-limit decorators on the candidate routes.

Spec §14.3 + §18 call out per-token rate limiting on the runner endpoints.
slowapi registers each decorated endpoint into the Limiter's
`_route_limits` map keyed on the qualified function path; the Limit
object's repr looks like `30 per 1 minute`. We inspect that map directly
rather than walking closures so the test is stable across decorator
versions.

Skipped gracefully if slowapi is not installed (the candidate module's
shim turns `_rate_limit` into a no-op then)."""

from __future__ import annotations

import importlib

import pytest


def _candidate_module():
    return importlib.import_module("ri_assessments_api.routers.candidate")


def _has_slowapi(module) -> bool:
    return getattr(module, "_RATE_LIMIT_ENABLED", False) and module._limiter is not None


def _limit_repr_for(module, qualname: str) -> str | None:
    limiter = module._limiter
    limits = limiter._route_limits.get(qualname) or []
    if not limits:
        return None
    return repr(limits[0].limit)


def test_code_run_route_has_30_per_minute_limit():
    module = _candidate_module()
    if not _has_slowapi(module):
        pytest.skip("slowapi not installed; decorator is a no-op shim")
    rendered = _limit_repr_for(
        module, "ri_assessments_api.routers.candidate.code_run"
    )
    assert rendered is not None, "code_run should be registered with slowapi"
    # Limit reprs as "30 per 1 minute" in slowapi 0.1.9+.
    assert "30 per 1 minute" == rendered


def test_heartbeat_route_has_60_per_minute_limit():
    module = _candidate_module()
    if not _has_slowapi(module):
        pytest.skip("slowapi not installed; decorator is a no-op shim")
    rendered = _limit_repr_for(
        module, "ri_assessments_api.routers.candidate.heartbeat"
    )
    assert rendered is not None
    assert "60 per 1 minute" == rendered


def test_events_route_has_30_per_minute_limit():
    module = _candidate_module()
    if not _has_slowapi(module):
        pytest.skip("slowapi not installed; decorator is a no-op shim")
    rendered = _limit_repr_for(
        module, "ri_assessments_api.routers.candidate.events"
    )
    assert rendered is not None
    assert "30 per 1 minute" == rendered


def test_n8n_embed_route_has_10_per_minute_limit():
    module = _candidate_module()
    if not _has_slowapi(module):
        pytest.skip("slowapi not installed; decorator is a no-op shim")
    rendered = _limit_repr_for(
        module, "ri_assessments_api.routers.candidate.n8n_embed"
    )
    assert rendered is not None
    assert "10 per 1 minute" == rendered
