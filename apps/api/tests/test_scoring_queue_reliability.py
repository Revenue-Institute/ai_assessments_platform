"""Tests for the BLMOVE + retry + reaper queue contract.

Spec §15 + remediation memo 2026-05-26: a worker crash between dequeue
and DB write must not silently drop a scoring job. The contract is:

  - dequeue_blocking returns (payload, raw_envelope) and the entry sits
    on PROCESSING_QUEUE until the worker ACKs.
  - ack_job removes the exact envelope from PROCESSING_QUEUE.
  - nack_job either re-queues with attempts+=1 and a fresh enqueued_at,
    or pushes to DLQ when attempts >= MAX_ATTEMPTS.
  - reap_stuck_jobs re-queues PROCESSING_QUEUE entries older than
    VISIBILITY_TIMEOUT_SECONDS.

We exercise the contract against a thin in-memory Redis fake. The real
Redis path is covered by the production deploy."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ri_assessments_api.services import queue as q


class _FakeRedis:
    """In-memory implementation of just enough of the redis-py surface
    the queue module uses. Lists, LPUSH/LREM/LRANGE, BLMOVE, PING."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    def execute_command(self, *args: Any) -> Any:
        if args[0] == "PING":
            return "PONG"
        if args[0] == "BLMOVE":
            _, src, dst, src_dir, dst_dir, _timeout = args
            src_list = self.lists.get(src) or []
            if not src_list:
                return None
            value = src_list.pop() if src_dir == "RIGHT" else src_list.pop(0)
            target = self.lists.setdefault(dst, [])
            if dst_dir == "LEFT":
                target.insert(0, value)
            else:
                target.append(value)
            return value
        raise NotImplementedError(args)

    def lpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    def lrem(self, key: str, count: int, value: str) -> int:
        bucket = self.lists.get(key) or []
        if value in bucket:
            bucket.remove(value)
            return 1
        return 0

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        bucket = self.lists.get(key) or []
        if end == -1:
            return list(bucket)
        return bucket[start : end + 1]

    def publish(self, *_args: Any, **_kwargs: Any) -> int:
        return 0

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Swap the module-level Redis client for an in-memory fake."""

    fake = _FakeRedis()
    monkeypatch.setattr(q, "_client", fake, raising=False)
    yield fake
    # Restore so test isolation is robust against parallel suites.
    monkeypatch.setattr(q, "_client", None, raising=False)


def test_enqueue_then_dequeue_round_trip(fake_redis):
    assert q.enqueue_score_assignment("a-1") is True

    result = q.dequeue_blocking(timeout_seconds=1)
    assert result is not None
    payload, raw = result
    assert payload["type"] == "score_assignment"
    assert payload["assignment_id"] == "a-1"
    assert payload["attempts"] == 0
    # PROCESSING_QUEUE now holds the in-flight envelope.
    assert raw in fake_redis.lists.get(q.PROCESSING_QUEUE, [])


def test_ack_job_clears_processing(fake_redis):
    q.enqueue_score_assignment("a-1")
    payload, raw = q.dequeue_blocking(timeout_seconds=1)
    q.ack_job(raw)
    assert fake_redis.lists.get(q.PROCESSING_QUEUE, []) == []


def test_nack_requeues_until_max_attempts(fake_redis):
    q.enqueue_score_assignment("a-1")

    # First failure: re-queued with attempts=1.
    _, raw1 = q.dequeue_blocking(timeout_seconds=1)
    outcome = q.nack_job(raw1, json.loads(raw1), "anthropic 529")
    assert outcome == "retried"
    assert fake_redis.lists.get(q.PROCESSING_QUEUE, []) == []
    assert fake_redis.lists.get(q.SCORING_QUEUE)

    # Second failure: re-queued with attempts=2.
    _, raw2 = q.dequeue_blocking(timeout_seconds=1)
    payload2 = json.loads(raw2)
    assert payload2["attempts"] == 1
    outcome = q.nack_job(raw2, payload2, "anthropic 529 again")
    assert outcome == "retried"

    # Third failure: attempts hits MAX_ATTEMPTS, goes to DLQ.
    _, raw3 = q.dequeue_blocking(timeout_seconds=1)
    payload3 = json.loads(raw3)
    assert payload3["attempts"] == 2
    outcome = q.nack_job(raw3, payload3, "anthropic 529 last time")
    assert outcome == "dead_letter"
    assert fake_redis.lists.get(q.SCORING_QUEUE, []) == []
    dlq = fake_redis.lists.get(q.DEAD_LETTER, [])
    assert dlq, "expected DLQ entry"
    parked = json.loads(dlq[0])
    assert parked["assignment_id"] == "a-1"
    assert parked["error"] == "anthropic 529 last time"


def test_reap_recovers_stuck_jobs(fake_redis):
    """Worker crash: the envelope sits on PROCESSING_QUEUE past the
    visibility timeout. reap_stuck_jobs re-queues it."""

    # Manually insert a stuck envelope with an old enqueued_at.
    old = (
        datetime.now(UTC)
        - timedelta(seconds=q.VISIBILITY_TIMEOUT_SECONDS + 30)
    ).isoformat()
    payload = {
        "type": "score_assignment",
        "assignment_id": "stuck-1",
        "enqueued_at": old,
        "attempts": 0,
    }
    raw = q._serialize(payload)
    fake_redis.lists.setdefault(q.PROCESSING_QUEUE, []).insert(0, raw)

    reaped = q.reap_stuck_jobs()
    assert reaped == 1
    assert fake_redis.lists.get(q.PROCESSING_QUEUE, []) == []
    requeued = fake_redis.lists.get(q.SCORING_QUEUE) or []
    assert requeued, "expected stuck job re-queued"
    new_payload = json.loads(requeued[0])
    assert new_payload["assignment_id"] == "stuck-1"
    assert new_payload["attempts"] == 1
    assert new_payload["last_error"] == "visibility_timeout"


def test_reap_ignores_fresh_jobs(fake_redis):
    """A freshly-dequeued job (within VISIBILITY_TIMEOUT_SECONDS) must
    NOT be touched by the reaper, even if the worker is mid-execution."""

    q.enqueue_score_assignment("a-fresh")
    _, raw = q.dequeue_blocking(timeout_seconds=1)
    reaped = q.reap_stuck_jobs()
    assert reaped == 0
    # The fresh envelope is still on PROCESSING_QUEUE.
    assert raw in fake_redis.lists.get(q.PROCESSING_QUEUE, [])


def test_serialize_is_stable_for_lrem(fake_redis):
    """LREM matches by exact string. _serialize must produce the same
    bytes regardless of dict insertion order."""

    a = q._serialize({"a": 1, "b": 2, "c": 3})
    b = q._serialize({"c": 3, "a": 1, "b": 2})
    assert a == b


def test_dequeue_drops_malformed_envelope(fake_redis):
    """A non-JSON entry on the queue must not crash the worker; it
    should be dropped from PROCESSING_QUEUE so the reaper does not
    churn on it forever."""

    fake_redis.lists.setdefault(q.SCORING_QUEUE, []).insert(0, "not-json-{")
    result = q.dequeue_blocking(timeout_seconds=1)
    assert result is None
    assert fake_redis.lists.get(q.PROCESSING_QUEUE, []) == []
