"""Shared fixtures for new-feature regression tests.

`MockSupabase` is a fluent in-memory stand-in for `supabase.Client`. It
mirrors the small slice of the SDK actually used by services / routers
(table().select().eq().limit().execute() and the corresponding
insert/update/delete chains) so the unit tests can drive the real code
paths without touching the network.

Tests register canned responses by `("table", "operation")` key, e.g.
`mock.add(("assignments", "select"), [row, ...])`. Calls fall through to
the registered list in FIFO order; if nothing is queued, the mock returns
an empty result (`data=[]`) which matches the real SDK's contract for an
empty query result.

Updates and inserts also record the payload on `mock.captured` so tests
can assert that the service issued the right write."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Result:
    data: list[dict[str, Any]] | None = None


class _Query:
    """One fluent builder per `table().<op>()` chain. The chain is replayed
    against the parent mock when `.execute()` is called."""

    def __init__(self, parent: "MockSupabase", table: str, operation: str,
                 payload: Any | None = None):
        self._parent = parent
        self._table = table
        self._operation = operation
        self._payload = payload
        # Filters & modifiers are recorded but unused for routing; the
        # MockSupabase router keys on (table, operation), which is enough
        # for the tests we ship. If a future test needs filter-aware
        # routing, extend `__call_key`.
        self._filters: list[tuple[str, Any]] = []
        self._modifiers: list[tuple[str, Any]] = []

    # -- chainable filters / modifiers --
    def select(self, *_args: Any, **_kwargs: Any) -> "_Query":
        return self

    def eq(self, key: str, value: Any) -> "_Query":
        self._filters.append(("eq", (key, value)))
        return self

    def neq(self, key: str, value: Any) -> "_Query":
        self._filters.append(("neq", (key, value)))
        return self

    def in_(self, key: str, value: Any) -> "_Query":
        self._filters.append(("in", (key, value)))
        return self

    def filter(self, key: str, op: str, value: Any) -> "_Query":
        self._filters.append((op, (key, value)))
        return self

    def order(self, key: str, *, desc: bool = False) -> "_Query":
        self._modifiers.append(("order", (key, desc)))
        return self

    def limit(self, n: int) -> "_Query":
        self._modifiers.append(("limit", n))
        return self

    # -- terminal --
    def execute(self) -> _Result:
        return self._parent._dispatch(
            table=self._table,
            operation=self._operation,
            payload=self._payload,
            filters=self._filters,
            modifiers=self._modifiers,
        )


class _Table:
    def __init__(self, parent: "MockSupabase", name: str):
        self._parent = parent
        self._name = name

    def select(self, *_args: Any, **_kwargs: Any) -> _Query:
        return _Query(self._parent, self._name, "select")

    def insert(self, payload: Any) -> _Query:
        return _Query(self._parent, self._name, "insert", payload=payload)

    def update(self, payload: Any) -> _Query:
        return _Query(self._parent, self._name, "update", payload=payload)

    def delete(self) -> _Query:
        return _Query(self._parent, self._name, "delete")

    def upsert(self, payload: Any) -> _Query:
        return _Query(self._parent, self._name, "upsert", payload=payload)


@dataclass
class _Captured:
    table: str
    operation: str
    payload: Any
    filters: list[tuple[str, Any]] = field(default_factory=list)
    modifiers: list[tuple[str, Any]] = field(default_factory=list)


class MockSupabase:
    """Minimal in-memory stand-in for `supabase.Client`. Tests register
    canned response queues per (table, operation) and inspect
    `mock.captured` to verify writes.

    Example:

        mock = MockSupabase()
        mock.queue(("assignments", "select"), [{"id": "a-1", ...}])
        result = mock.table("assignments").select("*").eq("id", "a-1").execute()
        assert result.data[0]["id"] == "a-1"

        mock.table("attempts").update({"score": 9}).eq("id", "x").execute()
        assert mock.captured[-1].operation == "update"
        assert mock.captured[-1].payload == {"score": 9}
    """

    def __init__(self) -> None:
        self._queues: dict[tuple[str, str], list[list[dict[str, Any]] | None]] = {}
        self.captured: list[_Captured] = []
        # Optional per-call hook so tests can answer dynamically.
        self._handlers: dict[tuple[str, str], Any] = {}

    def table(self, name: str) -> _Table:
        return _Table(self, name)

    def queue(self, key: tuple[str, str],
              data: list[dict[str, Any]] | None) -> None:
        """Push a canned response onto the queue for `(table, operation)`.
        FIFO: the next matching call pops and returns this entry."""

        self._queues.setdefault(key, []).append(data)

    def queue_many(self, key: tuple[str, str],
                   entries: list[list[dict[str, Any]] | None]) -> None:
        for entry in entries:
            self.queue(key, entry)

    def handler(self, key: tuple[str, str], fn: Any) -> None:
        """Register a callable invoked for every call matching the key.
        Receives the `_Captured` record and returns `data` (list or None).
        Useful when the response must depend on the filter values."""

        self._handlers[key] = fn

    # -- internals --
    def _dispatch(
        self,
        *,
        table: str,
        operation: str,
        payload: Any,
        filters: list[tuple[str, Any]],
        modifiers: list[tuple[str, Any]],
    ) -> _Result:
        cap = _Captured(
            table=table,
            operation=operation,
            payload=payload,
            filters=list(filters),
            modifiers=list(modifiers),
        )
        self.captured.append(cap)
        key = (table, operation)
        handler = self._handlers.get(key)
        if handler is not None:
            data = handler(cap)
            return _Result(data=data)
        queue = self._queues.get(key)
        if queue:
            data = queue.pop(0)
            return _Result(data=data)
        # Inserts default to echoing back the inserted payload (Supabase
        # does this when no .select() is chained); updates default to an
        # empty list. None of the new tests rely on the auto-echo, but
        # admin.create_module checks `inserted.data` for truthiness.
        if operation == "insert":
            if isinstance(payload, list):
                return _Result(data=list(payload))
            if isinstance(payload, dict):
                return _Result(data=[payload])
            return _Result(data=[])
        return _Result(data=[])

    # Convenience accessors -----------------------------------------------
    def calls_for(self, table: str, operation: str) -> list[_Captured]:
        return [c for c in self.captured if c.table == table and c.operation == operation]
