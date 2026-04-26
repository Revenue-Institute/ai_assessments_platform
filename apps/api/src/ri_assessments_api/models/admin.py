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
    module_id: str
    subject_id: str
    expires_in_days: int = Field(default=7, ge=1, le=90)


class AssignmentMagicLink(BaseModel):
    assignment_id: str
    subject_id: str
    module_id: str
    expires_at: datetime
    magic_link_url: str
    token: str = Field(
        description=(
            "Raw signed JWT. Returned once at create time; not retrievable later."
        ),
    )


class AssignmentSummary(BaseModel):
    id: str
    subject_id: str
    subject_full_name: str | None = None
    subject_email: str | None = None
    module_id: str | None = None
    module_title: str | None = None
    status: AssignmentStatus
    expires_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    integrity_score: float | None = None
    final_score: float | None = None
    max_possible_score: float | None = None
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
    active_time_seconds: int | None = None


class AssignmentDetail(AssignmentSummary):
    consent_at: datetime | None = None
    total_time_seconds: int | None = None
    attempts: list[AttemptSummary] = Field(default_factory=list)
