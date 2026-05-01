"""Seed a runners-coverage assignment: one question for each of sql,
notebook, and diagram so we can drive the full runner stack end-to-end.

Idempotent on the module + assessment + subject. Always creates a fresh
assignment + token so each run hands back a usable magic link.

Usage:
    cd apps/api
    SEED_ADMIN_EMAIL=qa-admin@revenueinstitute.com \
    SEED_ADMIN_PASSWORD=qa-password-1234 \
        uv run python scripts/seed_runners_assignment.py
"""

from __future__ import annotations

import os
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ri_assessments_api.auth import issue_candidate_token  # noqa: E402
from ri_assessments_api.config import get_settings  # noqa: E402
from ri_assessments_api.db import get_supabase  # noqa: E402
from ri_assessments_api.services.tokens import (  # noqa: E402
    candidate_token_url,
    hash_token,
)


MODULE_SLUG = "seed-runners"
ASSESSMENT_SLUG = "seed-runners"
SUBJECT_EMAIL = "seed-candidate@revenueinstitute.local"


def _runner_questions() -> list[dict]:
    return [
        # SQL: filter + sort
        {
            "type": "sql",
            "prompt_template": (
                "Return the names and ARR of the top three customers by "
                "ARR descending. Columns must be `name`, `arr`."
            ),
            "variable_schema": {},
            "rubric": {
                "version": "1",
                "scoring_mode": "test_cases",
                "criteria": [
                    {
                        "id": "result",
                        "label": "Returns the expected rows",
                        "weight": 1.0,
                        "description": "Result rows match expected.",
                        "scoring_guidance": "Set equality, column-order agnostic.",
                    }
                ],
            },
            "competency_tags": ["data.sql"],
            "max_points": 10,
            "interactive_config": {
                "schema_sql": (
                    "create table customers ("
                    "id integer primary key, name text, arr numeric"
                    ");"
                ),
                "seed_sql": (
                    "insert into customers values "
                    "(1, 'Acme', 120000),"
                    "(2, 'Globex', 480000),"
                    "(3, 'Initech', 90000),"
                    "(4, 'Stark', 760000),"
                    "(5, 'Wayne', 340000);"
                ),
                "expected_query_result": {
                    "columns": ["name", "arr"],
                    "rows": [
                        ["Stark", 760000],
                        ["Globex", 480000],
                        ["Wayne", 340000],
                    ],
                },
                "starter_sql": "-- write your query here\n",
            },
        },
        # Notebook: kernel-state check (the grader inspects a variable
        # the candidate sets, rather than parsing stdout)
        {
            "type": "notebook",
            "prompt_template": (
                "In the first code cell, compute the mean of "
                "[1, 2, 3, 4, 5] and assign it to a variable named `mean`. "
                "The grader runs your cells, then checks that `mean == 3.0`."
            ),
            "variable_schema": {},
            "rubric": {
                "version": "1",
                "scoring_mode": "test_cases",
                "criteria": [
                    {
                        "id": "stdout_match",
                        "label": "Prints expected value",
                        "weight": 1.0,
                        "description": "First cell stdout contains '3.0'.",
                        "scoring_guidance": "Substring match in stdout.",
                    }
                ],
            },
            "competency_tags": ["data.python"],
            "max_points": 10,
            "interactive_config": {
                "starter_cells": [
                    {"type": "code", "source": "# write your code here\n"},
                ],
                "validation_script": (
                    "_got = globals().get('mean')\n"
                    "result = {"
                    "'pass': isinstance(_got, (int, float)) and _got == 3.0, "
                    "'details': {'got': _got}}\n"
                ),
                "dataset_urls": [],
            },
        },
        # Diagram: a 3-node, 2-edge process
        {
            "type": "diagram",
            "prompt_template": (
                "Sketch the flow: a new lead comes in, gets enriched, then "
                "is routed to an SDR. Three nodes, two edges, in that order."
            ),
            "variable_schema": {},
            "rubric": {
                "version": "1",
                "scoring_mode": "structural_match",
                "criteria": [
                    {
                        "id": "structure",
                        "label": "Matches reference structure",
                        "weight": 1.0,
                        "description": "Nodes + edges match the reference graph.",
                        "scoring_guidance": "Greedy fuzzy node match + edge equality.",
                    }
                ],
            },
            "competency_tags": ["ops.process_design"],
            "max_points": 10,
            "interactive_config": {
                "reference_structure": {
                    "nodes": [
                        {"id": "n1", "type": "default", "label": "New Lead"},
                        {"id": "n2", "type": "default", "label": "Enrich"},
                        {"id": "n3", "type": "default", "label": "Route to SDR"},
                    ],
                    "edges": [
                        {"source": "n1", "target": "n2"},
                        {"source": "n2", "target": "n3"},
                    ],
                },
            },
        },
    ]


def ensure_admin_user_id(supabase) -> str:
    email = os.environ.get(
        "SEED_ADMIN_EMAIL", "qa-admin@revenueinstitute.com"
    )
    res = (
        supabase.table("users")
        .select("id")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise RuntimeError(
            f"Admin user '{email}' not found. Run seed_test_assignment.py first."
        )
    return res.data[0]["id"]


def ensure_subject(supabase) -> str:
    res = (
        supabase.table("subjects")
        .select("id")
        .eq("email", SUBJECT_EMAIL)
        .eq("type", "candidate")
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["id"]
    inserted = (
        supabase.table("subjects")
        .insert(
            {
                "type": "candidate",
                "full_name": "Seed Candidate",
                "email": SUBJECT_EMAIL,
                "metadata": {"role_applied_for": "Runners QA"},
            }
        )
        .execute()
    )
    return inserted.data[0]["id"]


def ensure_module(supabase, admin_id: str) -> tuple[str, list[dict]]:
    existing_module = (
        supabase.table("modules")
        .select("id")
        .eq("slug", MODULE_SLUG)
        .limit(1)
        .execute()
    )
    if existing_module.data:
        module_id = existing_module.data[0]["id"]
    else:
        inserted = (
            supabase.table("modules")
            .insert(
                {
                    "slug": MODULE_SLUG,
                    "title": "Seed runners coverage",
                    "description": (
                        "One question per interactive runner type "
                        "(sql, notebook, diagram). Used for QA, not for "
                        "real evaluation."
                    ),
                    "domain": "ops",
                    "target_duration_minutes": 20,
                    "difficulty": "junior",
                    "status": "published",
                    "version": 1,
                    "created_by": admin_id,
                    "published_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        module_id = inserted.data[0]["id"]

    existing_templates = (
        supabase.table("question_templates")
        .select(
            "id, module_id, position, type, prompt_template, "
            "variable_schema, solver_code, solver_language, "
            "interactive_config, rubric, competency_tags, "
            "time_limit_seconds, max_points, metadata"
        )
        .eq("module_id", module_id)
        .order("position")
        .execute()
    )
    if existing_templates.data:
        return module_id, existing_templates.data

    rows: list[dict] = []
    for position, q in enumerate(_runner_questions()):
        row = {
            "module_id": module_id,
            "position": position,
            "type": q["type"],
            "prompt_template": q["prompt_template"],
            "variable_schema": q.get("variable_schema") or {},
            "solver_code": q.get("solver_code"),
            "solver_language": q.get("solver_language") or "python",
            "interactive_config": q.get("interactive_config"),
            "rubric": q["rubric"],
            "competency_tags": q.get("competency_tags") or [],
            "max_points": q["max_points"],
            "time_limit_seconds": q.get("time_limit_seconds"),
            "metadata": {"difficulty": "junior"},
        }
        inserted = supabase.table("question_templates").insert(row).execute()
        rows.append(inserted.data[0])
    return module_id, rows


def ensure_assessment(supabase, admin_id: str, module_id: str) -> str:
    existing = (
        supabase.table("assessments")
        .select("id")
        .eq("slug", ASSESSMENT_SLUG)
        .limit(1)
        .execute()
    )
    title = "Seed Runners Coverage"
    description = (
        "Wraps the runners-coverage module so we can drive sql, "
        "notebook, and diagram end-to-end via the candidate flow."
    )
    if existing.data:
        assessment_id = existing.data[0]["id"]
        supabase.table("assessments").update(
            {
                "title": title,
                "description": description,
                "status": "published",
            }
        ).eq("id", assessment_id).execute()
    else:
        inserted = (
            supabase.table("assessments")
            .insert(
                {
                    "slug": ASSESSMENT_SLUG,
                    "title": title,
                    "description": description,
                    "status": "published",
                    "version": 1,
                    "created_by": admin_id,
                    "published_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        assessment_id = inserted.data[0]["id"]

    link_check = (
        supabase.table("assessment_modules")
        .select("module_id")
        .eq("assessment_id", assessment_id)
        .eq("module_id", module_id)
        .limit(1)
        .execute()
    )
    if not link_check.data:
        supabase.table("assessment_modules").insert(
            {
                "assessment_id": assessment_id,
                "module_id": module_id,
                "position": 0,
            }
        ).execute()
    return assessment_id


def main() -> int:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "(check apps/api/.env.local).",
            file=sys.stderr,
        )
        return 2
    if not settings.jwt_signing_secret:
        print("JWT_SIGNING_SECRET must be set.", file=sys.stderr)
        return 2

    supabase = get_supabase()
    admin_id = ensure_admin_user_id(supabase)
    subject_id = ensure_subject(supabase)
    module_id, question_rows = ensure_module(supabase, admin_id)
    assessment_id = ensure_assessment(supabase, admin_id, module_id)

    snapshot = {
        "slug": ASSESSMENT_SLUG,
        "title": "Seed Runners Coverage",
        "description": (
            "Wraps the runners-coverage module so we can drive sql, "
            "notebook, and diagram end-to-end via the candidate flow."
        ),
        "domain": "ops",
        "target_duration_minutes": 20,
        "difficulty": "junior",
        "modules": [
            {
                "module_id": module_id,
                "slug": MODULE_SLUG,
                "title": "Seed runners coverage",
                "description": "Runner-coverage questions.",
                "domain": "ops",
                "difficulty": "junior",
                "target_duration_minutes": 20,
                "position": 0,
            }
        ],
        "questions": [{**q, "module_id": module_id} for q in question_rows],
    }

    expires_at = datetime.now(UTC) + timedelta(days=7)
    assignment_id = str(uuid.uuid4())
    token = issue_candidate_token(
        assignment_id=assignment_id,
        subject_id=subject_id,
        expires_at=expires_at,
    )
    supabase.table("assignments").insert(
        {
            "id": assignment_id,
            "subject_id": subject_id,
            "module_id": module_id,
            "assessment_id": assessment_id,
            "module_snapshot": snapshot,
            "assessment_snapshot": snapshot,
            "created_by": admin_id,
            "token_hash": hash_token(token),
            "expires_at": expires_at.isoformat(),
            "status": "pending",
            "random_seed": secrets.randbits(63),
        }
    ).execute()

    candidate_url = candidate_token_url(
        settings.next_public_candidate_url, token
    )

    print("Runners assignment created.")
    print(f"  assignment_id: {assignment_id}")
    print(f"  subject_id:    {subject_id}")
    print(f"  expires_at:    {expires_at.isoformat()}")
    print()
    print("Magic-link URL:")
    print(f"  {candidate_url}")
    print()
    print(f"  RAW_TOKEN={token}")
    print(f"  ASSIGNMENT_ID={assignment_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
