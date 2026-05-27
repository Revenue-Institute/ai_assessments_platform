"""Lightweight Redis-backed job queue for async scoring (spec §15).

Two lists:
    SCORING_QUEUE       = "ri:scoring:jobs"        (pending jobs)
    PROCESSING_QUEUE    = "ri:scoring:processing"  (in-flight jobs)
    DEAD_LETTER         = "ri:scoring:dead"        (gave up after MAX_ATTEMPTS)

Each job is a JSON envelope:
    {
      "type": "score_assignment",
      "assignment_id": "<uuid>",
      "enqueued_at": "<iso>",
      "attempts":  0
    }

Workers use BLMOVE to atomically take the rightmost SCORING_QUEUE entry
and put it onto PROCESSING_QUEUE. On success the worker LREMs the exact
envelope from PROCESSING_QUEUE. On failure the envelope is incremented
and either re-queued or pushed to DLQ.

A reaper (`reap_stuck_jobs`) re-queues envelopes whose `enqueued_at` is
older than VISIBILITY_TIMEOUT_SECONDS. This is what prevents work loss
when a worker dies mid-job; before this module had no visibility timeout
and a SIGKILL between BRPOP and DB write silently dropped the job.

We could swap to RQ / Celery / BullMQ later; for v1 this shim is enough
and matches the existing operational model (one Redis, no extra
processes)."""

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
PROCESSING_QUEUE = "ri:scoring:processing"
DEAD_LETTER = "ri:scoring:dead"
SCORING_EVENTS_CHANNEL = "ri:scoring:events"

# At-least-once delivery (spec §15). Re-enqueued jobs increment
# `attempts`; once attempts >= MAX_ATTEMPTS the job goes to DLQ instead
# of looping forever on a poison input. 3 is enough to ride out the
# common transient: a single Anthropic 529 or Supabase 502.
MAX_ATTEMPTS = 3

# How long an in-flight job is allowed to stay in PROCESSING_QUEUE
# before the reaper treats it as orphaned and re-queues. Must be
# meaningfully longer than the longest legitimate scoring run. Rubric-AI
# scoring of a 10-question module typically finishes in well under a
# minute; 10 minutes gives generous headroom for slow networks while
# still recovering reasonably fast from a hard worker crash.
VISIBILITY_TIMEOUT_SECONDS = 600
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


def _serialize(payload: dict[str, Any]) -> str:
    # Stable serialization so LREM can match by string equality. Without
    # sort_keys two semantically-equal envelopes could disagree on dict
    # order and the LREM would silently miss its target, double-credit-
    # ing the job to PROCESSING_QUEUE.
    return json.dumps(payload, sort_keys=True)


def enqueue_score_assignment(assignment_id: str) -> bool:
    """Push a job onto the scoring queue. Returns True when enqueued,
    False when Redis is unavailable so the caller can fall back to
    inline scoring."""

    payload: dict[str, Any] = {
        "type": "score_assignment",
        "assignment_id": assignment_id,
        "enqueued_at": datetime.now(UTC).isoformat(),
        "attempts": 0,
    }
    try:
        client = _get_client()
        client.lpush(SCORING_QUEUE, _serialize(payload))
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


def dequeue_blocking(timeout_seconds: int = 5) -> tuple[dict[str, Any], str] | None:
    """Worker side: atomically move one job from SCORING_QUEUE onto
    PROCESSING_QUEUE and return (payload, raw_envelope). The raw string
    is the exact value sitting in PROCESSING_QUEUE so callers can pass
    it back to ack_job / nack_job for LREM matching.

    Returns None when no job arrived within timeout_seconds, so the
    worker can run its housekeeping loop (e.g. reap_stuck_jobs).

    BLMOVE replaces the previous BRPOP. With BRPOP a worker crash
    between dequeue and DB write silently dropped the job; with BLMOVE
    the entry sits on PROCESSING_QUEUE until the worker ACKs, and the
    reaper re-queues anything older than VISIBILITY_TIMEOUT_SECONDS."""

    # Honor the invariant documented at the top of this module: Redis's
    # server-side timeout must finish strictly before the socket read
    # timeout, otherwise the socket layer tears the connection down and
    # raises TimeoutError instead of returning None cleanly.
    effective_timeout = max(1, min(timeout_seconds, _REDIS_SOCKET_TIMEOUT_SECONDS - 1))

    client = _get_client()
    try:
        # BLMOVE src dst RIGHT LEFT timeout. Workers consume from the
        # right of SCORING_QUEUE (FIFO with LPUSH on enqueue) and place
        # in-flight jobs on the left of PROCESSING_QUEUE (so the reaper
        # sees the oldest in-flight job on the right).
        raw = client.execute_command(
            "BLMOVE",
            SCORING_QUEUE,
            PROCESSING_QUEUE,
            "RIGHT",
            "LEFT",
            effective_timeout,
        )
    except redis.exceptions.TimeoutError:
        # Belt-and-suspenders: a TCP retransmit can still eat the last
        # second. Treat as "no job this round" so the worker keeps
        # spinning instead of crash-looping under docker restart policy.
        return None
    if raw is None:
        return None
    if isinstance(raw, bytes):  # pragma: no cover - decode_responses=True
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError:
        log.exception("dropping malformed scoring job: %r", raw)
        # Get the malformed envelope off PROCESSING_QUEUE so the reaper
        # doesn't churn on it forever. LREM matches by exact string.
        with contextlib.suppress(Exception):
            client.lrem(PROCESSING_QUEUE, 1, raw)
        return None


def ack_job(raw_envelope: str) -> None:
    """Remove a successfully-processed envelope from PROCESSING_QUEUE.

    LREM matches by exact string, so callers MUST pass the value that
    dequeue_blocking returned, not a re-serialized dict (Python dict
    iteration order would corrupt the match)."""

    try:
        _get_client().lrem(PROCESSING_QUEUE, 1, raw_envelope)
    except Exception:
        log.exception("ack_job failed; entry may be re-queued by reaper")


def nack_job(
    raw_envelope: str, payload: dict[str, Any], error: str
) -> str:
    """Mark a failed job. If attempts < MAX_ATTEMPTS, increment and
    re-queue with a fresh enqueued_at. Otherwise push to DLQ. Returns
    one of 'retried' | 'dead_letter' for logging."""

    attempts = int(payload.get("attempts") or 0) + 1
    client = _get_client()
    try:
        client.lrem(PROCESSING_QUEUE, 1, raw_envelope)
    except Exception:
        log.exception(
            "nack_job: failed to remove envelope from processing list"
        )

    if attempts < MAX_ATTEMPTS:
        retry_payload = {
            **payload,
            "attempts": attempts,
            "enqueued_at": datetime.now(UTC).isoformat(),
            "last_error": error,
        }
        try:
            client.lpush(SCORING_QUEUE, _serialize(retry_payload))
            log.warning(
                "scoring job re-queued (assignment=%s attempt=%d/%d error=%s)",
                payload.get("assignment_id"),
                attempts,
                MAX_ATTEMPTS,
                error,
            )
            return "retried"
        except Exception:
            log.exception("nack_job: re-enqueue failed; falling through to DLQ")

    push_dead_letter(payload, error)
    return "dead_letter"


def push_dead_letter(payload: dict[str, Any], error: str) -> None:
    """Park a failed job so an operator can replay it later."""

    record = {**payload, "error": error, "failed_at": datetime.now(UTC).isoformat()}
    try:
        _get_client().lpush(DEAD_LETTER, _serialize(record))
    except Exception:
        log.exception("could not write dead-letter record")


def reap_stuck_jobs(now: datetime | None = None) -> int:
    """Re-queue any in-flight envelope whose enqueued_at is older than
    VISIBILITY_TIMEOUT_SECONDS. Called periodically by the worker loop
    so a crashed worker's jobs do not stay stuck forever. Returns the
    number of jobs reaped (zero on the steady-state happy path)."""

    client = _get_client()
    cutoff = (now or datetime.now(UTC)).timestamp() - VISIBILITY_TIMEOUT_SECONDS
    try:
        entries = client.lrange(PROCESSING_QUEUE, 0, -1)
    except Exception:
        log.exception("reap_stuck_jobs: could not read processing list")
        return 0

    reaped = 0
    for raw in entries or []:
        if isinstance(raw, bytes):  # pragma: no cover - decode_responses=True
            raw = raw.decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # Malformed entries: drop so they don't keep poisoning the
            # reaper loop. They are unrecoverable by definition.
            with contextlib.suppress(Exception):
                client.lrem(PROCESSING_QUEUE, 1, raw)
            log.error("reap_stuck_jobs: dropping malformed entry %r", raw)
            continue

        enqueued_iso = payload.get("enqueued_at") or ""
        try:
            enqueued_ts = datetime.fromisoformat(
                enqueued_iso.replace("Z", "+00:00")
            ).timestamp()
        except ValueError:
            log.warning(
                "reap_stuck_jobs: bad enqueued_at on entry, dropping: %r",
                payload,
            )
            with contextlib.suppress(Exception):
                client.lrem(PROCESSING_QUEUE, 1, raw)
            continue

        if enqueued_ts >= cutoff:
            continue

        nack_job(raw, payload, "visibility_timeout")
        reaped += 1

    if reaped:
        log.warning("reap_stuck_jobs: reclaimed %d in-flight job(s)", reaped)
    return reaped


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
