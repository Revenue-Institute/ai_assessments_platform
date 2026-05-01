"""Async scoring worker. Drains Redis-backed scoring jobs.

Run via:
    uv run python -m ri_assessments_api.worker

In docker-compose this is a sibling service to the api container that
shares the same image and env."""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Any

from .db import get_supabase
from .logging_config import install_pii_filter
from .services import queue as queue_service
from .services.scoring import score_assignment

log = logging.getLogger("ri_assessments_api.worker")


_should_stop = False


def _handle_signal(signum: int, _frame) -> None:
    global _should_stop
    log.info("worker received signal %s; draining and shutting down", signum)
    _should_stop = True


def _process(payload: dict[str, Any]) -> None:
    job_type = payload.get("type")
    if job_type != "score_assignment":
        log.warning("ignoring unknown job type %r", job_type)
        return
    assignment_id = payload.get("assignment_id")
    if not isinstance(assignment_id, str) or not assignment_id:
        log.warning("scoring job missing assignment_id: %r", payload)
        return

    started = time.monotonic()
    try:
        score_assignment(get_supabase(), assignment_id)
    except Exception as exc:
        log.exception("scoring job failed for %s", assignment_id)
        queue_service.push_dead_letter(payload, str(exc))
        return
    elapsed_ms = int((time.monotonic() - started) * 1000)
    log.info(
        "scored assignment %s in %s ms (queued at %s)",
        assignment_id,
        elapsed_ms,
        payload.get("enqueued_at"),
    )


def main() -> int:
    install_pii_filter()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if not queue_service.is_configured():
        log.error(
            "Redis is unavailable. Worker cannot start. Set UPSTASH_REDIS_URL "
            "(or run with docker-compose so the local redis service is "
            "reachable)."
        )
        return 2

    log.info("worker started; waiting for scoring jobs on %s", queue_service.SCORING_QUEUE)
    while not _should_stop:
        payload = queue_service.dequeue_blocking(timeout_seconds=5)
        if payload is None:
            continue
        _process(payload)
    log.info("worker exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
