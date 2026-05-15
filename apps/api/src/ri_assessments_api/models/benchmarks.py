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


class SeriesIssueNextResponse(BaseModel):
    series_id: str
    assignment_id: str
    module_id: str
    magic_link_url: str
    expires_at: datetime
    sequence_number: int
    next_due_at: datetime | None = None


class CompetencyDistributionResponse(BaseModel):
    competency_id: str
    sample_size: int
    min_pct: float
    p25_pct: float
    median_pct: float
    p75_pct: float
    max_pct: float
    values: list[float] = Field(
        default_factory=list,
        description="All score_pct values in the cohort, sorted ascending.",
    )
    # Spec §11.2: peer percentile per subject per competency. Populated when
    # the caller passes a subject_score or subject_id reference; null when
    # the queried subject has no score for this competency.
    subject_percentile: float | None = Field(
        default=None,
        description=(
            "Percentile rank (0 to 100) of the queried subject's latest "
            "score within the peer distribution. None when the subject "
            "has no score or no peer cohort exists."
        ),
    )
    subject_score_pct: float | None = Field(
        default=None,
        description=(
            "The subject's own latest score_pct for this competency, "
            "echoed back so the UI can render their dot on the boxplot."
        ),
    )


# Series trend (spec §11.4 'trend of each competency across sequence_number')


class SeriesTrendPoint(BaseModel):
    sequence_number: int
    assignment_id: str
    score_pct: float
    point_total: float
    point_possible: float
    completed_at: datetime | None = None


class SeriesTrendResponse(BaseModel):
    series_id: str
    subject_id: str
    competency_focus: list[str]
    # Keyed by competency_id; value is the per-sequence score timeline. UI
    # renders one trend line per competency.
    trends: dict[str, list[SeriesTrendPoint]] = Field(default_factory=dict)


# Assignment-scoped competency distribution (spec §11.3 candidate-vs-team) --


class AssignmentCompetencyDistribution(BaseModel):
    competency_id: str
    sample_size: int
    min_pct: float
    p25_pct: float
    median_pct: float
    p75_pct: float
    max_pct: float
    subject_score_pct: float | None = None
    subject_percentile: float | None = None


class CandidateAssignmentDistributionResponse(BaseModel):
    """Per-competency distribution view scoped to a single assignment so the
    assignment results page can render the candidate-vs-team overlay
    against only the competencies covered by that assignment (spec §11.3)."""

    subject_id: str
    assignment_id: str
    distributions: list[AssignmentCompetencyDistribution] = Field(
        default_factory=list
    )
