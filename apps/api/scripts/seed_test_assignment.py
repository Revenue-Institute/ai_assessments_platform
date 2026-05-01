"""Creates a minimal test assignment and prints a magic-link URL.

Idempotent on the test admin + subject; always creates a fresh assignment
+ token so each run produces a usable link. For local dev only.

Usage:
    cd apps/api
    uv run python scripts/seed_test_assignment.py
"""

from __future__ import annotations

import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure src/ is on the path so we can import the package without installing.
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

import os

TEST_ADMIN_EMAIL = os.environ.get(
    "SEED_ADMIN_EMAIL", "seed-admin@revenueinstitute.local"
)
TEST_ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD")
TEST_SUBJECT_EMAIL = "seed-candidate@revenueinstitute.local"


def ensure_admin_user(supabase) -> str:
    """Make sure an admin auth.user + public.users row exists. Returns the UUID.

    If SEED_ADMIN_PASSWORD is set, the auth user is created or updated to
    use it; otherwise a random password is set on first creation."""

    password = TEST_ADMIN_PASSWORD or secrets.token_urlsafe(24)

    # See if a public.users row already exists for the test admin.
    existing = (
        supabase.table("users")
        .select("id")
        .eq("email", TEST_ADMIN_EMAIL)
        .limit(1)
        .execute()
    )
    if existing.data:
        auth_id = existing.data[0]["id"]
        # Reset password if the operator passed one explicitly.
        if TEST_ADMIN_PASSWORD:
            supabase.auth.admin.update_user_by_id(
                auth_id, {"password": TEST_ADMIN_PASSWORD, "email_confirm": True}
            )
        return auth_id

    # Try to create the auth user; if it already exists, fetch by email.
    try:
        created = supabase.auth.admin.create_user(
            {
                "email": TEST_ADMIN_EMAIL,
                "password": password,
                "email_confirm": True,
            }
        )
        auth_id = created.user.id  # type: ignore[union-attr]
    except Exception as exc:  # already exists or RLS error
        # Fall back to listing users and matching email.
        listing = supabase.auth.admin.list_users()
        match = next(
            (
                u
                for u in listing  # type: ignore[union-attr]
                if getattr(u, "email", None) == TEST_ADMIN_EMAIL
            ),
            None,
        )
        if not match:
            raise RuntimeError(
                f"Could not create or find test admin: {exc}"
            ) from exc
        auth_id = match.id
        if TEST_ADMIN_PASSWORD:
            supabase.auth.admin.update_user_by_id(
                auth_id, {"password": TEST_ADMIN_PASSWORD, "email_confirm": True}
            )

    supabase.table("users").upsert(
        {
            "id": auth_id,
            "email": TEST_ADMIN_EMAIL,
            "full_name": "Seed Admin",
            "role": "admin",
        }
    ).execute()

    return auth_id


def ensure_subject(supabase) -> str:
    existing = (
        supabase.table("subjects")
        .select("id")
        .eq("email", TEST_SUBJECT_EMAIL)
        .eq("type", "candidate")
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = (
        supabase.table("subjects")
        .insert(
            {
                "type": "candidate",
                "full_name": "Seed Candidate",
                "email": TEST_SUBJECT_EMAIL,
                "metadata": {"role_applied_for": "Seed test"},
            }
        )
        .execute()
    )
    return inserted.data[0]["id"]


SEED_MODULE_SLUG = "seed-mixed-smoke"
SEED_MODULE_VERSION = 1


def _seed_questions() -> list[dict]:
    """Question templates covering mcq + short + long + code, with one
    MCQ that uses sampled variables and a Python code question that
    exercises the E2B runner. IDs are generated at insert time by the
    DB so they line up with the FK on attempts.question_template_id."""

    return [
            {
                "type": "mcq",
                "prompt_template": "What does RI stand for in this platform?",
                "variable_schema": {},
                "rubric": {
                    "version": "1",
                    "scoring_mode": "exact_match",
                    "criteria": [
                        {
                            "id": "answer",
                            "label": "Correct answer",
                            "weight": 1.0,
                            "description": "Selects the correct option.",
                            "scoring_guidance": "Only 'Revenue Institute' is correct.",
                        }
                    ],
                },
                "competency_tags": ["ops.process_design"],
                "max_points": 10,
                "difficulty": "junior",
                "interactive_config": {
                    "options": [
                        "Revenue Institute",
                        "Recurring Income",
                        "Real Index",
                        "Random Item",
                    ],
                    "correct_index": 0,
                },
            },
            {
                "type": "short_answer",
                "prompt_template": (
                    "In one sentence, name a HubSpot workflow trigger you would use "
                    "to enroll a contact when their lifecycle stage becomes "
                    "Marketing Qualified Lead."
                ),
                "variable_schema": {},
                "rubric": {
                    "version": "1",
                    "scoring_mode": "rubric_ai",
                    "criteria": [
                        {
                            "id": "trigger",
                            "label": "Names a valid trigger",
                            "weight": 1.0,
                            "description": "References a property-based trigger on lifecycle stage.",
                            "scoring_guidance": "Accept 'lifecycle stage is any of MQL', 'contact property change', etc.",
                        }
                    ],
                },
                "competency_tags": ["hubspot.workflows"],
                "max_points": 10,
                "difficulty": "junior",
            },
            {
                "type": "long_answer",
                "prompt_template": (
                    "Describe how you would design a re-engagement sequence for "
                    "contacts who have been inactive for 90 days. Cover: entry "
                    "criteria, branching, exit criteria, and one risk you would "
                    "monitor."
                ),
                "variable_schema": {},
                "rubric": {
                    "version": "1",
                    "scoring_mode": "rubric_ai",
                    "criteria": [
                        {
                            "id": "structure",
                            "label": "Covers all four elements",
                            "weight": 0.5,
                            "description": "Entry, branching, exit, risk all addressed.",
                            "scoring_guidance": "Penalize answers that only describe one or two elements.",
                        },
                        {
                            "id": "judgment",
                            "label": "Operational judgment",
                            "weight": 0.5,
                            "description": "Risk awareness and exit criteria are concrete.",
                            "scoring_guidance": "Reward specific risks (suppression overlap, deliverability).",
                        },
                    ],
                },
                "competency_tags": ["marketing.content", "hubspot.workflows"],
                "max_points": 20,
                "difficulty": "mid",
            },
            {
                "type": "mcq",
                "prompt_template": (
                    "A SaaS company has ${{ revenue }} in ARR and is growing "
                    "{{ growth_rate * 100 }}% YoY. Which growth motion is the "
                    "most appropriate next investment?"
                ),
                "variable_schema": {
                    "revenue": {
                        "kind": "int",
                        "min": 5_000_000,
                        "max": 25_000_000,
                        "step": 1_000_000,
                    },
                    "growth_rate": {
                        "kind": "float",
                        "min": 0.10,
                        "max": 0.45,
                        "decimals": 2,
                    },
                },
                "rubric": {
                    "version": "1",
                    "scoring_mode": "rubric_ai",
                    "criteria": [
                        {
                            "id": "fit",
                            "label": "Motion fits the size + growth profile",
                            "weight": 1.0,
                            "description": "Justification matches stage and capacity.",
                            "scoring_guidance": "No single right answer; reward reasoning.",
                        }
                    ],
                },
                "competency_tags": ["sales.pipeline_management"],
                "max_points": 10,
                "difficulty": "senior",
                "interactive_config": {
                    "options": [
                        "Hire a partnerships lead and build a co-sell motion",
                        "Double the SDR team and add an outbound playbook",
                        "Invest in a self-serve PLG funnel for SMB",
                        "Launch enterprise security certifications and ABM",
                    ],
                },
            },
            {
                "type": "code",
                "prompt_template": (
                    "Implement `total(prices)` that returns the sum of a list "
                    "of numeric prices, rounded to 2 decimal places. Returning "
                    "0 for an empty list is required."
                ),
                "variable_schema": {},
                "rubric": {
                    "version": "1",
                    "scoring_mode": "test_cases",
                    "criteria": [
                        {
                            "id": "correctness",
                            "label": "Hidden tests pass",
                            "weight": 1.0,
                            "description": "All hidden tests must pass.",
                            "scoring_guidance": "Score = passed / total * max_points",
                        }
                    ],
                },
                "competency_tags": ["engineering.python"],
                "max_points": 20,
                "difficulty": "junior",
                "interactive_config": {
                    "language": "python",
                    "starter_code": (
                        "def total(prices):\n"
                        "    # TODO: return the sum of prices, rounded to 2 decimals.\n"
                        "    return 0\n"
                    ),
                    "visible_tests": (
                        "from solution import total\n"
                        "\n"
                        "def test_basic():\n"
                        "    assert total([1, 2, 3]) == 6\n"
                        "\n"
                        "def test_empty():\n"
                        "    assert total([]) == 0\n"
                    ),
                    "hidden_tests": (
                        "from solution import total\n"
                        "\n"
                        "def test_empty():\n"
                        "    assert total([]) == 0\n"
                        "\n"
                        "def test_single():\n"
                        "    assert total([10.0]) == 10.0\n"
                        "\n"
                        "def test_multi():\n"
                        "    assert total([1.5, 2.5, 3.0]) == 7.0\n"
                        "\n"
                        "def test_rounding():\n"
                        "    assert total([0.1, 0.2]) == 0.3\n"
                        "\n"
                        "def test_negatives():\n"
                        "    assert total([5, -2.5]) == 2.5\n"
                    ),
                    "allow_internet": False,
                    "packages": [],
                    "time_limit_exec_ms": 15000,
                },
            },
    ]


def ensure_module(supabase, admin_id: str) -> tuple[str, list[dict]]:
    """Upsert the seed module and its question_templates. Returns
    (module_id, question_template_rows) where the rows include real ids
    and positions; those rows are what the snapshot is built from."""

    existing_module = (
        supabase.table("modules")
        .select("id")
        .eq("slug", SEED_MODULE_SLUG)
        .eq("version", SEED_MODULE_VERSION)
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
                    "slug": SEED_MODULE_SLUG,
                    "title": "Seed smoke test",
                    "description": (
                        "A five-question assessment used to verify the "
                        "candidate flow end-to-end (mcq, short, long, mcq with "
                        "sampled variables, code). Not for real evaluation."
                    ),
                    "domain": "ops",
                    "target_duration_minutes": 15,
                    "difficulty": "junior",
                    "status": "published",
                    "version": SEED_MODULE_VERSION,
                    "created_by": admin_id,
                    "published_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )
        module_id = inserted.data[0]["id"]

    # Reuse existing templates if the seed already ran; otherwise insert
    # the canonical set. We don't delete templates that may already be
    # referenced by existing attempts.
    existing_templates = (
        supabase.table("question_templates")
        .select(
            "id, module_id, position, type, prompt_template, variable_schema, "
            "solver_code, solver_language, interactive_config, rubric, "
            "competency_tags, time_limit_seconds, max_points, metadata"
        )
        .eq("module_id", module_id)
        .order("position")
        .execute()
    )
    if existing_templates.data:
        return module_id, existing_templates.data

    rows: list[dict] = []
    for position, q in enumerate(_seed_questions()):
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
            "metadata": {"difficulty": q.get("difficulty", "junior")},
        }
        inserted = supabase.table("question_templates").insert(row).execute()
        rows.append(inserted.data[0])

    return module_id, rows


def build_module_snapshot(module_id: str, question_rows: list[dict]) -> dict:
    return {
        "slug": SEED_MODULE_SLUG,
        "title": "Seed smoke test",
        "description": (
            "A five-question assessment used to verify the candidate flow "
            "end-to-end (mcq, short, long, mcq with sampled variables, code). "
            "Not for real evaluation."
        ),
        "domain": "ops",
        "target_duration_minutes": 15,
        "difficulty": "junior",
        "questions": question_rows,
    }


def ensure_assessment(supabase, admin_id: str, module_id: str) -> str:
    """Wrap the seed module in a published Assessment so the assignment can
    bind to the new container model."""

    existing = (
        supabase.table("assessments")
        .select("id")
        .eq("slug", SEED_MODULE_SLUG)
        .limit(1)
        .execute()
    )
    title = "Seed Smoke Assessment"
    description = (
        "One module wrapping the seed smoke test. Verifies the "
        "candidate flow, scoring, and admin views end-to-end."
    )
    if existing.data:
        assessment_id = existing.data[0]["id"]
        # Normalize the title in case the migration auto-created this one
        # off the module title (which read "Seed smoke test").
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
                    "slug": SEED_MODULE_SLUG,
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

    # Idempotent module-link.
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

    admin_id = ensure_admin_user(supabase)
    subject_id = ensure_subject(supabase)
    module_id, question_rows = ensure_module(supabase, admin_id)
    assessment_id = ensure_assessment(supabase, admin_id, module_id)
    snapshot = build_module_snapshot(module_id, question_rows)
    # Wrap as an assessment_snapshot so new code paths read it correctly,
    # while keeping the same flat questions list the candidate flow expects.
    snapshot_with_assessment = {
        **snapshot,
        "title": "Seed Smoke Assessment",
        "modules": [
            {
                "module_id": module_id,
                "slug": SEED_MODULE_SLUG,
                "title": snapshot["title"],
                "description": snapshot["description"],
                "domain": snapshot["domain"],
                "difficulty": snapshot["difficulty"],
                "target_duration_minutes": snapshot["target_duration_minutes"],
                "position": 0,
            }
        ],
        "questions": [
            {**q, "module_id": module_id} for q in snapshot["questions"]
        ],
    }

    expires_at = datetime.now(UTC) + timedelta(days=7)
    assignment_id = str(uuid.uuid4())

    token = issue_candidate_token(
        assignment_id=assignment_id,
        subject_id=subject_id,
        expires_at=expires_at,
    )
    token_hash = hash_token(token)

    supabase.table("assignments").insert(
        {
            "id": assignment_id,
            "subject_id": subject_id,
            "module_id": module_id,
            "assessment_id": assessment_id,
            "module_snapshot": snapshot_with_assessment,
            "assessment_snapshot": snapshot_with_assessment,
            "created_by": admin_id,
            "token_hash": token_hash,
            "expires_at": expires_at.isoformat(),
            "status": "pending",
            "random_seed": secrets.randbits(63),
        }
    ).execute()

    candidate_url = candidate_token_url(settings.next_public_candidate_url, token)

    print("Seed assignment created.")
    print(f"  assignment_id: {assignment_id}")
    print(f"  subject_id:    {subject_id}")
    print(f"  expires_at:    {expires_at.isoformat()}")
    print()
    print("Magic-link URL:")
    print(f"  {candidate_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
