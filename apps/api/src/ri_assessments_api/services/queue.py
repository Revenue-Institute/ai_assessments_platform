"""Lightweight Redis-backed job queue for async scoring (spec §15).

We use a single LIST (`SCORING_QUEUE`) with LPUSH for enqueue and BRPOP
for blocking dequeue from the worker. Each job is a JSON envelope:

    {"type": "score_assignment", "assignment_id": "<uuid>", "enqueued_at": "<iso>"}

This keeps the contract intentionally narrow. If we add more job types
later they discriminate on the `type` field. We could swap to RQ /
Celery / BullMQ later; for v1 a 30-line shim is enough."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import redis

from ..config import get_settings

SCORING_QUEUE = "ri:scoring:jobs"
DEAD_LETTER = "ri:scoring:dead"

log = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _redis_url() -> str:
    settings = get_settings()
    raw = settings.upstash_redis_url or os.environ.get("REDIS_URL") or ""
    if not raw:
        # Default to the docker-compose redis service when nothing else
        # is configured. Local dev convenience.
        raw = "redis://redis:6379/0"
    if not raw.startswith(("redis://", "rediss://", "http://", "https://")):
        # Bare host:port, treat as redis://
        raw = f"redis://{raw}"
    if raw.startswith("http://"):
        raw = "redis://" + raw[len("http://") :]
    if raw.startswith("https://"):
        raw = "rediss://" + raw[len("https://") :]
    return raw


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(_redis_url(), decode_responses=True)
    return _client


def is_configured() -> bool:
    """True when we should enqueue async; False when we should fall back
    to synchronous scoring (e.g. local dev without Redis)."""

    try:
        _get_client().ping()
        return True
    except Exception:
        return False


def enqueue_score_assignment(assignment_id: str) -> bool:
    """Push a job onto the scoring queue. Returns True when enqueued,
    False when Redis is unavailable so the caller can fall back to
    inline scoring."""

    payload: dict[str, Any] = {
        "type": "score_assignment",
        "assignment_id": assignment_id,
        "enqueued_at": datetime.now(UTC).isoformat(),
    }
    try:
        _get_client().lpush(SCORING_QUEUE, json.dumps(payload))
        log.info("enqueued scoring job for assignment %s", assignment_id)
        return True
    except Exception as exc:
        log.warning(
            "failed to enqueue scoring job for assignment %s: %s",
            assignment_id,
            exc,
        )
        return False


def dequeue_blocking(timeout_seconds: int = 5) -> dict[str, Any] | None:
    """Worker side: BRPOP one job with a server-side timeout. Returns
    None when the timeout elapses with no job, so the worker can run
    its housekeeping loop."""

    client = _get_client()
    result = client.brpop([SCORING_QUEUE], timeout=timeout_seconds)
    if result is None:
        return None
    _, raw = result
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.exception("dropping malformed scoring job: %r", raw)
        return None


def push_dead_letter(payload: dict[str, Any], error: str) -> None:
    """Park a failed job so an operator can replay it later."""

    record = {**payload, "error": error, "failed_at": datetime.now(UTC).isoformat()}
    try:
        _get_client().lpush(DEAD_LETTER, json.dumps(record))
    except Exception:
        log.exception("could not write dead-letter record")
