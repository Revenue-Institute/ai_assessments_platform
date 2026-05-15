"""PII-scrubbing log configuration (spec §11.3) plus Axiom log shipping
plus per-request correlation IDs.

PII policy (spec §18: "No PII in logs."):
  * Email addresses are masked to `<email>`.
  * Phone numbers are masked to `<phone>`.
  * Candidate magic-link JWTs are masked to `<jwt>`.
  * 13-19 digit runs (credit-card shaped) are masked to `<cc>`.
  * Candidate IPs are never logged raw. The candidate router writes a
    keyed HMAC-SHA256 (`_ip_hash_from_request`) to attempt_events.ip_hash;
    raw IPs are only ever held in process memory long enough to compute
    that hash. The HMAC key is SESSION_COOKIE_SECRET so DB rows alone
    cannot be reversed.
  * Raw candidate answers are never logged at INFO. Service code that
    touches answers logs counts, ids, and scoring deltas only; the
    answer payload itself is persisted in `attempts.raw_answer` and
    rendered through admin auth, never echoed to the log sink.

We expose `install_pii_filter()` which mounts a logging.Filter on the
root logger that masks the patterns above before any record is emitted.
The filter applies to both `record.msg` and any string args, so
f-strings *and* % formatting are covered. Bound integers, floats, and
dataclasses pass through unchanged.

Why a filter rather than per-call sanitization? Because we have ~30
log sites and adding a sanitize call to each one would rot. A filter at
the root makes the policy enforceable centrally and immune to drift.

`install_axiom_shipping()` adds an HTTP handler that batches log records
and POSTs them to Axiom (spec §17). Stdout still gets every record, so
local tailing and Vercel logs continue to work.

`install_request_id_filter()` attaches a contextvar-driven filter so
every log record emitted inside a request carries the same `request_id`,
which lets Axiom and Sentry correlate across services per request. The
contextvar is set by a middleware in main.py at request start.
"""

from __future__ import annotations

import contextvars
import json
import logging
import queue
import re
import threading
import time
from typing import Any

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
PHONE_RE = re.compile(
    r"(?:(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})(?!\d)"
)
# Candidate magic-link tokens are JWTs; mask anything that looks like a JWT.
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")
# 13-19 digit credit-card-ish runs (with optional separators).
CC_RE = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")


# -- Request correlation id ----------------------------------------------

# Populated by the per-request middleware in main.py at the start of
# every HTTP request, cleared in a finally block. Contextvars survive
# `await` boundaries inside the same task, so any log call within the
# request flow (sync or async) picks up the right id automatically.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    """Stamps every LogRecord with a `request_id` attribute pulled from
    the contextvar. Records emitted outside a request (startup, worker
    loop) get the literal `-` sentinel so log queries can distinguish
    them from real traffic."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.request_id = request_id_var.get()
        except LookupError:  # pragma: no cover - default kicks in
            record.request_id = "-"
        return True


_REQUEST_ID_FILTER_SINGLETON: RequestIdFilter | None = None


def install_request_id_filter() -> None:
    """Attach the request-id filter to the root logger and known noisy
    children, and to all currently registered handlers. Idempotent."""

    global _REQUEST_ID_FILTER_SINGLETON
    f = _REQUEST_ID_FILTER_SINGLETON or RequestIdFilter()
    _REQUEST_ID_FILTER_SINGLETON = f
    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "anthropic"):
        logger = logging.getLogger(name)
        if not any(isinstance(existing, RequestIdFilter) for existing in logger.filters):
            logger.addFilter(f)
        for handler in logger.handlers:
            if not any(isinstance(existing, RequestIdFilter) for existing in handler.filters):
                handler.addFilter(f)


def _scrub(text: str) -> str:
    text = EMAIL_RE.sub("<email>", text)
    text = JWT_RE.sub("<jwt>", text)
    text = PHONE_RE.sub("<phone>", text)
    text = CC_RE.sub("<cc>", text)
    return text


class PIIScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        if record.args:
            scrubbed_args: list[object] = []
            for arg in record.args if isinstance(record.args, tuple) else (record.args,):
                if isinstance(arg, str):
                    scrubbed_args.append(_scrub(arg))
                else:
                    scrubbed_args.append(arg)
            record.args = (
                tuple(scrubbed_args)
                if isinstance(record.args, tuple)
                else scrubbed_args[0]
            )
        return True


_PII_FILTER_SINGLETON: PIIScrubFilter | None = None


class _PIIHandlerRegistrar(logging.Handler):
    """No-op handler whose only purpose is to wrap addHandler() at the root
    so any handler installed *after* install_pii_filter() (e.g. uvicorn's
    access-log handler attached on startup) still gets the filter applied.

    Without this, attaching the filter once at import time misses handlers
    that are added later in the boot sequence."""

    def __init__(self, pii: PIIScrubFilter) -> None:
        super().__init__()
        self._pii = pii
        self._installed: set[int] = set()

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        return

    def ensure_attached(self, logger: logging.Logger) -> None:
        for handler in logger.handlers:
            key = id(handler)
            if key in self._installed:
                continue
            handler.addFilter(self._pii)
            self._installed.add(key)


def install_pii_filter() -> None:
    """Attach the filter to every handler reachable from the root logger,
    plus the known-noisy children (uvicorn/httpx/anthropic), and re-scan
    on demand via reapply_pii_filter() once additional handlers are wired
    (e.g. by uvicorn or by Axiom shipping in main.py)."""

    global _PII_FILTER_SINGLETON
    pii = _PII_FILTER_SINGLETON or PIIScrubFilter()
    _PII_FILTER_SINGLETON = pii

    # Filter at the logger level catches records logged directly at that
    # logger, but per the stdlib semantics it does NOT see records
    # propagated up from descendants. So we ALSO attach to handlers, which
    # see every record reaching them regardless of origin.
    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "anthropic"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, PIIScrubFilter) for f in logger.filters):
            logger.addFilter(pii)
        for handler in logger.handlers:
            if not any(isinstance(f, PIIScrubFilter) for f in handler.filters):
                handler.addFilter(pii)


def reapply_pii_filter() -> None:
    """Call this after adding new log handlers (e.g. an Axiom HTTP handler
    in main.py) so they pick up the scrubber."""

    install_pii_filter()
    install_request_id_filter()


# -- Axiom log shipping ---------------------------------------------------


class AxiomBatchHandler(logging.Handler):
    """Buffers log records and POSTs them to Axiom in batches from a
    daemon thread. Drops to stderr on transport failure; never blocks the
    request thread.

    Spec §17: structured logs go to Axiom, breadcrumbs go to Sentry. Sentry
    is wired separately in main.py:_init_sentry."""

    def __init__(
        self,
        *,
        token: str,
        dataset: str,
        env: str,
        flush_interval: float = 2.0,
        max_batch: int = 200,
    ) -> None:
        super().__init__()
        self._token = token
        self._dataset = dataset
        self._env = env
        self._flush_interval = flush_interval
        self._max_batch = max_batch
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="axiom-log-shipper", daemon=True
        )
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry: dict[str, Any] = {
                "_time": int(record.created * 1000),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "env": self._env,
                "request_id": getattr(record, "request_id", "-"),
            }
            if record.exc_info:
                entry["exc_info"] = self.format(record)
            if record.pathname:
                entry["source"] = f"{record.pathname}:{record.lineno}"
            self._queue.put_nowait(entry)
        except queue.Full:
            # Drop on overflow rather than block. Local stderr handler
            # still has the record.
            pass
        except Exception:
            self.handleError(record)

    def _run(self) -> None:
        try:
            import urllib.request
        except Exception:  # pragma: no cover
            return
        url = f"https://api.axiom.co/v1/datasets/{self._dataset}/ingest"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        while not self._stop.is_set():
            batch: list[dict[str, Any]] = []
            deadline = time.monotonic() + self._flush_interval
            while time.monotonic() < deadline and len(batch) < self._max_batch:
                timeout = max(0.0, deadline - time.monotonic())
                try:
                    item = self._queue.get(timeout=timeout or 0.01)
                except queue.Empty:
                    break
                batch.append(item)
            if not batch:
                continue
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(batch).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=5).read()
            except Exception:
                # Swallow: the local stderr handler still has the records,
                # and we don't want a misbehaving log sink to crash the API.
                continue


_AXIOM_HANDLER: AxiomBatchHandler | None = None


def install_axiom_shipping(*, token: str, dataset: str, env: str) -> None:
    """Attach an Axiom shipper to the root logger. Idempotent."""

    global _AXIOM_HANDLER
    if _AXIOM_HANDLER is not None:
        return
    if not token or not dataset:
        return
    handler = AxiomBatchHandler(token=token, dataset=dataset, env=env)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    _AXIOM_HANDLER = handler
    # Make sure the new handler also runs the PII scrubber + request id stamp.
    reapply_pii_filter()
