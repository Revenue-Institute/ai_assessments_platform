"""Benchmarking + series endpoints (spec §11, §14.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from supabase import Client

from ..auth import AdminPrincipal, require_admin_jwt
from ..db import get_supabase
from ..models.benchmarks import (
    CohortHeatmapResponse,
    CompetencyDistributionResponse,
    SeriesCreateRequest,
    SeriesDetail,
    SeriesIssueNextResponse,
    SeriesSummary,
    SubjectCompetencyResponse,
    WeakSpotsResponse,
)
from ..services import benchmarks as benchmarks_service
from ..services import series as series_service

router = APIRouter(tags=["benchmarks"], dependencies=[Depends(require_admin_jwt)])


# Subject competency view ---------------------------------------------------


@router.get(
    "/api/subjects/{subject_id}/competency-scores",
    response_model=SubjectCompetencyResponse,
)
def subject_competency_scores(
    subject_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SubjectCompetencyResponse:
    return benchmarks_service.subject_competency_summary(supabase, subject_id)


# Cohorts -------------------------------------------------------------------


@router.get("/api/cohorts/heatmap", response_model=CohortHeatmapResponse)
def cohorts_heatmap(
    supabase: Annotated[Client, Depends(get_supabase)],
    type: str | None = Query(default=None, alias="type"),
    domain: str | None = None,
    days: int = Query(default=365, ge=1, le=3650),
) -> CohortHeatmapResponse:
    return benchmarks_service.cohort_heatmap(
        supabase, subject_type=type, domain=domain, days=days
    )


@router.get("/api/cohorts/weak-spots", response_model=WeakSpotsResponse)
def cohorts_weak_spots(
    supabase: Annotated[Client, Depends(get_supabase)],
    type: str | None = Query(default=None, alias="type"),
    threshold_pct: float = Query(default=60.0, ge=0, le=100),
) -> WeakSpotsResponse:
    return benchmarks_service.weak_spots(
        supabase, subject_type=type, threshold_pct=threshold_pct
    )


@router.get(
    "/api/cohorts/distribution", response_model=CompetencyDistributionResponse
)
def cohorts_distribution(
    supabase: Annotated[Client, Depends(get_supabase)],
    competency_id: str = Query(min_length=1),
    type: str | None = Query(default=None, alias="type"),
    exclude_subject_id: str | None = None,
) -> CompetencyDistributionResponse:
    return benchmarks_service.competency_distribution(
        supabase,
        competency_id=competency_id,
        subject_type=type,
        exclude_subject_id=exclude_subject_id,
    )


# Series --------------------------------------------------------------------


@router.get("/api/series", response_model=list[SeriesSummary])
def list_series(
    supabase: Annotated[Client, Depends(get_supabase)],
) -> list[SeriesSummary]:
    return series_service.list_series(supabase)


@router.post("/api/series", response_model=SeriesSummary, status_code=201)
def create_series(
    payload: SeriesCreateRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SeriesSummary:
    return series_service.create_series(supabase, principal, payload)


@router.get("/api/series/{series_id}", response_model=SeriesDetail)
def get_series(
    series_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SeriesDetail:
    return series_service.get_series_detail(supabase, series_id)


@router.post(
    "/api/series/{series_id}/assignments/{assignment_id}",
    response_model=SeriesDetail,
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
)
def issue_next(
    series_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
    expires_in_days: int = Query(default=7, ge=1, le=90),
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


@router.post("/api/series/dispatch-due")
def dispatch_due(
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
    expires_in_days: int = Query(default=7, ge=1, le=90),
    send_email: bool = Query(default=True),
) -> dict:
    """Walks every series with next_due_at <= now and issues the next
    assignment for each. Designed for a Cloud Scheduler cron — idempotent
    and partial-failure tolerant."""

    return series_service.dispatch_due_series(
        supabase,
        principal,
        expires_in_days=expires_in_days,
        send_email=send_email,
    )
