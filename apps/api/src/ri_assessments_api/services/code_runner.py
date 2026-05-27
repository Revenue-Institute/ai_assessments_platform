"""E2B-backed code execution and test running (spec §7.1).

Each call provisions a fresh sandbox, writes the candidate's solution and
the test files, runs pytest (Python) or the JS test runner, parses results,
then tears down. We don't persist sandbox handles between calls, keeps the
service stateless and avoids cross-attempt leakage.

Fails soft when E2B_API_KEY is unset: callers see a 503 so the candidate's
buffered answer is still saved on submit even when the sandbox is offline."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import queue as _queue
import re
import string
import threading
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from .e2b_sandbox import get_sandbox as _sandbox_or_503
from .narrative_grader import grade as _narrative_grade_call
from .narrative_grader import rubric_wants_narrative as _rubric_wants_narrative
from .narrative_grader import serialize_criteria as _criteria_summary

log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class CodeRunResult:
    stdout: str
    stderr: str
    exit_code: int
    runtime_ms: int
    timed_out: bool


@dataclass(slots=True, frozen=True)
class TestRunResult:
    passed: int
    failed: int
    errors: int
    total: int
    output: str
    runtime_ms: int
    timed_out: bool


def _file_for_language(language: str) -> tuple[str, str]:
    """Returns (solution_filename, run_command) for a candidate buffer."""
    if language == "python":
        return "solution.py", "PYTHONPATH=/home/user python /home/user/solution.py"
    if language in ("javascript", "typescript"):
        ext = "js" if language == "javascript" else "ts"
        return f"solution.{ext}", f"node /home/user/solution.{ext}"
    if language == "bash":
        return "solution.sh", "bash /home/user/solution.sh"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Language {language!r} is not yet supported.",
    )


def run_user_code(
    *,
    code: str,
    language: str = "python",
    packages: list[str] | None = None,
    time_limit_ms: int = 10_000,
) -> CodeRunResult:
    # Buffered (non-streaming) entry point retained for back-compat
    # callers and tests. For live stdout/stderr fanout (spec §7.1,
    # §14.3) use `run_user_code_streaming` from the SSE route.
    sandbox_cls, api_key = _sandbox_or_503()
    timeout_s = max(1, time_limit_ms // 1000)
    started = time.monotonic()
    timed_out = False
    stdout = ""
    stderr = ""
    exit_code = 1

    try:
        with sandbox_cls.create(api_key=api_key, timeout=timeout_s + 10) as sandbox:
            if packages:
                sandbox.commands.run(
                    f"pip install --quiet {' '.join(_safe_pkg(p) for p in packages)}",
                    timeout=120,
                )
            filename, run_cmd = _file_for_language(language)
            sandbox.files.write(f"/home/user/{filename}", code)
            try:
                result = sandbox.commands.run(
                    run_cmd,
                    timeout=timeout_s,
                )
                stdout = result.stdout or ""
                stderr = result.stderr or ""
                exit_code = result.exit_code if result.exit_code is not None else 1
            except Exception as exc:  # timeout and friends
                timed_out = "timeout" in repr(exc).lower()
                stderr = stderr or str(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Code runner failure: {exc}",
        ) from exc

    return CodeRunResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        runtime_ms=int((time.monotonic() - started) * 1000),
        timed_out=timed_out,
    )


def _sse_line(payload: dict[str, Any]) -> bytes:
    """Encode one SSE `data:` frame. Keep the JSON on a single line so
    SSE clients see exactly one `data:` per event (multi-line JSON would
    require splitting on '\\n')."""

    return f"data: {_json.dumps(payload, separators=(',', ':'))}\n\n".encode()


async def run_user_code_streaming(
    *,
    code: str,
    language: str = "python",
    packages: list[str] | None = None,
    time_limit_ms: int = 10_000,
) -> AsyncGenerator[bytes, None]:
    """Async generator yielding SSE frames for a single user-code run
    (spec §7.1, §14.3).

    Event shapes:
      data: {"type": "started", "language": str, "time_limit_ms": int}
      data: {"type": "stdout", "chunk": str}
      data: {"type": "stderr", "chunk": str}
      data: {"type": "exit",   "exit_code": int, "runtime_ms": int,
              "timed_out": bool, "error": str|None}

    Bridge model: E2B's Python SDK is sync (`Sandbox.commands.run`
    blocks and dispatches `on_stdout`/`on_stderr` callbacks on its own
    thread). We run the whole sandbox lifecycle in a worker thread via
    `asyncio.to_thread`, while the callbacks LPUSH onto a thread-safe
    `queue.Queue`. The async generator pulls from that queue with a
    short poll (run_in_executor on Queue.get with a timeout) so we
    cooperate with the event loop, emit a periodic heartbeat, and exit
    cleanly when the sandbox thread signals completion via a sentinel.

    Wrap in `StreamingResponse(media_type='text/event-stream')` at the
    router layer."""

    sandbox_cls, api_key = _sandbox_or_503()
    timeout_s = max(1, time_limit_ms // 1000)
    started = time.monotonic()

    # Thread-safe one-way pipe between the sync E2B callbacks (running on
    # whatever worker thread the SDK chooses) and this async generator.
    # Each item is a dict; a `None` is the sentinel marking "sandbox
    # finished, no more frames coming".
    msg_q: _queue.Queue[dict[str, Any] | None] = _queue.Queue()

    def _on_stdout(line: Any) -> None:
        # E2B may pass a string or a small object with a .line / .text
        # attribute depending on SDK version; coerce defensively.
        text = getattr(line, "line", None) or getattr(line, "text", None) or str(line)
        if text:
            msg_q.put({"type": "stdout", "chunk": text})

    def _on_stderr(line: Any) -> None:
        text = getattr(line, "line", None) or getattr(line, "text", None) or str(line)
        if text:
            msg_q.put({"type": "stderr", "chunk": text})

    def _run_sandbox() -> dict[str, Any]:
        """Sync worker that owns the sandbox lifecycle. Returns the
        terminal `exit` frame so the async side can emit it after
        draining the queue."""

        exit_code = 1
        timed_out = False
        error: str | None = None
        try:
            with sandbox_cls.create(api_key=api_key, timeout=timeout_s + 10) as sandbox:
                if packages:
                    sandbox.commands.run(
                        f"pip install --quiet {' '.join(_safe_pkg(p) for p in packages)}",
                        timeout=120,
                    )
                filename, run_cmd = _file_for_language(language)
                sandbox.files.write(f"/home/user/{filename}", code)
                try:
                    result = sandbox.commands.run(
                        run_cmd,
                        timeout=timeout_s,
                        on_stdout=_on_stdout,
                        on_stderr=_on_stderr,
                    )
                    exit_code = result.exit_code if result.exit_code is not None else 1
                except Exception as exc:
                    timed_out = "timeout" in repr(exc).lower()
                    error = str(exc)
        except HTTPException as exc:
            error = exc.detail if isinstance(exc.detail, str) else "code runner unavailable"
        except Exception as exc:
            error = f"Code runner failure: {exc}"
        return {
            "type": "exit",
            "exit_code": exit_code,
            "runtime_ms": int((time.monotonic() - started) * 1000),
            "timed_out": timed_out,
            "error": error,
        }

    # Kick off the sandbox in a background thread. We hold on to the
    # thread handle so we can join it after the generator's loop
    # finishes; this guarantees the exit frame's runtime_ms reflects
    # the full sandbox lifecycle.
    sandbox_result: dict[str, Any] = {}

    def _thread_target() -> None:
        try:
            sandbox_result.update(_run_sandbox())
        finally:
            msg_q.put(None)

    worker = threading.Thread(target=_thread_target, name="e2b-stream", daemon=True)
    worker.start()

    # Initial frame so the client flips into "running" state immediately,
    # before the first stdout byte arrives.
    yield _sse_line(
        {"type": "started", "language": language, "time_limit_ms": time_limit_ms}
    )

    loop = asyncio.get_running_loop()
    try:
        while True:
            # Poll the queue with a 1s timeout so we can interleave a
            # heartbeat comment if the candidate's code is silent for a
            # long time. SSE comment lines (": text") are ignored by
            # browsers but prevent proxy idle disconnects.
            try:
                item = await loop.run_in_executor(
                    None, lambda: msg_q.get(timeout=1.0)
                )
            except _queue.Empty:
                yield b": keepalive\n\n"
                continue
            if item is None:
                # Sentinel: sandbox thread finished. Drain any final
                # frames the worker pushed before the sentinel (rare,
                # but the queue could race) by exiting the loop. The
                # `exit` frame is emitted below from sandbox_result.
                break
            yield _sse_line(item)
    finally:
        # Make sure the worker has populated sandbox_result before we
        # emit the exit frame. Generous join timeout because the
        # sandbox-side timeout was already enforced upstream.
        await loop.run_in_executor(None, lambda: worker.join(timeout=timeout_s + 15))

    exit_frame = sandbox_result or {
        "type": "exit",
        "exit_code": 1,
        "runtime_ms": int((time.monotonic() - started) * 1000),
        "timed_out": False,
        "error": "sandbox thread did not return",
    }
    yield _sse_line(exit_frame)


_PYTEST_SUMMARY = re.compile(
    r"(?P<n>\d+)\s+(?P<word>passed|failed|error|errors)",
    re.IGNORECASE,
)


def _parse_pytest_summary(stdout: str) -> tuple[int, int, int]:
    """Return (passed, failed, errors) from pytest's summary line.

    Matches the standard `=== N passed, M failed in T.Ts ===` pattern. Falls
    back to scanning the whole output for word counts when the summary is
    missing (rare, e.g. collection error)."""
    passed = failed = errors = 0
    for match in _PYTEST_SUMMARY.finditer(stdout):
        word = match.group("word").lower()
        n = int(match.group("n"))
        if word == "passed":
            passed = max(passed, n)
        elif word == "failed":
            failed = max(failed, n)
        elif word.startswith("error"):
            errors = max(errors, n)
    return passed, failed, errors


def run_test_suite(
    *,
    code: str,
    tests: str,
    language: str = "python",
    packages: list[str] | None = None,
    time_limit_ms: int = 15_000,
) -> TestRunResult:
    """Runs a pytest-style suite against the candidate's code in a fresh
    sandbox. Currently Python-only; JS/TS lands when we wire vitest in a
    sandbox image."""

    if language != "python":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Test running for {language!r} is not yet implemented.",
        )

    sandbox_cls, api_key = _sandbox_or_503()
    timeout_s = max(2, time_limit_ms // 1000)
    started = time.monotonic()
    output = ""
    timed_out = False

    try:
        with sandbox_cls.create(api_key=api_key, timeout=timeout_s + 15) as sandbox:
            if packages:
                sandbox.commands.run(
                    f"pip install --quiet {' '.join(_safe_pkg(p) for p in packages)}",
                    timeout=180,
                )
            sandbox.files.write("/home/user/solution.py", code)
            sandbox.files.write("/home/user/tests/__init__.py", "")
            sandbox.files.write("/home/user/tests/test_hidden.py", tests)
            sandbox.commands.run("touch /home/user/__init__.py", timeout=10)

            try:
                result = sandbox.commands.run(
                    "cd /home/user && PYTHONPATH=/home/user python -m pytest tests/ "
                    "--tb=short -q --no-header --color=no",
                    timeout=timeout_s,
                )
                output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            except Exception as exc:
                timed_out = "timeout" in repr(exc).lower()
                output = output or str(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Test runner failure: {exc}",
        ) from exc

    passed, failed, errors = _parse_pytest_summary(output)
    total = passed + failed + errors
    return TestRunResult(
        passed=passed,
        failed=failed,
        errors=errors,
        total=total,
        output=output,
        runtime_ms=int((time.monotonic() - started) * 1000),
        timed_out=timed_out,
    )


_PKG_RE = re.compile(r"^[A-Za-z0-9_.\-]+(?:[<>=!~]+[A-Za-z0-9_.\-]+)?$")


def _safe_pkg(name: str) -> str:
    """Allow only well-formed package specifiers, guards against shell injection
    when we shell-out to pip."""
    if not _PKG_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Refusing to install package with unsafe name: {name!r}",
        )
    return name


_VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _render_hidden_tests(
    hidden_tests: str, variables: dict[str, Any] | None
) -> str:
    """Spec §7.1: hidden tests parameterize on the attempt's
    `variables_used`. Replace `{{ name }}` (jinja-style) with the Python
    repr of `variables[name]` so numeric and string values both survive
    substitution. Unknown variables are left as-is so authors get a
    visible failure rather than a silent zero-fill."""

    if not hidden_tests or not variables:
        return hidden_tests

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in variables:
            return repr(variables[name])
        return match.group(0)

    return _VAR_PATTERN.sub(_sub, hidden_tests)


def grade_code_attempt(
    *,
    code: str,
    config: dict[str, Any],
    max_points: float,
    variables_used: dict[str, Any] | None = None,
    rubric: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run hidden tests and convert the pass rate into a score (spec §7.1).

    `variables_used` lets us parameterize hidden tests with the same
    sampled values the candidate's prompt used (spec §7.1: "Parameterize
    tests with the same variables used in the rendered prompt").

    `rubric`, when populated with criteria, triggers a Claude Sonnet 4.6
    code-quality narrative pass; the narrative score blends into the
    final score. Skipped silently if Anthropic isn't configured.

    Returns a dict ready to splat into an attempts row update."""

    language = config.get("language", "python")
    hidden_tests = _render_hidden_tests(
        config.get("hidden_tests") or "", variables_used
    )
    if not hidden_tests:
        return {}
    result = run_test_suite(
        code=code,
        tests=hidden_tests,
        language=language,
        packages=list(config.get("packages") or []),
        time_limit_ms=int(config.get("time_limit_exec_ms") or 15_000),
    )
    test_pct = (result.passed / result.total) if result.total else 0.0
    rationale_lines = [
        f"{result.passed}/{result.total} hidden tests passed.",
    ]
    if result.failed:
        rationale_lines.append(f"{result.failed} failed.")
    if result.errors:
        rationale_lines.append(f"{result.errors} errored.")
    if result.timed_out:
        rationale_lines.append("Timed out.")

    # Code-quality narrative pass (spec §7.1): when the rubric has style
    # criteria, send the final code to Claude for a structured score.
    narrative = None
    if _rubric_wants_narrative(rubric):
        narrative = _narrative_code_grade(code, language, rubric or {})
    overall_pct = test_pct
    if narrative is not None and isinstance(narrative.get("pct"), (int, float)):
        overall_pct = max(0.0, min(1.0, 0.7 * test_pct + 0.3 * float(narrative["pct"])))
        if narrative.get("rationale"):
            rationale_lines.append(f"Narrative: {narrative['rationale']}")

    score = round(overall_pct * max_points, 2)
    return {
        "score": score,
        "score_rationale": " ".join(rationale_lines),
        "scorer_model": (
            "e2b-pytest+narrative" if narrative is not None else "e2b-pytest"
        ),
        "scorer_version": "1",
    }


def _narrative_code_grade(
    code: str, language: str, rubric: dict[str, Any]
) -> dict[str, Any] | None:
    """Claude reviews the candidate's final code against the rubric's
    narrative criteria. Returns {pct: 0..1, rationale: str} or None on
    any failure. Never raises. Shared call shape lives in
    services.narrative_grader; this function owns only the code-specific
    prompt framing."""

    system = (
        "You are reviewing candidate code for style and design "
        "criteria (readability, correctness signals, idiomatic use "
        f"of {language}, defensive coding). Respond with a single "
        'JSON object: {"pct": <float 0..1>, '
        '"rationale": "<one or two sentences>"}. '
        "No prose outside the JSON."
    )
    user = (
        "Rubric criteria:\n"
        f"{_criteria_summary(rubric)}\n\n"
        f"Candidate {language} code:\n```\n{code[:12000]}\n```"
    )
    return _narrative_grade_call(subject_label="code", system=system, user=user)


# Re-exported for callers that want to substitute placeholders the same
# way grade_code_attempt does (e.g. visible test renderer).
_string_template_sentinel = string.Template
