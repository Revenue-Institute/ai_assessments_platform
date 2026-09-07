"""Backfill partial-attempt evaluations for existing assignments.

Safe to re-run: evaluate_assignment is idempotent and only scores
attempts with a submitted raw_answer.

Usage:
    cd apps/api
    # Prefer queue (rate-limits Anthropic via the worker):
    uv run python scripts/backfill_partial_evaluations.py --limit 25

    # Inline (dev / when Redis is down):
    uv run python scripts/backfill_partial_evaluations.py --limit 10 --inline
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Score inline instead of enqueueing Redis jobs.",
    )
    args = parser.parse_args(argv)

    from ri_assessments_api.db import get_supabase
    from ri_assessments_api.services import queue as queue_service
    from ri_assessments_api.services import scoring as scoring_service

    supabase = get_supabase()
    candidates = scoring_service.list_partial_assignments_for_backfill(
        supabase, limit=args.limit
    )
    if not candidates:
        print("No partial assignments needing evaluation.")
        return 0

    queued = 0
    scored = 0
    errors = 0
    for row in candidates:
        assignment_id = row["id"]
        print(
            f"{assignment_id} status={row['status']} "
            f"answered={row['answered_count']} "
            f"unscored={row['unscored_answered_count']}"
        )
        if not args.inline:
            if queue_service.enqueue_score_assignment(
                assignment_id, allow_partial=True
            ):
                queued += 1
                continue
            print("  redis unavailable; falling back to inline")
        try:
            scoring_service.evaluate_assignment(supabase, assignment_id)
            scored += 1
        except Exception as exc:  # pragma: no cover, operational
            errors += 1
            print(f"  ERROR: {exc}", file=sys.stderr)

    print(f"done queued={queued} scored_inline={scored} errors={errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
