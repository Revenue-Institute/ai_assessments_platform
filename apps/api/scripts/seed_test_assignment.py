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

from ri_assessments_api.config import get_settings  # noqa: E402
from ri_assessments_api.db import get_supabase  # noqa: E402
from ri_assessments_api.services.tokens import (  # noqa: E402
    candidate_token_url,
    hash_token,
)
from ri_assessments_api.auth import issue_candidate_token  # noqa: E402

TEST_ADMIN_EMAIL = "seed-admin@revenueinstitute.local"
TEST_SUBJECT_EMAIL = "seed-candidate@revenueinstitute.local"


def ensure_admin_user(supabase) -> str:
    """Make sure an admin auth.user + public.users row exists. Returns the UUID."""

    # See if a public.users row already exists for the test admin.
    existing = (
        supabase.table("users")
        .select("id")
        .eq("email", TEST_ADMIN_EMAIL)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    # Try to create the auth user; if it already exists, fetch by email.
    try:
        created = supabase.auth.admin.create_user(
            {
                "email": TEST_ADMIN_EMAIL,
                "password": secrets.token_urlsafe(24),
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


def build_module_snapshot() -> dict:
    """Minimal module shape sufficient for the consent screen + a single MCQ.

    The candidate UI only needs title/description/duration/questions for v1;
    full QuestionTemplate fidelity ships once randomizer + renderer are wired."""
    return {
        "slug": "seed-mcq-smoke",
        "title": "Seed smoke test",
        "description": (
            "A one-question assessment used to verify the candidate flow "
            "end-to-end. Not for real evaluation."
        ),
        "domain": "ops",
        "target_duration_minutes": 5,
        "difficulty": "junior",
        "questions": [
            {
                "id": str(uuid.uuid4()),
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
            }
        ],
    }


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
    snapshot = build_module_snapshot()

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
            "module_snapshot": snapshot,
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
