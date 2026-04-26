"""E2B-backed code execution and test running (spec §7.1).

Each call provisions a fresh sandbox, writes the candidate's solution and
the test files, runs pytest (Python) or the JS test runner, parses results,
then tears down. We don't persist sandbox handles between calls — keeps the
service stateless and avoids cross-attempt leakage.

Fails soft when E2B_API_KEY is unset: callers see a 503 so the candidate's
buffered answer is still saved on submit even when the sandbox is offline."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from ..config import get_settings


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


def _sandbox_or_503():
    settings = get_settings()
    if not settings.e2b_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code runner is not configured (E2B_API_KEY missing).",
        )
    try:
        from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="e2b-code-interpreter is not installed on the server.",
        ) from exc
    return Sandbox, settings.e2b_api_key


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
    sandbox_cls, api_key = _sandbox_or_503()
    timeout_s = max(1, time_limit_ms // 1000)
    started = time.monotonic()
    timed_out = False
    stdout = ""
    stderr = ""
    exit_code = 1

    try:
        with sandbox_cls(api_key=api_key, timeout=timeout_s + 10) as sandbox:
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
        with sandbox_cls(api_key=api_key, timeout=timeout_s + 15) as sandbox:
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
    """Allow only well-formed package specifiers — guards against shell injection
    when we shell-out to pip."""
    if not _PKG_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Refusing to install package with unsafe name: {name!r}",
        )
    return name


def grade_code_attempt(
    *,
    code: str,
    config: dict[str, Any],
    max_points: float,
) -> dict[str, Any]:
    """Run hidden tests and convert the pass rate into a score (spec §7.1).

    Returns a dict ready to splat into an attempts row update."""

    hidden_tests = config.get("hidden_tests")
    if not hidden_tests:
        return {}
    result = run_test_suite(
        code=code,
        tests=hidden_tests,
        language=config.get("language", "python"),
        packages=list(config.get("packages") or []),
        time_limit_ms=int(config.get("time_limit_exec_ms") or 15_000),
    )
    score = (
        round((result.passed / result.total) * max_points, 2)
        if result.total
        else 0.0
    )
    rationale_lines = [
        f"{result.passed}/{result.total} hidden tests passed.",
    ]
    if result.failed:
        rationale_lines.append(f"{result.failed} failed.")
    if result.errors:
        rationale_lines.append(f"{result.errors} errored.")
    if result.timed_out:
        rationale_lines.append("Timed out.")
    return {
        "score": score,
        "score_rationale": " ".join(rationale_lines),
        "scorer_model": "e2b-pytest",
        "scorer_version": "1",
    }
