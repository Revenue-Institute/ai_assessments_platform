"""Response shapes for benchmarking endpoints (spec §11)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CompetencyScorePoint(BaseModel):
    competency_id: str
    score_pct: float
    point_total: float
    point_possible: float
    assignment_id: str
    computed_at: datetime


class SubjectCompetencyTrend(BaseModel):
    competency_id: str
    points: list[CompetencyScorePoint]
    latest_score_pct: float
    delta_vs_previous: float | None = Field(
        default=None,
        description="Change vs the prior assignment, in percentage points.",
    )


class SubjectCompetencyResponse(BaseModel):
    subject_id: str
    trends: list[SubjectCompetencyTrend]


class CohortHeatmapCell(BaseModel):
    subject_id: str
    competency_id: str
    score_pct: float
    assignment_id: str
    computed_at: datetime


class CohortSubject(BaseModel):
    id: str
    full_name: str
    email: str
    type: Literal["candidate", "employee"]


class CohortHeatmapResponse(BaseModel):
    subjects: list[CohortSubject]
    competencies: list[str]
    cells: list[CohortHeatmapCell]
    team_average_pct: dict[str, float] = Field(
        default_factory=dict,
        description="Mean score_pct per competency across the cohort.",
    )


class WeakSpot(BaseModel):
    competency_id: str
    median_pct: float
    sample_size: int


class WeakSpotsResponse(BaseModel):
    threshold_pct: float
    weak_spots: list[WeakSpot]


# Series ---------------------------------------------------------------------


class SeriesCreateRequest(BaseModel):
    subject_id: str
    name: str = Field(min_length=1, max_length=200)
    competency_focus: list[str] = Field(min_length=1)
    cadence_days: int | None = Field(default=None, ge=1, le=365)
    next_due_at: datetime | None = None


class SeriesAssignmentSummary(BaseModel):
    assignment_id: str
    sequence_number: int
    status: str
    final_score: float | None = None
    max_possible_score: float | None = None
    completed_at: datetime | None = None


class SeriesSummary(BaseModel):
    id: str
    subject_id: str
    subject_full_name: str | None = None
    subject_email: str | None = None
    name: str
    competency_focus: list[str]
    cadence_days: int | None = None
    next_due_at: datetime | None = None
    created_at: datetime
    assignment_count: int = 0


class SeriesDetail(SeriesSummary):
    assignments: list[SeriesAssignmentSummary] = Field(default_factory=list)
