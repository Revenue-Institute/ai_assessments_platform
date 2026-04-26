"""Benchmarking aggregations (spec §11.2 / §11.3).

We pull raw competency_scores rows and aggregate in Python. Cohort sizes
are bounded (50-500 subjects in v1), so the round-trip is fine and we
avoid stored-procedure coupling. Once we outgrow this, push the median
+ heatmap math into Postgres views."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from supabase import Client

from ..models.benchmarks import (
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
) -> CohortHeatmapResponse:
    """Returns the latest score per (subject, competency) for the filter set,
    plus team averages per competency."""

    # 1. Subjects matching the filter.
    subj_q = supabase.table("subjects").select("id, full_name, email, type")
    if subject_type:
        subj_q = subj_q.eq("type", subject_type)
    subjects = subj_q.execute().data or []
    if not subjects:
        return CohortHeatmapResponse(
            subjects=[], competencies=[], cells=[], team_average_pct={}
        )
    subject_ids = [s["id"] for s in subjects]

    # 2. Competency scores within window.
    cs_q = (
        supabase.table("competency_scores")
        .select(
            "subject_id, competency_id, score_pct, assignment_id, "
            "computed_at, competencies(domain)"
        )
        .in_("subject_id", subject_ids)
    )
    if days is not None:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        cs_q = cs_q.gte("computed_at", since)
    rows = cs_q.execute().data or []
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
) -> CompetencyDistributionResponse:
    """Latest score_pct per subject for a single competency, returned with
    summary stats (min / p25 / median / p75 / max). Used by the
    candidate-vs-team overlay (spec §11.3) — caller plots their subject's
    own latest score on top of this distribution."""

    subj_q = supabase.table("subjects").select("id")
    if subject_type:
        subj_q = subj_q.eq("type", subject_type)
    subjects = subj_q.execute().data or []
    subject_ids = [s["id"] for s in subjects if s["id"] != exclude_subject_id]
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
