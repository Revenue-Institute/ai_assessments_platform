"""DuckDB-in-E2B SQL runner (spec §7.5).

Each call provisions a fresh E2B sandbox, installs duckdb, applies the
question's schema_sql + seed_sql, runs the candidate query, returns the
result set. We don't persist sandboxes between calls — keeps the service
stateless and avoids cross-attempt leakage.

Grading is column-order-agnostic set equality (per spec) plus optional
regex matching against expected_sql_patterns (e.g. 'must use a window
function')."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from ..config import get_settings


@dataclass(slots=True, frozen=True)
class SqlRunResult:
    columns: list[str]
    rows: list[list[Any]]
    runtime_ms: int
    error: str | None
    timed_out: bool


def _sandbox_or_503():
    settings = get_settings()
    if not settings.e2b_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SQL runner is not configured (E2B_API_KEY missing).",
        )
    try:
        from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="e2b-code-interpreter is not installed on the server.",
        ) from exc
    return Sandbox, settings.e2b_api_key


# DuckDB returns native Python via a small driver script we ship into the
# sandbox. JSON is the wire format because it survives stdout cleanly across
# E2B's command transport.
_DRIVER = r"""
import duckdb, json, sys

schema = open('/home/user/schema.sql').read()
seed = open('/home/user/seed.sql').read()
query = open('/home/user/query.sql').read()

con = duckdb.connect(':memory:')
try:
    if schema.strip():
        con.execute(schema)
    if seed.strip():
        con.execute(seed)
    cur = con.execute(query)
    columns = [d[0] for d in (cur.description or [])]
    rows = [list(r) for r in cur.fetchall()]
    print(json.dumps({"columns": columns, "rows": rows}, default=str))
except Exception as exc:
    print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
"""


def run_sql(
    *,
    schema_sql: str,
    seed_sql: str,
    query_sql: str,
    time_limit_ms: int = 15_000,
) -> SqlRunResult:
    sandbox_cls, api_key = _sandbox_or_503()
    timeout_s = max(2, time_limit_ms // 1000)
    started = time.monotonic()
    timed_out = False
    columns: list[str] = []
    rows: list[list[Any]] = []
    error: str | None = None

    try:
        with sandbox_cls(api_key=api_key, timeout=timeout_s + 15) as sandbox:
            sandbox.commands.run("pip install --quiet duckdb", timeout=120)
            sandbox.files.write("/home/user/schema.sql", schema_sql or "")
            sandbox.files.write("/home/user/seed.sql", seed_sql or "")
            sandbox.files.write("/home/user/query.sql", query_sql or "")
            sandbox.files.write("/home/user/driver.py", _DRIVER)
            try:
                result = sandbox.commands.run(
                    "python /home/user/driver.py",
                    timeout=timeout_s,
                )
                stdout = (result.stdout or "").strip()
                if not stdout:
                    error = (result.stderr or "Empty driver output").strip()
                else:
                    payload = json.loads(stdout.splitlines()[-1])
                    if "error" in payload:
                        error = payload["error"]
                    else:
                        columns = list(payload.get("columns") or [])
                        rows = [list(r) for r in payload.get("rows") or []]
            except Exception as exc:
                timed_out = "timeout" in repr(exc).lower()
                error = error or str(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SQL runner failure: {exc}",
        ) from exc

    return SqlRunResult(
        columns=columns,
        rows=rows,
        runtime_ms=int((time.monotonic() - started) * 1000),
        error=error,
        timed_out=timed_out,
    )


# -- Grading ----------------------------------------------------------------


def _canonicalize_rows(
    columns: list[str], rows: list[list[Any]]
) -> set[tuple[Any, ...]]:
    """Sort each row by column-name order so result-set equality is
    independent of how the candidate ordered SELECT clauses."""
    if not columns:
        return {tuple(r) for r in rows}
    order = sorted(range(len(columns)), key=lambda i: columns[i].lower())
    out: set[tuple[Any, ...]] = set()
    for row in rows:
        ordered = tuple(row[i] if i < len(row) else None for i in order)
        out.add(_normalize_row(ordered))
    return out


def _normalize_row(row: tuple[Any, ...]) -> tuple[Any, ...]:
    """Coerce to JSON-friendly primitives so DuckDB Decimal/datetime values
    compare consistently across runs."""
    return tuple(_normalize_cell(c) for c in row)


def _normalize_cell(cell: Any) -> Any:
    if cell is None:
        return None
    if isinstance(cell, float):
        return round(cell, 6)
    if isinstance(cell, (int, bool, str)):
        return cell
    return str(cell)


def compare_results(
    actual_columns: list[str],
    actual_rows: list[list[Any]],
    expected: dict[str, Any] | list[Any] | None,
) -> tuple[bool, str]:
    """expected may be:
      {"columns": [...], "rows": [[...], ...]}
      [[...], ...]              (rows only, columns inferred or skipped)
      None                       (no expected → cannot grade structurally)
    """

    if expected is None:
        return False, "No expected_query_result on the question — cannot grade."

    if isinstance(expected, list):
        expected_columns = actual_columns
        expected_rows = expected
    elif isinstance(expected, dict):
        expected_columns = list(expected.get("columns") or actual_columns)
        expected_rows = list(expected.get("rows") or [])
    else:
        return False, f"Unsupported expected_query_result shape: {type(expected).__name__}"

    actual_set = _canonicalize_rows(actual_columns, actual_rows)
    expected_set = _canonicalize_rows(expected_columns, expected_rows)
    if actual_set == expected_set:
        return True, (
            f"Result set matches ({len(actual_rows)} rows, "
            f"{len(actual_columns)} columns)."
        )
    missing = expected_set - actual_set
    extra = actual_set - expected_set
    return False, (
        f"Result set mismatch. {len(missing)} expected row(s) missing, "
        f"{len(extra)} unexpected row(s)."
    )


def check_patterns(query_sql: str, patterns: list[str]) -> tuple[bool, str]:
    """All patterns must match (regex) for a pass. Empty list = pass."""

    failed: list[str] = []
    for pat in patterns:
        try:
            if not re.search(pat, query_sql, re.IGNORECASE):
                failed.append(pat)
        except re.error as exc:
            return False, f"Invalid pattern {pat!r}: {exc}"
    if failed:
        return False, "Required patterns missing: " + ", ".join(repr(p) for p in failed)
    return True, "All required SQL patterns present."


def grade_sql_attempt(
    *,
    query_sql: str,
    config: dict[str, Any],
    max_points: float,
) -> dict[str, Any]:
    """Provision DuckDB, run the candidate query, compare to
    expected_query_result, optionally regex-match expected_sql_patterns.
    Returns an attempts-row update payload."""

    schema = config.get("schema_sql") or ""
    seed = config.get("seed_sql") or ""
    expected = config.get("expected_query_result")
    patterns = list(config.get("expected_sql_patterns") or [])

    run = run_sql(schema_sql=schema, seed_sql=seed, query_sql=query_sql)
    if run.error:
        return {
            "score": 0.0,
            "score_rationale": f"SQL execution failed: {run.error}",
            "scorer_model": "duckdb-e2b",
            "scorer_version": "1",
        }

    rows_match = True
    rows_note = "No expected_query_result; skipping result-set check."
    if expected is not None:
        rows_match, rows_note = compare_results(run.columns, run.rows, expected)

    pattern_match = True
    pattern_note = ""
    if patterns:
        pattern_match, pattern_note = check_patterns(query_sql, patterns)

    passed = rows_match and pattern_match
    score = round(max_points if passed else 0.0, 2)
    rationale = rows_note + (f" {pattern_note}" if pattern_note else "")
    return {
        "score": score,
        "score_rationale": rationale.strip(),
        "scorer_model": "duckdb-e2b",
        "scorer_version": "1",
    }
