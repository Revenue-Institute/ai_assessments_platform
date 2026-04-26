"""E2B Jupyter-kernel notebook runner (spec §7.3).

v1 scope: the candidate's notebook is a list of `{type: "code"|"markdown",
source: str}` cells. We provision a fresh E2B sandbox, optionally pull
dataset_urls into /data/, run each code cell through a stateful Python
kernel via Sandbox.run_code (state carries across calls), and capture
per-cell outputs. For grading we append the question's validation_script
in the same kernel and parse its JSON line — the spec format is
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

from ..config import get_settings

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


def _sandbox_or_503():
    settings = get_settings()
    if not settings.e2b_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notebook runner is not configured (E2B_API_KEY missing).",
        )
    try:
        from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="e2b-code-interpreter is not installed on the server.",
        ) from exc
    return Sandbox, settings.e2b_api_key


def _safe_url(url: str) -> str:
    """Whitelist http/https URLs only — `wget` shells out, so anything else is
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
        with sandbox_cls(api_key=api_key, timeout=overall_timeout_s) as sandbox:
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
) -> dict[str, Any]:
    """Provision a fresh kernel, run the candidate's cells, then run the
    question's validation_script in the same kernel and parse the JSON
    {pass, details} it prints. Score is binary pass times max_points (the
    spec leaves room for a richer rubric_ai pass on narrative cells; that
    layers in via score_assignment's rubric_ai path post-hoc)."""

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

    sandbox_cls, api_key = _sandbox_or_503()
    output_log_parts: list[str] = []
    passed = False
    details: dict[str, Any] = {}

    try:
        with sandbox_cls(api_key=api_key, timeout=240) as sandbox:
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

            # Validation: prepend a guard so we can find the JSON line even
            # if the script also prints other things.
            wrapped = (
                "import json as _json, sys as _sys\n"
                "_RI_SENTINEL = '__RI_VALIDATION_RESULT__'\n"
                + validation_script
                + (
                    "\nif isinstance(globals().get('result'), dict):\n"
                    "    _sys.stdout.flush(); print(_RI_SENTINEL + _json.dumps(result))\n"
                )
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
            detail=f"Notebook grading failure: {exc}",
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
