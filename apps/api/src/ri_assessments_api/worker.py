"""Async scoring worker. Drains Redis-backed scoring jobs (spec §15).

Run via:
    uv run python -m ri_assessments_api.worker

In docker-compose this is a sibling service to the api container that
shares the same image and env.

Reliability contract:
- dequeue uses BLMOVE so an in-flight envelope sits on the processing
  list until the worker ACKs or NACKs it. A SIGKILL between dequeue and
  DB write no longer drops the job.
- failures call nack_job which either re-queues (attempts < MAX_ATTEMPTS)
  or pushes to the dead-letter list. The retry happens on a fresh
  envelope with a new enqueued_at, so the reaper does not double-reap.
- every loop iteration runs reap_stuck_jobs to recover entries whose
  enqueued_at is older than VISIBILITY_TIMEOUT_SECONDS. That covers the
  hard-crash case where the worker never gets to call nack."""

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

# Run the reaper at most this often. The reap scan is O(processing-list
# length), and on the steady state the list is empty, so 30s keeps the
# tail-latency on stuck-job recovery low without flooding Redis.
_REAP_INTERVAL_SECONDS = 30
_last_reap_at = 0.0


def _handle_signal(signum: int, _frame) -> None:
    global _should_stop
    log.info("worker received signal %s; draining and shutting down", signum)
    _should_stop = True


def _process(payload: dict[str, Any], raw_envelope: str) -> None:
    job_type = payload.get("type")
    if job_type != "score_assignment":
        log.warning("ignoring unknown job type %r", job_type)
        # Unknown types are not retryable; drop from processing without
        # going to DLQ so the operator does not have to drain noise.
        queue_service.ack_job(raw_envelope)
        return
    assignment_id = payload.get("assignment_id")
    if not isinstance(assignment_id, str) or not assignment_id:
        log.warning("scoring job missing assignment_id: %r", payload)
        queue_service.ack_job(raw_envelope)
        return

    started = time.monotonic()
    try:
        score_assignment(get_supabase(), assignment_id)
    except Exception as exc:
        log.exception("scoring job failed for %s", assignment_id)
        outcome = queue_service.nack_job(raw_envelope, payload, str(exc))
        queue_service.publish_scoring_event(
            {
                "type": "scoring_failed" if outcome == "dead_letter" else "scoring_retrying",
                "assignment_id": assignment_id,
                "error": str(exc),
                "attempts": int(payload.get("attempts") or 0) + 1,
            }
        )
        return

    elapsed_ms = int((time.monotonic() - started) * 1000)
    queue_service.ack_job(raw_envelope)
    queue_service.publish_scoring_event(
        {
            "type": "scoring_completed",
            "assignment_id": assignment_id,
            "elapsed_ms": elapsed_ms,
        }
    )
    log.info(
        "scored assignment %s in %s ms (queued at %s, attempt %s)",
        assignment_id,
        elapsed_ms,
        payload.get("enqueued_at"),
        int(payload.get("attempts") or 0) + 1,
    )


def _maybe_reap() -> None:
    global _last_reap_at
    now = time.monotonic()
    if now - _last_reap_at < _REAP_INTERVAL_SECONDS:
        return
    _last_reap_at = now
    try:
        queue_service.reap_stuck_jobs()
    except Exception:
        log.exception("reap_stuck_jobs raised; continuing")


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

    log.info(
        "worker started; waiting for scoring jobs on %s (processing=%s, dlq=%s)",
        queue_service.SCORING_QUEUE,
        queue_service.PROCESSING_QUEUE,
        queue_service.DEAD_LETTER,
    )
    # Reclaim anything left in PROCESSING_QUEUE from a previous run
    # before we start draining new jobs.
    queue_service.reap_stuck_jobs()

    while not _should_stop:
        _maybe_reap()
        result = queue_service.dequeue_blocking(timeout_seconds=5)
        if result is None:
            continue
        payload, raw_envelope = result
        _process(payload, raw_envelope)
    log.info("worker exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
