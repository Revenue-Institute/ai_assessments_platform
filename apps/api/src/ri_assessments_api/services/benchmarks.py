"""Benchmarking aggregations (spec §11.2 / §11.3).

We pull raw competency_scores rows and aggregate in Python. Cohort sizes
are bounded (50-500 subjects in v1), so the round-trip is fine and we
avoid stored-procedure coupling. Once we outgrow this, push the median
+ heatmap math into Postgres views."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any

from supabase import Client

from ..models.benchmarks import (
    AssignmentCompetencyDistribution,
    CandidateAssignmentDistributionResponse,
    CohortHeatmapCell,
    CohortHeatmapResponse,
    CohortSubject,
    CompetencyDistributionResponse,
    CompetencyScorePoint,
    SubjectCompetencyResponse,
    SubjectCompetencyTrend,
    WeakSpot,
    WeakSpotsResponse,
)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# -- Subject view -----------------------------------------------------------


def subject_competency_summary(
    supabase: Client, subject_id: str
) -> SubjectCompetencyResponse:
    res = (
        supabase.table("competency_scores")
        .select(
            "competency_id, score_pct, point_total, point_possible, "
            "assignment_id, computed_at"
        )
        .eq("subject_id", subject_id)
        .order("computed_at")
        .execute()
    )
    rows = res.data or []

    # Group by competency_id, preserving chronological order per group.
    by_comp: dict[str, list[CompetencyScorePoint]] = {}
    for row in rows:
        point = CompetencyScorePoint(
            competency_id=row["competency_id"],
            score_pct=float(row["score_pct"]),
            point_total=float(row["point_total"]),
            point_possible=float(row["point_possible"]),
            assignment_id=row["assignment_id"],
            computed_at=_parse_ts(row["computed_at"]),
        )
        by_comp.setdefault(row["competency_id"], []).append(point)

    trends: list[SubjectCompetencyTrend] = []
    for comp_id, points in sorted(by_comp.items()):
        latest = points[-1]
        delta = (
            latest.score_pct - points[-2].score_pct if len(points) >= 2 else None
        )
        trends.append(
            SubjectCompetencyTrend(
                competency_id=comp_id,
                points=points,
                latest_score_pct=latest.score_pct,
                delta_vs_previous=round(delta, 2) if delta is not None else None,
            )
        )

    return SubjectCompetencyResponse(subject_id=subject_id, trends=trends)


# -- Cohort heatmap ---------------------------------------------------------


def cohort_heatmap(
    supabase: Client,
    *,
    subject_type: str | None = None,
    domain: str | None = None,
    days: int | None = 365,
    role: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> CohortHeatmapResponse:
    """Returns the latest score per (subject, competency) for the filter set,
    plus team averages per competency.

    Spec §11.2 filters:
    - type: candidate / employee
    - domain: competencies.domain
    - role: matched against subjects.metadata->>'role_applied_for'
    - date range: explicit start_date / end_date filter assignments by
      `completed_at`. When neither bound is supplied, the legacy `days`
      rolling window is applied to competency_scores.computed_at for
      backwards compatibility with existing callers."""

    use_explicit_range = start_date is not None or end_date is not None

    # 1. Subjects matching the filter.
    subj_q = supabase.table("subjects").select(
        "id, full_name, email, type, metadata"
    )
    if subject_type:
        subj_q = subj_q.eq("type", subject_type)
    subjects = subj_q.execute().data or []

    # Filter by role (subjects.metadata->>'role_applied_for'). supabase-py
    # doesn't expose a fluent JSON path helper, so we filter in-Python.
    # Cohort sizes are bounded (spec §18: 50 concurrent target), so this
    # is fine for v1.
    if role:
        subjects = [
            s
            for s in subjects
            if (s.get("metadata") or {}).get("role_applied_for") == role
        ]

    if not subjects:
        return CohortHeatmapResponse(
            subjects=[], competencies=[], cells=[], team_average_pct={}
        )
    subject_ids = [s["id"] for s in subjects]

    # 2. Competency scores. When a date range was supplied, scope by the
    # assignment's completed_at instead of computed_at: assignments are
    # what HR actually filters on ("show me everyone who completed
    # between Q1 dates"), and computed_at is just when the rollup row
    # was upserted.
    assignment_id_whitelist: set[str] | None = None
    if use_explicit_range:
        a_q = (
            supabase.table("assignments")
            .select("id, completed_at")
            .in_("subject_id", subject_ids)
            .eq("status", "completed")
        )
        if start_date is not None:
            a_q = a_q.gte("completed_at", start_date.isoformat())
        if end_date is not None:
            # Inclusive end-of-day so end_date='2026-04-30' captures
            # assignments completed any time that day.
            end_dt = datetime.combine(
                end_date, datetime.max.time(), tzinfo=UTC
            )
            a_q = a_q.lte("completed_at", end_dt.isoformat())
        assignment_rows = a_q.execute().data or []
        assignment_id_whitelist = {
            r["id"] for r in assignment_rows if r.get("completed_at")
        }
        if not assignment_id_whitelist:
            return CohortHeatmapResponse(
                subjects=[], competencies=[], cells=[], team_average_pct={}
            )

    cs_q = (
        supabase.table("competency_scores")
        .select(
            "subject_id, competency_id, score_pct, assignment_id, "
            "computed_at, competencies(domain)"
        )
        .in_("subject_id", subject_ids)
    )
    if not use_explicit_range and days is not None:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        cs_q = cs_q.gte("computed_at", since)
    rows = cs_q.execute().data or []
    if assignment_id_whitelist is not None:
        rows = [
            r for r in rows if r.get("assignment_id") in assignment_id_whitelist
        ]
    if domain:
        rows = [
            r for r in rows
            if (r.get("competencies") or {}).get("domain") == domain
        ]

    # 3. Pick latest per (subject, competency).
    latest_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["subject_id"], r["competency_id"])
        existing = latest_by_key.get(key)
        if existing is None or _parse_ts(r["computed_at"]) > _parse_ts(
            existing["computed_at"]
        ):
            latest_by_key[key] = r

    cells = [
        CohortHeatmapCell(
            subject_id=r["subject_id"],
            competency_id=r["competency_id"],
            score_pct=float(r["score_pct"]),
            assignment_id=r["assignment_id"],
            computed_at=_parse_ts(r["computed_at"]),
        )
        for r in latest_by_key.values()
    ]

    competencies = sorted({c.competency_id for c in cells})
    team_average: dict[str, float] = {}
    for comp_id in competencies:
        scores = [c.score_pct for c in cells if c.competency_id == comp_id]
        team_average[comp_id] = round(sum(scores) / len(scores), 2) if scores else 0.0

    # Drop subjects that have no scores within the filter window so the
    # heatmap doesn't render empty rows.
    seen_subject_ids = {c.subject_id for c in cells}
    visible_subjects = [
        CohortSubject(
            id=s["id"],
            full_name=s["full_name"],
            email=s["email"],
            type=s["type"],
        )
        for s in subjects
        if s["id"] in seen_subject_ids
    ]

    return CohortHeatmapResponse(
        subjects=visible_subjects,
        competencies=competencies,
        cells=cells,
        team_average_pct=team_average,
    )


# -- Weak spots -------------------------------------------------------------


def weak_spots(
    supabase: Client,
    *,
    subject_type: str | None = None,
    threshold_pct: float = 60.0,
) -> WeakSpotsResponse:
    """Competencies whose median score across the filtered cohort sits below
    the threshold (spec §11.2 'weak-spot detection')."""

    subj_q = supabase.table("subjects").select("id")
    if subject_type:
        subj_q = subj_q.eq("type", subject_type)
    subjects = subj_q.execute().data or []
    subject_ids = [s["id"] for s in subjects]
    if not subject_ids:
        return WeakSpotsResponse(threshold_pct=threshold_pct, weak_spots=[])

    rows = (
        supabase.table("competency_scores")
        .select("competency_id, score_pct, subject_id, computed_at")
        .in_("subject_id", subject_ids)
        .execute()
    ).data or []

    # Latest per (subject, competency).
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["subject_id"], r["competency_id"])
        existing = latest.get(key)
        if existing is None or _parse_ts(r["computed_at"]) > _parse_ts(
            existing["computed_at"]
        ):
            latest[key] = r

    by_comp: dict[str, list[float]] = {}
    for r in latest.values():
        by_comp.setdefault(r["competency_id"], []).append(float(r["score_pct"]))

    out: list[WeakSpot] = []
    for comp_id, scores in by_comp.items():
        if not scores:
            continue
        med = median(scores)
        if med < threshold_pct:
            out.append(
                WeakSpot(
                    competency_id=comp_id,
                    median_pct=round(med, 2),
                    sample_size=len(scores),
                )
            )
    out.sort(key=lambda w: w.median_pct)
    return WeakSpotsResponse(threshold_pct=threshold_pct, weak_spots=out)


def competency_distribution(
    supabase: Client,
    *,
    competency_id: str,
    subject_type: str | None = None,
    exclude_subject_id: str | None = None,
    subject_id: str | None = None,
) -> CompetencyDistributionResponse:
    """Latest score_pct per subject for a single competency, returned with
    summary stats (min / p25 / median / p75 / max). Used by the
    candidate-vs-team overlay (spec §11.3), caller plots their subject's
    own latest score on top of this distribution.

    Spec §11.2 'peer percentile per subject per competency': when
    `subject_id` is provided, the response includes the subject's own
    latest score_pct and their percentile rank within the peer set
    (subjects matching subject_type, with the queried subject excluded
    from the peer cohort)."""

    subj_q = supabase.table("subjects").select("id")
    if subject_type:
        subj_q = subj_q.eq("type", subject_type)
    subjects = subj_q.execute().data or []

    # Pull the queried subject's latest score first so the peer cohort can
    # always exclude them (avoids the subject pulling their own percentile
    # toward 50). `exclude_subject_id` stays around for the legacy
    # candidate-vs-team-without-self-aware-percentile callers.
    subject_score: float | None = None
    if subject_id:
        my_rows = (
            supabase.table("competency_scores")
            .select("score_pct, computed_at")
            .eq("competency_id", competency_id)
            .eq("subject_id", subject_id)
            .order("computed_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        if my_rows:
            subject_score = float(my_rows[0]["score_pct"])

    excluded_ids = {x for x in (exclude_subject_id, subject_id) if x}
    subject_ids = [s["id"] for s in subjects if s["id"] not in excluded_ids]

    if not subject_ids:
        return CompetencyDistributionResponse(
            competency_id=competency_id,
            sample_size=0,
            min_pct=0,
            p25_pct=0,
            median_pct=0,
            p75_pct=0,
            max_pct=0,
            values=[],
            subject_score_pct=subject_score,
            subject_percentile=None,
        )

    rows = (
        supabase.table("competency_scores")
        .select("subject_id, score_pct, computed_at")
        .eq("competency_id", competency_id)
        .in_("subject_id", subject_ids)
        .execute()
    ).data or []

    latest_by_subject: dict[str, dict[str, Any]] = {}
    for r in rows:
        existing = latest_by_subject.get(r["subject_id"])
        if existing is None or _parse_ts(r["computed_at"]) > _parse_ts(
            existing["computed_at"]
        ):
            latest_by_subject[r["subject_id"]] = r

    values = sorted(float(r["score_pct"]) for r in latest_by_subject.values())
    if not values:
        return CompetencyDistributionResponse(
            competency_id=competency_id,
            sample_size=0,
            min_pct=0,
            p25_pct=0,
            median_pct=0,
            p75_pct=0,
            max_pct=0,
            values=[],
            subject_score_pct=subject_score,
            subject_percentile=None,
        )

    return CompetencyDistributionResponse(
        competency_id=competency_id,
        sample_size=len(values),
        min_pct=round(values[0], 2),
        p25_pct=round(_quantile(values, 0.25), 2),
        median_pct=round(_quantile(values, 0.5), 2),
        p75_pct=round(_quantile(values, 0.75), 2),
        max_pct=round(values[-1], 2),
        values=values,
        subject_score_pct=subject_score,
        subject_percentile=(
            _percentile_rank(values, subject_score)
            if subject_score is not None
            else None
        ),
    )


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation quantile on a pre-sorted list."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    idx = (n - 1) * q
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def _percentile_rank(sorted_values: list[float], value: float) -> float:
    """Percentile rank (0 to 100) of `value` within `sorted_values`.

    Uses numpy when available for exact tie-handling; otherwise falls
    back to the standard rank/total formulation (count of peers strictly
    below + half of peers equal, divided by total). Returns 0 when the
    peer set is empty."""

    if not sorted_values:
        return 0.0
    try:
        import numpy as np  # type: ignore[import-not-found]

        arr = np.asarray(sorted_values, dtype=float)
        below = float(np.sum(arr < value))
        equal = float(np.sum(arr == value))
        rank = (below + 0.5 * equal) / float(len(arr))
        return round(rank * 100.0, 2)
    except Exception:
        n = len(sorted_values)
        below = sum(1 for v in sorted_values if v < value)
        equal = sum(1 for v in sorted_values if v == value)
        rank = (below + 0.5 * equal) / float(n)
        return round(rank * 100.0, 2)


def assignment_competency_distribution(
    supabase: Client,
    *,
    subject_id: str,
    assignment_id: str,
    subject_type: str | None = None,
) -> CandidateAssignmentDistributionResponse:
    """Per-competency distribution for ONLY the competencies covered by
    `assignment_id` (spec §11.3 candidate-vs-team overlay on the
    assignment results page).

    Returns one AssignmentCompetencyDistribution per competency present
    on this assignment's competency_scores rows. Peer cohort excludes the
    queried subject so they don't pull their own percentile."""

    # 1. Discover which competencies this assignment scored on, plus the
    # subject's own score_pct per competency. Same query covers both.
    own_rows = (
        supabase.table("competency_scores")
        .select(
            "competency_id, score_pct, point_total, point_possible, computed_at"
        )
        .eq("assignment_id", assignment_id)
        .eq("subject_id", subject_id)
        .execute()
    ).data or []

    if not own_rows:
        return CandidateAssignmentDistributionResponse(
            subject_id=subject_id,
            assignment_id=assignment_id,
            distributions=[],
        )

    own_by_comp: dict[str, float] = {
        r["competency_id"]: float(r["score_pct"]) for r in own_rows
    }

    # 2. Build the peer cohort: subjects of the configured type, minus
    # the queried subject. Reused for every competency below.
    subj_q = supabase.table("subjects").select("id")
    if subject_type:
        subj_q = subj_q.eq("type", subject_type)
    subjects = subj_q.execute().data or []
    peer_ids = [s["id"] for s in subjects if s["id"] != subject_id]

    distributions: list[AssignmentCompetencyDistribution] = []
    for competency_id, subject_score in own_by_comp.items():
        if not peer_ids:
            distributions.append(
                AssignmentCompetencyDistribution(
                    competency_id=competency_id,
                    sample_size=0,
                    min_pct=0,
                    p25_pct=0,
                    median_pct=0,
                    p75_pct=0,
                    max_pct=0,
                    subject_score_pct=subject_score,
                    subject_percentile=None,
                )
            )
            continue

        peer_rows = (
            supabase.table("competency_scores")
            .select("subject_id, score_pct, computed_at")
            .eq("competency_id", competency_id)
            .in_("subject_id", peer_ids)
            .execute()
        ).data or []
        latest_by_subject: dict[str, dict[str, Any]] = {}
        for r in peer_rows:
            existing = latest_by_subject.get(r["subject_id"])
            if existing is None or _parse_ts(r["computed_at"]) > _parse_ts(
                existing["computed_at"]
            ):
                latest_by_subject[r["subject_id"]] = r

        values = sorted(
            float(r["score_pct"]) for r in latest_by_subject.values()
        )
        if not values:
            distributions.append(
                AssignmentCompetencyDistribution(
                    competency_id=competency_id,
                    sample_size=0,
                    min_pct=0,
                    p25_pct=0,
                    median_pct=0,
                    p75_pct=0,
                    max_pct=0,
                    subject_score_pct=subject_score,
                    subject_percentile=None,
                )
            )
            continue

        distributions.append(
            AssignmentCompetencyDistribution(
                competency_id=competency_id,
                sample_size=len(values),
                min_pct=round(values[0], 2),
                p25_pct=round(_quantile(values, 0.25), 2),
                median_pct=round(_quantile(values, 0.5), 2),
                p75_pct=round(_quantile(values, 0.75), 2),
                max_pct=round(values[-1], 2),
                subject_score_pct=subject_score,
                subject_percentile=_percentile_rank(values, subject_score),
            )
        )

    distributions.sort(key=lambda d: d.competency_id)
    return CandidateAssignmentDistributionResponse(
        subject_id=subject_id,
        assignment_id=assignment_id,
        distributions=distributions,
    )
