"""Solver execution (spec §8.3, §8.4).

Solvers are short Python snippets defined per question template. We
execute them in an E2B sandbox to compute a deterministic
`expected_answer` for the sampled variables. Three callsites:

  1. Lazy attempt creation, populates attempts.expected_answer the
     first time the candidate views a question (so exact_match /
     numeric_tolerance scoring has something to compare against).
  2. Module publish (§8.4 fairness validation), runs the solver on
     50 sampled variable sets and rejects publish if any error.
  3. Generation stage 2 self-verification (§6.3 rule 10), runs the
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


# Bulk driver runs the same solver across N variable sets in a single
# sandbox, collapsing the per-sample cold-start cost (~500-1000ms) to
# one. Used by fairness_check and fairness_check_module so publish stays
# under tens of seconds instead of minutes.
_SOLVER_BULK_DRIVER = r'''
import json, traceback

VARIABLE_SETS = json.loads({variable_sets_literal})

{solver_code}

results = []
for variables in VARIABLE_SETS:
    try:
        r = solve(variables)
        results.append({{"ok": True, "result": r}})
    except Exception as exc:
        results.append({{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}})
print("__RI_SOLVER_BULK__" + json.dumps(results, default=str))
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
        with sandbox_cls.create(api_key=api_key, timeout=timeout_s + 10) as sandbox:
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


def execute_solver_bulk(
    *,
    solver_code: str,
    variable_sets: list[dict[str, Any]],
    time_limit_ms: int = 30_000,
) -> list[dict[str, Any]] | None:
    """Run `solve(variables)` for each entry in `variable_sets` inside a
    single E2B sandbox. Returns one result entry per input in order, each
    shaped {"ok": bool, "result"?: any, "error"?: str}. Returns None when
    E2B is unavailable; caller decides what to do.

    This is the hot path for publish-time fairness validation; the bulk
    form collapses N sandbox cold starts (~500-1000ms each) into one."""

    if not solver_code or not solver_code.strip():
        return None
    if not variable_sets:
        return []

    sandbox_setup = _sandbox_or_none()
    if sandbox_setup is None:
        return None
    sandbox_cls, api_key = sandbox_setup

    timeout_s = max(5, time_limit_ms // 1000)
    driver = _SOLVER_BULK_DRIVER.format(
        variable_sets_literal=json.dumps(json.dumps(variable_sets)),
        solver_code=solver_code,
    )

    try:
        with sandbox_cls.create(api_key=api_key, timeout=timeout_s + 10) as sandbox:
            sandbox.files.write("/home/user/solver_bulk.py", driver)
            result = sandbox.commands.run(
                "python /home/user/solver_bulk.py",
                timeout=timeout_s,
            )
            if result.exit_code != 0:
                log.warning(
                    "bulk solver exit %s: %s",
                    result.exit_code,
                    (result.stderr or "")[:300],
                )
                return None
            for line in (result.stdout or "").splitlines():
                marker = "__RI_SOLVER_BULK__"
                if marker in line:
                    payload = line.split(marker, 1)[1]
                    parsed = json.loads(payload)
                    if isinstance(parsed, list):
                        return parsed
            return None
    except Exception as exc:
        log.warning("bulk solver execution failed: %s", exc)
        return None


def fairness_check(
    *,
    solver_code: str,
    variable_schema: dict[str, Any],
    sample_count: int = 50,
    random_seed: int = 0,
) -> dict[str, Any]:
    """Spec §8.4: sample N variable sets, run the solver, confirm every
    run produces a JSON-serialisable dict. Returns a report; caller
    decides whether to block publish.

    Implementation note: samples are pre-computed deterministically from
    the seed and sent to one sandbox via execute_solver_bulk. A previous
    implementation spun up one sandbox per sample, which made publish
    take minutes for typical modules."""

    from .randomizer import sample_variables

    failures: list[dict[str, Any]] = []
    sample_seeds: list[str] = []
    sampled: list[dict[str, Any]] = []
    for i in range(sample_count):
        seed = f"fairness::{random_seed}::{i}"
        try:
            variables = sample_variables(variable_schema, seed)
        except Exception as exc:
            failures.append({"seed": seed, "stage": "sample", "error": str(exc)})
            continue
        sample_seeds.append(seed)
        sampled.append(variables)

    if not solver_code:
        # No solver => can't run. Each successful sample counts as
        # informational pass (variables sampled cleanly).
        return {
            "samples": sample_count,
            "successes": len(sampled),
            "failures": failures,
            "passed": not failures,
        }

    bulk_results = execute_solver_bulk(
        solver_code=solver_code,
        variable_sets=sampled,
    )

    if bulk_results is None:
        # E2B offline. Mirror the old single-call behavior: emit a
        # `solver returned no result` failure per sample. _self_verify_question
        # treats the all-no-result case as "could not verify, accept";
        # publish-time assert_publishable will block.
        for seed in sample_seeds:
            failures.append(
                {"seed": seed, "stage": "solve", "error": "solver returned no result"}
            )
        return {
            "samples": sample_count,
            "successes": 0,
            "failures": failures,
            "passed": not failures,
        }

    successes = 0
    for seed, sample_result in zip(sample_seeds, bulk_results, strict=False):
        if not sample_result.get("ok"):
            failures.append(
                {
                    "seed": seed,
                    "stage": "solve",
                    "error": sample_result.get("error") or "solver returned no result",
                }
            )
            continue
        result = sample_result.get("result")
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
        "passed": not failures,
    }


def fairness_check_module(
    *,
    questions: list[dict[str, Any]],
    sample_count: int = 50,
    max_workers: int = 4,
) -> dict[str, Any]:
    """Run fairness_check across every question on a module. Used by
    publish_module (§8.4 'Fails block publish').

    Per-question fairness checks run in a small thread pool so publish
    on a 10-question module finishes in seconds, not minutes. The cap
    keeps E2B concurrency below the typical paid-plan default."""

    from concurrent.futures import ThreadPoolExecutor

    eligible: list[tuple[int, dict[str, Any]]] = []
    per_question: list[dict[str, Any] | None] = [None] * len(questions)

    for idx, q in enumerate(questions):
        solver = q.get("solver_code") or ""
        schema = q.get("variable_schema") or {}
        if not solver and not schema:
            per_question[idx] = {
                "question_id": q.get("id"),
                "skipped": True,
                "reason": "no solver, no variables",
            }
            continue
        eligible.append((idx, q))

    if eligible:
        def _run(item: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any]]:
            idx, q = item
            report = fairness_check(
                solver_code=q.get("solver_code") or "",
                variable_schema=q.get("variable_schema") or {},
                sample_count=sample_count,
            )
            report["question_id"] = q.get("id")
            return idx, report

        workers = min(max_workers, len(eligible)) or 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for idx, report in pool.map(_run, eligible):
                per_question[idx] = report

    overall_passed = all(
        (entry is None) or entry.get("passed", True) or entry.get("skipped")
        for entry in per_question
    )
    return {
        "passed": overall_passed,
        "per_question": [p for p in per_question if p is not None],
    }


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
