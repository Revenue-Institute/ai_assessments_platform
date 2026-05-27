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
UserRole = Literal["admin", "reviewer", "viewer"]


class ModuleQuestion(BaseModel):
    """Admin-facing question payload for `GET /api/modules/{id}`. Unlike
    the candidate view (see services/attempts._sanitize_interactive_config)
    the admin sees rubric, variable_schema, solver_code, and the full
    interactive_config so the module editor / preview page can render the
    bank without spinning up an attempt (spec §12.1, §14.1)."""

    id: str
    position: int
    type: str
    prompt_template: str
    variable_schema: dict[str, Any] = Field(default_factory=dict)
    solver_code: str | None = None
    interactive_config: dict[str, Any] | None = None
    rubric: dict[str, Any] = Field(default_factory=dict)
    competency_tags: list[str] = Field(default_factory=list)
    time_limit_seconds: int | None = None
    max_points: float = 10.0


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
    # Typed as ModuleQuestion for the admin module-detail endpoint so the
    # response includes rubric, variable_schema, solver_code, and
    # interactive_config. The list[dict] permissive shape stays via the
    # ModuleQuestion BaseModel which accepts extra keys downstream.
    questions: list[ModuleQuestion] = Field(default_factory=list)


QuestionType = Literal[
    "mcq",
    "multi_select",
    "short_answer",
    "long_answer",
    "code",
    "notebook",
    "sql",
    "n8n",
    "diagram",
    "scenario",
]


class QuestionTemplateCreate(BaseModel):
    """Typed body for POST /api/modules/{id}/questions. Mirrors the Zod
    `QuestionTemplate` in packages/schemas/src/question.ts. `position` is
    optional; the service appends when omitted."""

    type: QuestionType
    prompt_template: str = Field(min_length=1)
    variable_schema: dict[str, Any] = Field(default_factory=dict)
    solver_code: str | None = None
    solver_language: Literal["python"] = "python"
    interactive_config: dict[str, Any] | None = None
    rubric: dict[str, Any]
    competency_tags: list[str] = Field(min_length=1)
    time_limit_seconds: int | None = Field(default=None, ge=30, le=1800)
    max_points: float = Field(default=10, ge=0, le=100)
    difficulty: Difficulty
    metadata: dict[str, Any] | None = None
    position: int | None = Field(default=None, ge=0)


class QuestionTemplatePatch(BaseModel):
    """Typed body for PATCH /api/modules/{id}/questions/{qid}. Every field
    optional; the service applies only the keys that were sent."""

    type: QuestionType | None = None
    prompt_template: str | None = Field(default=None, min_length=1)
    variable_schema: dict[str, Any] | None = None
    solver_code: str | None = None
    solver_language: Literal["python"] | None = None
    interactive_config: dict[str, Any] | None = None
    rubric: dict[str, Any] | None = None
    competency_tags: list[str] | None = Field(default=None, min_length=1)
    time_limit_seconds: int | None = Field(default=None, ge=30, le=1800)
    max_points: float | None = Field(default=None, ge=0, le=100)
    difficulty: Difficulty | None = None
    metadata: dict[str, Any] | None = None
    position: int | None = Field(default=None, ge=0)


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
    pass `assessment_id`.

    `expires_in_days` is capped at 14. Magic-link tokens are bearer
    credentials in the URL path: a leaked link is replayable for the
    entire window. Two weeks is the longest window a candidate should
    ever need; HR can resend an expired link via the assignment detail
    page without re-binding the subject."""

    assessment_id: str | None = None
    module_id: str | None = None
    subject_id: str
    expires_in_days: int = Field(default=7, ge=1, le=14)
    send_email: bool = True


class AssignmentBulkCreateRequest(BaseModel):
    assessment_id: str | None = None
    module_id: str | None = None
    subject_ids: list[str] = Field(min_length=1, max_length=200)
    expires_in_days: int = Field(default=7, ge=1, le=14)
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


# Settings / users management (spec §12.1 /settings/users) -------------------


class UserListItem(BaseModel):
    """Internal user as surfaced on /settings/users. Mirrors the public.users
    row (spec §4.1) plus a self flag so the UI can grey-out destructive
    actions on the signed-in admin's own row."""

    id: str
    email: str
    full_name: str | None = None
    role: UserRole
    is_self: bool = False


class UserListResponse(BaseModel):
    users: list[UserListItem]


class UserRoleUpdate(BaseModel):
    role: UserRole
