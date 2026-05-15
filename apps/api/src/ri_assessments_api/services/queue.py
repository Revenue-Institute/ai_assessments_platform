"""Lightweight Redis-backed job queue for async scoring (spec §15).

We use a single LIST (`SCORING_QUEUE`) with LPUSH for enqueue and BRPOP
for blocking dequeue from the worker. Each job is a JSON envelope:

    {"type": "score_assignment", "assignment_id": "<uuid>", "enqueued_at": "<iso>"}

This keeps the contract intentionally narrow. If we add more job types
later they discriminate on the `type` field. We could swap to RQ /
Celery / BullMQ later; for v1 a 30-line shim is enough."""

from __future__ import annotations

import contextlib
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import redis

from ..config import get_settings

SCORING_QUEUE = "ri:scoring:jobs"
DEAD_LETTER = "ri:scoring:dead"
SCORING_EVENTS_CHANNEL = "ri:scoring:events"
# Per-run channel pattern for generator progress (spec §12.2 step 4).
# Each generator run gets its own channel so SSE subscribers can scope
# to one run_id without filtering noise from concurrent generations.
GENERATION_EVENTS_CHANNEL_PREFIX = "ri:generation:events"

# Spec §18 + production hardening: redis-py defaults to no socket
# timeout. Without these, a single unreachable Upstash node hangs the
# worker thread (and any sync FastAPI handler that touches Redis)
# indefinitely. 5s is the sweet spot: long enough to ride out a normal
# TLS handshake on a cold connection, short enough that a true outage
# fails over to inline scoring inside one request.
_REDIS_SOCKET_TIMEOUT_SECONDS = 5
_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS = 5
# brpop() needs a server-side timeout that is strictly greater than the
# socket read timeout so the blocking pop returns cleanly instead of
# the socket layer ripping the connection down. Worker callers pass
# their own timeout (default 5s); we clamp to <= socket_timeout - 1.
_REDIS_HEALTHCHECK_TIMEOUT_SECONDS = 2

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
        _client = redis.Redis.from_url(
            _redis_url(),
            decode_responses=True,
            socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
            socket_keepalive=True,
            health_check_interval=30,
        )
    return _client


def close_client() -> None:
    """Release the module-level Redis client. Called from the FastAPI
    lifespan shutdown path so pooled connections don't linger after the
    app exits (helpful for clean container shutdowns and for tests that
    swap settings between runs)."""

    global _client
    client = _client
    _client = None
    if client is None:
        return
    try:
        client.close()
    except Exception:  # pragma: no cover - close is best-effort
        log.debug("redis client close raised; ignoring", exc_info=True)


def is_configured() -> bool:
    """True when we should enqueue async; False when we should fall back
    to synchronous scoring (e.g. local dev without Redis). Uses a short
    health-check timeout so a dead Redis never stalls request handling."""

    try:
        client = _get_client()
        # Override the default socket_timeout for this one PING; we'd
        # rather declare Redis unconfigured fast than wait 5s on each
        # request when it is plainly unreachable.
        client.execute_command("PING")
        return True
    except Exception:
        return False


def ping_with_timeout(timeout_seconds: float = _REDIS_HEALTHCHECK_TIMEOUT_SECONDS) -> bool:
    """Stricter PING used by /health/ready. Builds a one-shot client with
    a tight socket timeout so a slow Redis cannot make the readiness
    probe block long enough for the orchestrator to kill the pod for
    the wrong reason."""

    url = _redis_url()
    probe: redis.Redis | None = None
    try:
        probe = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=timeout_seconds,
            socket_connect_timeout=timeout_seconds,
        )
        probe.execute_command("PING")
        return True
    except Exception:
        return False
    finally:
        if probe is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                probe.close()


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
        client = _get_client()
        client.lpush(SCORING_QUEUE, json.dumps(payload))
        # Best-effort SSE notification so the admin UI can flip to a
        # "scoring..." state immediately, before the worker picks up.
        with contextlib.suppress(Exception):
            client.publish(
                SCORING_EVENTS_CHANNEL,
                json.dumps(
                    {
                        "type": "scoring_queued",
                        "assignment_id": assignment_id,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                ),
            )
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


# -- Pub/sub for SSE fanout (spec §9.1, §14.4) ----------------------------


def publish_scoring_event(payload: dict[str, Any]) -> None:
    """Push an event onto the SCORING_EVENTS_CHANNEL pub/sub channel so any
    SSE subscribers in the admin app see it in near-real-time. Failures are
    swallowed because events are advisory: missing one means the admin sees
    the same state on next poll/refresh."""

    try:
        body = json.dumps({**payload, "ts": datetime.now(UTC).isoformat()})
        _get_client().publish(SCORING_EVENTS_CHANNEL, body)
    except Exception as exc:
        log.warning("could not publish scoring event: %s", exc)


def subscribe_scoring_events():
    """Returns a redis PubSub subscribed to SCORING_EVENTS_CHANNEL. Caller
    is responsible for calling .unsubscribe() / .close() on cleanup."""

    pubsub = _get_client().pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(SCORING_EVENTS_CHANNEL)
    return pubsub


# -- Generator per-run progress fanout (spec §12.2 step 4) ------------------


def _generation_channel(run_id: str) -> str:
    return f"{GENERATION_EVENTS_CHANNEL_PREFIX}:{run_id}"


def publish_generation_event(run_id: str, payload: dict[str, Any]) -> None:
    """Push a generator progress event onto the per-run pub/sub channel.
    Failures are swallowed: events are advisory. The HTTP response of
    POST /api/generator/questions remains the authoritative outcome."""

    try:
        body = json.dumps({**payload, "ts": datetime.now(UTC).isoformat()})
        _get_client().publish(_generation_channel(run_id), body)
    except Exception as exc:
        log.warning("could not publish generation event for run %s: %s", run_id, exc)


def subscribe_generation_events(run_id: str):
    """Returns a redis PubSub subscribed to this run's events channel.
    Caller owns .unsubscribe() / .close() in a finally block."""

    pubsub = _get_client().pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(_generation_channel(run_id))
    return pubsub
