"""Request and response shapes for the AI generation pipeline (spec §6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Difficulty = Literal["junior", "mid", "senior", "expert"]


class QuestionMix(BaseModel):
    """Optional admin-supplied constraints on the question type mix.

    Each percentage is optional. When a field is None, the AI picks a
    value that fits the role; when set, the AI must honor it. Set fields
    must collectively be <= 100; the remainder is filled in by the AI."""

    mcq_pct: float | None = Field(default=None, ge=0, le=100)
    short_pct: float | None = Field(default=None, ge=0, le=100)
    long_pct: float | None = Field(default=None, ge=0, le=100)
    code_pct: float | None = Field(default=None, ge=0, le=100)
    interactive_pct: float | None = Field(default=None, ge=0, le=100)

    def constrained_total(self) -> float:
        return sum(
            v
            for v in (
                self.mcq_pct,
                self.short_pct,
                self.long_pct,
                self.code_pct,
                self.interactive_pct,
            )
            if v is not None
        )

    def is_empty(self) -> bool:
        return all(
            v is None
            for v in (
                self.mcq_pct,
                self.short_pct,
                self.long_pct,
                self.code_pct,
                self.interactive_pct,
            )
        )


class GenerationBriefIn(BaseModel):
    role_title: str = Field(min_length=1, max_length=200)
    responsibilities: str = Field(min_length=1, max_length=8_000)
    target_duration_minutes: int = Field(ge=10, le=240)
    difficulty: Difficulty
    domains: list[str] = Field(default_factory=list)
    question_mix: QuestionMix | None = None
    reference_document_ids: list[str] = Field(default_factory=list)
    required_competencies: list[str] = Field(default_factory=list)
    notes: str | None = None


class OutlineTopic(BaseModel):
    name: str
    competency_tags: list[str]
    weight_pct: float
    question_count: int
    recommended_types: list[str]
    rationale: str


class GeneratedOutline(BaseModel):
    title: str
    description: str
    topics: list[OutlineTopic]
    total_points: float
    estimated_duration_minutes: int


class OutlineRunResponse(BaseModel):
    run_id: str
    outline: GeneratedOutline
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


class EditedOutlineTopic(BaseModel):
    """Outline topic shape accepted from the admin after edits.

    Mirrors OutlineTopic but every field is optional except `name`,
    `competency_tags`, and `recommended_types` so the admin can override
    everything but the structural anchors."""

    name: str
    competency_tags: list[str]
    weight_pct: float
    question_count: int
    recommended_types: list[str]
    rationale: str


class EditedOutline(BaseModel):
    title: str
    description: str
    topics: list[EditedOutlineTopic]
    total_points: float
    estimated_duration_minutes: int


class QuestionGenerationRequest(BaseModel):
    outline_run_id: str
    brief: GenerationBriefIn
    outline: EditedOutline
    slug: str = Field(min_length=1, max_length=120)
    domain: str = Field(min_length=1, max_length=80)


class QuestionGenerationResponse(BaseModel):
    module_id: str
    module_run_ids: list[str]
    questions_generated: int
    model: str
    total_tokens_in: int
    total_tokens_out: int


class PreviewVariantsRequest(BaseModel):
    variable_schema: dict[str, Any]
    prompt_template: str
    seed_count: int = Field(default=5, ge=1, le=10)


class PreviewVariant(BaseModel):
    seed: str
    variables: dict[str, Any]
    rendered_prompt: str


class PreviewVariantsResponse(BaseModel):
    variants: list[PreviewVariant]


class GenerationRunSummary(BaseModel):
    id: str
    stage: Literal["outline", "full", "single_question", "revision"]
    status: Literal["pending", "success", "failed"]
    model: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    created_at: datetime
    parent_run_id: str | None = None


class ReviseQuestionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)
    preserve: list[
        Literal[
            "type",
            "competency_tags",
            "max_points",
            "difficulty",
            "time_limit_seconds",
            "rubric",
        ]
    ] = Field(default_factory=list)


class ReviseQuestionResponse(BaseModel):
    question_id: str
    run_id: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    revised: dict[str, Any]


# Reference library ----------------------------------------------------------


class ReferenceTextUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=2_000_000)
    domain: str | None = Field(default=None, max_length=80)
    source_url: str | None = None


class ReferenceUrlUploadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=300)
    domain: str | None = Field(default=None, max_length=80)


class ReferenceDocumentSummary(BaseModel):
    id: str
    title: str
    source_url: str | None = None
    domain: str | None = None
    chunk_count: int
    created_at: datetime


class ReferenceUploadResponse(BaseModel):
    document: ReferenceDocumentSummary
    chunks_inserted: int
