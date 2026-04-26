"""Solver execution (spec §8.3, §8.4).

Solvers are short Python snippets defined per question template. We
execute them in an E2B sandbox to compute a deterministic
`expected_answer` for the sampled variables. Three callsites:

  1. Lazy attempt creation — populates attempts.expected_answer the
     first time the candidate views a question (so exact_match /
     numeric_tolerance scoring has something to compare against).
  2. Module publish (§8.4 fairness validation) — runs the solver on
     50 sampled variable sets and rejects publish if any error.
  3. Generation stage 2 self-verification (§6.3 rule 10) — runs the
     solver on 3 sampled variable sets to confirm it parses + executes.

Fails soft when E2B_API_KEY is unset: callers get None back and the
system continues without solver-derived answers. Admin can rescore
later once the sandbox is reachable."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, status

from ..config import get_settings

log = logging.getLogger(__name__)


_SOLVER_DRIVER = r'''
import json, sys

VARIABLES = json.loads({variables_literal})

{solver_code}

result = solve(VARIABLES)
print("__RI_SOLVER_RESULT__" + json.dumps(result, default=str))
'''


def _sandbox_or_none():
    settings = get_settings()
    if not settings.e2b_api_key:
        return None
    try:
        from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
    except ImportError:
        return None
    return Sandbox, settings.e2b_api_key


def execute_solver(
    *,
    solver_code: str,
    variables: dict[str, Any],
    time_limit_ms: int = 10_000,
) -> dict[str, Any] | None:
    """Run `def solve(variables)` from solver_code with the given vars,
    parse the JSON result. Returns None on any failure (E2B unavailable,
    syntax error, runtime error)."""

    if not solver_code or not solver_code.strip():
        return None

    sandbox_setup = _sandbox_or_none()
    if sandbox_setup is None:
        return None
    sandbox_cls, api_key = sandbox_setup

    timeout_s = max(2, time_limit_ms // 1000)
    driver = _SOLVER_DRIVER.format(
        variables_literal=json.dumps(json.dumps(variables)),
        solver_code=solver_code,
    )

    try:
        with sandbox_cls(api_key=api_key, timeout=timeout_s + 10) as sandbox:
            sandbox.files.write("/home/user/solver.py", driver)
            result = sandbox.commands.run(
                "python /home/user/solver.py",
                timeout=timeout_s,
            )
            if result.exit_code != 0:
                log.warning(
                    "solver exit %s: %s",
                    result.exit_code,
                    (result.stderr or "")[:300],
                )
                return None
            for line in (result.stdout or "").splitlines():
                marker = "__RI_SOLVER_RESULT__"
                if marker in line:
                    payload = line.split(marker, 1)[1]
                    return json.loads(payload)
            return None
    except Exception as exc:
        log.warning("solver execution failed: %s", exc)
        return None


def fairness_check(
    *,
    solver_code: str,
    variable_schema: dict[str, Any],
    sample_count: int = 50,
    random_seed: int = 0,
) -> dict[str, Any]:
    """Spec §8.4: sample N variable sets, run the solver, confirm every
    run produces a JSON-serialisable result. Returns a report; caller
    decides whether to block publish."""

    from .randomizer import sample_variables

    failures: list[dict[str, Any]] = []
    successes = 0
    for i in range(sample_count):
        seed = f"fairness::{random_seed}::{i}"
        try:
            variables = sample_variables(variable_schema, seed)
        except Exception as exc:
            failures.append({"seed": seed, "stage": "sample", "error": str(exc)})
            continue
        if not solver_code:
            # No solver => can't verify. Treat as informational, not failure.
            successes += 1
            continue
        result = execute_solver(solver_code=solver_code, variables=variables)
        if result is None:
            failures.append({"seed": seed, "stage": "solve", "error": "solver returned no result"})
            continue
        if not isinstance(result, dict):
            failures.append(
                {
                    "seed": seed,
                    "stage": "shape",
                    "error": f"expected dict from solver, got {type(result).__name__}",
                }
            )
            continue
        successes += 1

    return {
        "samples": sample_count,
        "successes": successes,
        "failures": failures,
        "passed": len(failures) == 0,
    }


def fairness_check_module(
    *,
    questions: list[dict[str, Any]],
    sample_count: int = 50,
) -> dict[str, Any]:
    """Run fairness_check across every question on a module. Used by
    publish_module (§8.4 'Fails block publish')."""

    overall_passed = True
    per_question: list[dict[str, Any]] = []
    for q in questions:
        solver = q.get("solver_code") or ""
        schema = q.get("variable_schema") or {}
        if not solver and not schema:
            per_question.append(
                {"question_id": q.get("id"), "skipped": True, "reason": "no solver, no variables"}
            )
            continue
        report = fairness_check(
            solver_code=solver,
            variable_schema=schema,
            sample_count=sample_count,
        )
        report["question_id"] = q.get("id")
        per_question.append(report)
        if not report["passed"]:
            overall_passed = False
    return {"passed": overall_passed, "per_question": per_question}


def assert_publishable(report: dict[str, Any]) -> None:
    """Raise 409 with a useful detail if a fairness report fails."""
    if report.get("passed"):
        return
    bad = [r for r in (report.get("per_question") or []) if not r.get("passed", True)]
    sample = bad[:3] if bad else []
    detail = (
        f"Fairness check failed for {len(bad)} question(s). "
        f"First failures: {sample}"
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )
