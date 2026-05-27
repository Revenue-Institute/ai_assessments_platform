"""Benchmarking + series endpoints (spec §11, §14.1)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from supabase import Client

from ..auth import AdminPrincipal, require_admin_jwt, require_role
from ..db import get_supabase
from ..models.benchmarks import (
    CandidateAssignmentDistributionResponse,
    CohortHeatmapResponse,
    CompetencyDistributionResponse,
    SeriesCreateRequest,
    SeriesDetail,
    SeriesIssueNextResponse,
    SeriesSummary,
    SeriesTrendResponse,
    SubjectCompetencyResponse,
    WeakSpotsResponse,
)
from ..services import benchmarks as benchmarks_service
from ..services import series as series_service

# Authentication via require_admin_jwt; per-route role gates are wired below.
# Cohort analytics, heatmaps, weak-spots and series are admin/reviewer surfaces;
# viewers do not get to read cross-subject benchmarks because the data exposes
# every candidate's competency scores in one response (spec §11).
router = APIRouter(tags=["benchmarks"])

_AnalyticsRole = Depends(require_role("admin", "reviewer"))
_AdminOnly = Depends(require_role("admin"))


# Subject competency view ---------------------------------------------------


@router.get(
    "/api/subjects/{subject_id}/competency-scores",
    response_model=SubjectCompetencyResponse,
    dependencies=[_AnalyticsRole],
)
def subject_competency_scores(
    subject_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SubjectCompetencyResponse:
    return benchmarks_service.subject_competency_summary(supabase, subject_id)


# Cohorts -------------------------------------------------------------------


@router.get(
    "/api/cohorts/heatmap",
    response_model=CohortHeatmapResponse,
    dependencies=[_AnalyticsRole],
)
def cohorts_heatmap(
    supabase: Annotated[Client, Depends(get_supabase)],
    type: str | None = Query(default=None, alias="type"),
    domain: str | None = None,
    days: int = Query(default=365, ge=1, le=3650),
    role: str | None = Query(
        default=None,
        description=(
            "Filter subjects by metadata.role_applied_for. Matches the "
            "value stored on subjects.metadata."
        ),
    ),
    start_date: date | None = None,
    end_date: date | None = None,
) -> CohortHeatmapResponse:
    return benchmarks_service.cohort_heatmap(
        supabase,
        subject_type=type,
        domain=domain,
        days=days,
        role=role,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/api/cohorts/weak-spots",
    response_model=WeakSpotsResponse,
    dependencies=[_AnalyticsRole],
)
def cohorts_weak_spots(
    supabase: Annotated[Client, Depends(get_supabase)],
    type: str | None = Query(default=None, alias="type"),
    threshold_pct: float = Query(default=60.0, ge=0, le=100),
) -> WeakSpotsResponse:
    return benchmarks_service.weak_spots(
        supabase, subject_type=type, threshold_pct=threshold_pct
    )


@router.get(
    "/api/cohorts/distribution",
    response_model=CompetencyDistributionResponse,
    dependencies=[_AnalyticsRole],
)
def cohorts_distribution(
    supabase: Annotated[Client, Depends(get_supabase)],
    competency_id: str = Query(min_length=1),
    type: str | None = Query(default=None, alias="type"),
    exclude_subject_id: str | None = None,
    subject_id: str | None = Query(
        default=None,
        description=(
            "When provided, the response carries subject_score_pct and "
            "subject_percentile (peer rank, spec §11.2). The subject is "
            "automatically excluded from the peer cohort."
        ),
    ),
) -> CompetencyDistributionResponse:
    return benchmarks_service.competency_distribution(
        supabase,
        competency_id=competency_id,
        subject_type=type,
        exclude_subject_id=exclude_subject_id,
        subject_id=subject_id,
    )


# Candidate-vs-team overlay (spec §11.3) -----------------------------------


@router.get(
    "/api/candidates/{subject_id}/competency-distribution",
    response_model=CandidateAssignmentDistributionResponse,
    dependencies=[_AnalyticsRole],
)
def candidate_assignment_distribution(
    subject_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
    assignment_id: str = Query(min_length=1),
    type: str | None = Query(default="employee", alias="type"),
) -> CandidateAssignmentDistributionResponse:
    """Returns the per-competency p25 / p50 / p75 distribution plus the
    subject's own score for ONLY the competencies covered by the given
    assignment. Drives the candidate-vs-team overlay on the assignment
    results page (spec §11.3)."""

    return benchmarks_service.assignment_competency_distribution(
        supabase,
        subject_id=subject_id,
        assignment_id=assignment_id,
        subject_type=type,
    )


# Series --------------------------------------------------------------------


@router.get(
    "/api/series",
    response_model=list[SeriesSummary],
    dependencies=[_AnalyticsRole],
)
def list_series(
    supabase: Annotated[Client, Depends(get_supabase)],
) -> list[SeriesSummary]:
    return series_service.list_series(supabase)


@router.post(
    "/api/series",
    response_model=SeriesSummary,
    status_code=201,
    dependencies=[_AdminOnly],
)
def create_series(
    payload: SeriesCreateRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SeriesSummary:
    return series_service.create_series(supabase, principal, payload)


@router.get(
    "/api/series/{series_id}",
    response_model=SeriesDetail,
    dependencies=[_AnalyticsRole],
)
def get_series(
    series_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SeriesDetail:
    return series_service.get_series_detail(supabase, series_id)


@router.get(
    "/api/series/{series_id}/trend",
    response_model=SeriesTrendResponse,
    dependencies=[_AnalyticsRole],
)
def get_series_trend(
    series_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SeriesTrendResponse:
    """Per-competency score timeline across the series, ordered by
    sequence_number (spec §11.4). Frontend renders one trend line per
    competency on the series detail page."""

    return series_service.get_series_trend(supabase, series_id)


@router.post(
    "/api/series/{series_id}/assignments/{assignment_id}",
    response_model=SeriesDetail,
    dependencies=[_AdminOnly],
)
def attach_assignment(
    series_id: str,
    assignment_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SeriesDetail:
    return series_service.link_assignment(
        supabase, principal, series_id=series_id, assignment_id=assignment_id
    )


@router.post(
    "/api/series/{series_id}/issue-next",
    response_model=SeriesIssueNextResponse,
    dependencies=[_AdminOnly],
)
def issue_next(
    series_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
    expires_in_days: int = Query(default=7, ge=1, le=14),
    send_email: bool = Query(default=True),
) -> SeriesIssueNextResponse:
    result = series_service.issue_next_for_series(
        supabase,
        principal,
        series_id=series_id,
        expires_in_days=expires_in_days,
        send_email=send_email,
    )
    return SeriesIssueNextResponse(**result)


@router.post("/api/series/dispatch-due", dependencies=[_AdminOnly])
def dispatch_due(
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
    expires_in_days: int = Query(default=7, ge=1, le=14),
    send_email: bool = Query(default=True),
) -> dict:
    """Walks every series with next_due_at <= now and issues the next
    assignment for each. Designed for a Cloud Scheduler cron, idempotent
    and partial-failure tolerant."""

    return series_service.dispatch_due_series(
        supabase,
        principal,
        expires_in_days=expires_in_days,
        send_email=send_email,
    )
