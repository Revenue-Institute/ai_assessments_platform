"""Request and response shapes for admin endpoints (spec §14.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

ModuleStatus = Literal["draft", "published", "archived"]
Difficulty = Literal["junior", "mid", "senior", "expert"]
SubjectType = Literal["candidate", "employee"]
AssignmentStatus = Literal[
    "pending", "in_progress", "completed", "expired", "cancelled"
]


class ModuleCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    domain: str = Field(min_length=1, max_length=80)
    target_duration_minutes: int = Field(ge=1, le=480)
    difficulty: Difficulty


class ModulePatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    domain: str | None = Field(default=None, min_length=1, max_length=80)
    target_duration_minutes: int | None = Field(default=None, ge=1, le=480)
    difficulty: Difficulty | None = None


class ModuleSummary(BaseModel):
    id: str
    slug: str
    title: str
    description: str | None = None
    domain: str
    target_duration_minutes: int
    difficulty: Difficulty
    status: ModuleStatus
    version: int
    question_count: int
    created_at: datetime
    published_at: datetime | None = None


class ModuleDetail(ModuleSummary):
    questions: list[dict[str, Any]] = Field(default_factory=list)


AssessmentStatus = ModuleStatus


class AssessmentCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    module_ids: list[str] = Field(default_factory=list, max_length=20)


class AssessmentPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class AssessmentModuleEntry(BaseModel):
    module_id: str
    position: int
    title: str
    domain: str
    difficulty: Difficulty
    target_duration_minutes: int
    question_count: int


class AssessmentSummary(BaseModel):
    id: str
    slug: str
    title: str
    description: str | None = None
    status: AssessmentStatus
    version: int
    module_count: int
    question_count: int
    total_duration_minutes: int
    created_at: datetime
    published_at: datetime | None = None


class AssessmentDetail(AssessmentSummary):
    modules: list[AssessmentModuleEntry] = Field(default_factory=list)


class AssessmentModuleAddRequest(BaseModel):
    module_id: str
    position: int | None = None


class AssessmentReorderRequest(BaseModel):
    module_ids: list[str] = Field(min_length=1, max_length=20)


class SubjectCreateRequest(BaseModel):
    type: SubjectType
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    metadata: dict[str, Any] | None = None


class SubjectSummary(BaseModel):
    id: str
    type: SubjectType
    full_name: str
    email: str
    metadata: dict[str, Any]
    created_at: datetime


class AssignmentCreateRequest(BaseModel):
    """Bind a subject to an assessment. `module_id` is accepted only as a
    legacy alias when the admin still has just-a-module data; new flows
    pass `assessment_id`."""

    assessment_id: str | None = None
    module_id: str | None = None
    subject_id: str
    expires_in_days: int = Field(default=7, ge=1, le=90)
    send_email: bool = True


class AssignmentBulkCreateRequest(BaseModel):
    assessment_id: str | None = None
    module_id: str | None = None
    subject_ids: list[str] = Field(min_length=1, max_length=200)
    expires_in_days: int = Field(default=7, ge=1, le=90)
    send_email: bool = True


class AssignmentMagicLink(BaseModel):
    assignment_id: str
    subject_id: str
    assessment_id: str | None = None
    module_id: str | None = None
    expires_at: datetime
    magic_link_url: str
    token: str = Field(
        description=(
            "Raw signed JWT. Returned once at create time; not retrievable later."
        ),
    )


class AssignmentBulkCreateResult(BaseModel):
    created: list[AssignmentMagicLink]
    failed: list[dict[str, str]] = Field(default_factory=list)


class AssignmentSummary(BaseModel):
    id: str
    subject_id: str
    subject_full_name: str | None = None
    subject_email: str | None = None
    assessment_id: str | None = None
    assessment_title: str | None = None
    module_id: str | None = None
    module_title: str | None = None
    status: AssignmentStatus
    expires_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    integrity_score: float | None = None
    final_score: float | None = None
    max_possible_score: float | None = None
    # True when at least one scored attempt has needs_review=true
    # (low scorer confidence, spec §9.2). Drives the admin filter.
    needs_review: bool = False
    created_at: datetime


class AttemptSummary(BaseModel):
    id: str
    question_template_id: str
    rendered_prompt: str
    raw_answer: dict[str, Any] | None = None
    submitted_at: datetime | None = None
    score: float | None = None
    max_score: float
    score_rationale: str | None = None
    scorer_model: str | None = None
    scorer_confidence: float | None = None
    needs_review: bool = False
    active_time_seconds: int | None = None


class AssignmentDetail(AssignmentSummary):
    consent_at: datetime | None = None
    total_time_seconds: int | None = None
    attempts: list[AttemptSummary] = Field(default_factory=list)
