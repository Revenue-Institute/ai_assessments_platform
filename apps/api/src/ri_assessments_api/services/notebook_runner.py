"""E2B Jupyter-kernel notebook runner (spec §7.3).

v1 scope: the candidate's notebook is a list of `{type: "code"|"markdown",
source: str}` cells. We provision a fresh E2B sandbox, optionally pull
dataset_urls into /data/, run each code cell through a stateful Python
kernel via Sandbox.run_code (state carries across calls), and capture
per-cell outputs. For grading we append the question's validation_script
in the same kernel and parse its JSON line, the spec format is
`{pass: bool, details: {...}}`.

Skipped for v1 (lands when we wire jupyter-lite or @nteract/core):
- per-cell run with persistent sandbox between requests
- rich output rendering (charts, HTML) in the candidate UI."""

from __future__ import annotations

import json
import logging
import shlex
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status

from .e2b_sandbox import get_sandbox as _sandbox_or_503

log = logging.getLogger(__name__)


@dataclass(slots=True)
class NotebookCellOutput:
    index: int
    type: str
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    runtime_ms: int = 0


@dataclass(slots=True)
class NotebookRunResult:
    cells: list[NotebookCellOutput] = field(default_factory=list)
    runtime_ms: int = 0
    timed_out: bool = False


@dataclass(slots=True)
class NotebookGradeResult:
    passed: bool
    details: dict[str, Any]
    output_log: str
    runtime_ms: int


def _safe_url(url: str) -> str:
    """Whitelist http/https URLs only, `wget` shells out, so anything else is
    a vector. Keeps it boring."""
    if not url.startswith(("https://", "http://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Refusing dataset URL with unsupported scheme: {url!r}",
        )
    return shlex.quote(url)


def _materialize_datasets(sandbox, dataset_urls: list[str]) -> None:
    if not dataset_urls:
        return
    sandbox.commands.run("mkdir -p /data", timeout=30)
    for url in dataset_urls:
        safe = _safe_url(url)
        # -nc skips re-download on a re-run within the same sandbox session.
        sandbox.commands.run(
            f"cd /data && wget --quiet --no-clobber {safe}",
            timeout=120,
        )


def _capture_run(sandbox, source: str, cell_timeout_s: int) -> NotebookCellOutput:
    started = time.monotonic()
    try:
        exec_result = sandbox.run_code(source, timeout=cell_timeout_s)
    except Exception as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        return NotebookCellOutput(
            index=-1,
            type="code",
            error=str(exc),
            runtime_ms=elapsed,
        )

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    logs = getattr(exec_result, "logs", None)
    if logs is not None:
        if getattr(logs, "stdout", None):
            stdout_parts.extend(logs.stdout)
        if getattr(logs, "stderr", None):
            stderr_parts.extend(logs.stderr)

    text_result = getattr(exec_result, "text", None)
    if isinstance(text_result, str) and text_result:
        stdout_parts.append(text_result)

    error_obj = getattr(exec_result, "error", None)
    error_str: str | None = None
    if error_obj is not None:
        name = getattr(error_obj, "name", "") or ""
        value = getattr(error_obj, "value", "") or ""
        error_str = f"{name}: {value}".strip(": ")

    return NotebookCellOutput(
        index=-1,
        type="code",
        stdout="\n".join(s.strip() for s in stdout_parts if s).strip(),
        stderr="\n".join(s.strip() for s in stderr_parts if s).strip(),
        error=error_str,
        runtime_ms=int((time.monotonic() - started) * 1000),
    )


def run_notebook(
    *,
    cells: list[dict[str, Any]],
    dataset_urls: list[str] | None = None,
    cell_timeout_ms: int = 30_000,
    overall_timeout_ms: int = 180_000,
) -> NotebookRunResult:
    sandbox_cls, api_key = _sandbox_or_503()
    cell_timeout_s = max(2, cell_timeout_ms // 1000)
    overall_timeout_s = max(cell_timeout_s + 30, overall_timeout_ms // 1000)
    started = time.monotonic()
    timed_out = False
    outputs: list[NotebookCellOutput] = []

    try:
        with sandbox_cls.create(api_key=api_key, timeout=overall_timeout_s) as sandbox:
            _materialize_datasets(sandbox, dataset_urls or [])
            for i, cell in enumerate(cells):
                ctype = (cell.get("type") or "code").lower()
                if ctype == "markdown":
                    outputs.append(NotebookCellOutput(index=i, type="markdown"))
                    continue
                source = cell.get("source") or ""
                if not source.strip():
                    outputs.append(NotebookCellOutput(index=i, type="code"))
                    continue
                row = _capture_run(sandbox, source, cell_timeout_s)
                row.index = i
                outputs.append(row)
                if row.error and row.error.lower().startswith("timeout"):
                    timed_out = True
                    break
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Notebook runner failure: {exc}",
        ) from exc

    return NotebookRunResult(
        cells=outputs,
        runtime_ms=int((time.monotonic() - started) * 1000),
        timed_out=timed_out,
    )


def grade_notebook_attempt(
    *,
    cells: list[dict[str, Any]],
    config: dict[str, Any],
    max_points: float,
    packages: list[str] | None = None,
) -> dict[str, Any]:
    """Provision a fresh kernel, run the candidate's cells, snapshot the
    resulting globals to a pickle file, then run the question's
    validation_script in a SECOND, fresh sandbox that loads that state.

    Security rationale (spec §7.3): the validation script encodes the
    answer key. Running it in the candidate's kernel means the candidate
    can monkey-patch globals (`def assert_(*a, **k): pass`,
    `result = {"pass": True}`) and trivially flip the verdict. Loading
    state into a fresh kernel and exec'ing the validation script there
    with the snapshot bound to a local namespace (`state`) prevents that
    tampering: validation reads candidate values but the validation
    script's own globals are untouched by candidate code.

    Caveat: only picklable values survive the snapshot. Modules,
    open file handles, and live connections drop. The validation script
    should look up data in `state[name]` rather than relying on imports
    persisting from the candidate kernel."""

    validation_script = config.get("validation_script") or ""
    if not validation_script.strip():
        return {
            "score": 0.0,
            "score_rationale": (
                "Notebook question has no validation_script; cannot grade."
            ),
            "scorer_model": "notebook-e2b",
            "scorer_version": "1",
        }

    dataset_urls = list(config.get("dataset_urls") or [])
    install_packages = list(packages or config.get("packages") or [])

    sandbox_cls, api_key = _sandbox_or_503()
    output_log_parts: list[str] = []
    passed = False
    details: dict[str, Any] = {}
    state_b64: str | None = None

    # Stage 1: candidate kernel. Run the candidate's cells, then dump
    # picklable globals to base64-encoded bytes we can ferry across the
    # sandbox boundary via stdout (avoids depending on the sandbox SDK's
    # file-transfer specifics).
    try:
        with sandbox_cls.create(api_key=api_key, timeout=240) as sandbox:
            if install_packages:
                joined = " ".join(shlex.quote(p) for p in install_packages)
                sandbox.commands.run(f"pip install --quiet {joined}", timeout=180)
            _materialize_datasets(sandbox, dataset_urls)
            for i, cell in enumerate(cells):
                if (cell.get("type") or "code").lower() != "code":
                    continue
                source = cell.get("source") or ""
                if not source.strip():
                    continue
                row = _capture_run(sandbox, source, 60)
                if row.stderr:
                    output_log_parts.append(f"[cell {i} stderr] {row.stderr}")
                if row.error:
                    output_log_parts.append(f"[cell {i} error] {row.error}")
                if row.stdout:
                    output_log_parts.append(f"[cell {i} stdout] {row.stdout}")

            # Snapshot globals. We pickle inside a try/except per key so a
            # single un-picklable value (e.g. a thread lock) doesn't lose
            # the whole state.
            snapshot_src = (
                "import pickle as _p, base64 as _b64, sys as _sys\n"
                "_RI_SNAPSHOT_SENTINEL = '__RI_STATE_PKL_B64__'\n"
                "_state = {}\n"
                "for _k, _v in list(globals().items()):\n"
                "    if _k.startswith('_'): continue\n"
                "    try:\n"
                "        _p.dumps(_v); _state[_k] = _v\n"
                "    except Exception:\n"
                "        pass\n"
                "_blob = _b64.b64encode(_p.dumps(_state)).decode('ascii')\n"
                "_sys.stdout.flush(); print(_RI_SNAPSHOT_SENTINEL + _blob)\n"
            )
            snap = _capture_run(sandbox, snapshot_src, 60)
            marker = "__RI_STATE_PKL_B64__"
            for line in (snap.stdout or "").splitlines():
                if marker in line:
                    state_b64 = line.split(marker, 1)[1].strip()
                    break
            if state_b64 is None and snap.stderr:
                output_log_parts.append(f"[snapshot stderr] {snap.stderr}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Notebook grading failure: {exc}",
        ) from exc

    if state_b64 is None:
        # Couldn't capture state. Surface as a graded failure rather than
        # a 502 so the attempt still records something.
        return {
            "score": 0.0,
            "score_rationale": "Validation skipped: could not snapshot kernel state.",
            "scorer_model": "notebook-e2b",
            "scorer_version": "1",
        }

    # Stage 2: validation kernel. Fresh sandbox so the candidate's code
    # has zero opportunity to tamper with the verdict. We rebuild the
    # state dict and exec the validation script with `state` injected as
    # a local; the script reads candidate values via `state[name]`.
    try:
        with sandbox_cls.create(api_key=api_key, timeout=240) as sandbox:
            if install_packages:
                joined = " ".join(shlex.quote(p) for p in install_packages)
                sandbox.commands.run(f"pip install --quiet {joined}", timeout=180)
            _materialize_datasets(sandbox, dataset_urls)

            # NOTE: we pass the validation_script verbatim inside a Python
            # string. To avoid quote-escape headaches we ship it via a file
            # using base64, same pattern as the state blob.
            import base64 as _b64

            script_b64 = _b64.b64encode(
                validation_script.encode("utf-8")
            ).decode("ascii")
            wrapped = (
                "import pickle as _p, base64 as _b64, json as _json, sys as _sys\n"
                f"_STATE_B64 = {state_b64!r}\n"
                f"_SCRIPT_B64 = {script_b64!r}\n"
                "_RI_SENTINEL = '__RI_VALIDATION_RESULT__'\n"
                "state = _p.loads(_b64.b64decode(_STATE_B64))\n"
                "_validation_src = _b64.b64decode(_SCRIPT_B64).decode('utf-8')\n"
                "_ns = {'state': state}\n"
                "exec(compile(_validation_src, '<validation>', 'exec'), _ns, _ns)\n"
                "_res = _ns.get('result')\n"
                "if isinstance(_res, dict):\n"
                "    _sys.stdout.flush(); print(_RI_SENTINEL + _json.dumps(_res, default=str))\n"
            )
            verdict = _capture_run(sandbox, wrapped, 90)
            output_log_parts.append("[validation]")
            if verdict.stdout:
                output_log_parts.append(verdict.stdout)
            if verdict.stderr:
                output_log_parts.append(f"[validation stderr] {verdict.stderr}")
            if verdict.error:
                output_log_parts.append(f"[validation error] {verdict.error}")

            for line in (verdict.stdout or "").splitlines():
                marker = "__RI_VALIDATION_RESULT__"
                if marker in line:
                    try:
                        payload = json.loads(line.split(marker, 1)[1])
                        passed = bool(payload.get("pass"))
                        details = payload.get("details") or {}
                        break
                    except (json.JSONDecodeError, ValueError):
                        continue
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Notebook validation failure: {exc}",
        ) from exc

    score = round(max_points if passed else 0.0, 2)
    rationale = "Validation passed." if passed else "Validation failed."
    if details:
        rationale += f" Details: {json.dumps(details)[:300]}"
    return {
        "score": score,
        "score_rationale": rationale,
        "scorer_model": "notebook-e2b",
        "scorer_version": "1",
    }
