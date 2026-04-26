"""Response shapes for candidate-facing endpoints (spec §13, §14.2).

Hand-written for now. Will be regenerated from packages/schemas (Zod) once
the Zod → JSON Schema → Pydantic pipeline lands."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CandidateSubjectView(BaseModel):
    """Subject info exposed to the candidate (no metadata, no email)."""

    full_name: str
    type: Literal["candidate", "employee"]


class CandidateModuleView(BaseModel):
    """Module shape the candidate sees on the consent screen."""

    title: str
    description: str
    target_duration_minutes: int
    question_count: int


class CandidateAssignmentView(BaseModel):
    """What the candidate UI receives for the consent + landing screen."""

    assignment_id: str
    status: Literal["pending", "in_progress", "completed", "expired", "cancelled"]
    expires_at: datetime
    started_at: datetime | None = None
    consent_at: datetime | None = None
    subject: CandidateSubjectView
    module: CandidateModuleView


class ConsentResponse(BaseModel):
    """Returned after the candidate accepts consent and the timer starts."""

    assignment_id: str
    status: Literal["in_progress"]
    started_at: datetime
    server_deadline: datetime = Field(
        description="UTC timestamp when the assignment hard-expires (spec §10.1)."
    )


class CandidateQuestionView(BaseModel):
    """Per-question payload sent to the candidate. Strips solver outputs and
    interactive_config fields that would leak the answer (spec §13.2)."""

    assignment_id: str
    index: int
    total: int
    question_template_id: str
    type: str
    rendered_prompt: str
    max_points: float
    time_limit_seconds: int | None = None
    competency_tags: list[str] = Field(default_factory=list)
    interactive_config: dict[str, Any] | None = None
    raw_answer: dict[str, Any] | None = None
    submitted_at: datetime | None = None
    expires_at: datetime


class SubmitAnswerRequest(BaseModel):
    """Candidate-supplied answer. Shape varies by question type; we accept
    arbitrary JSON-shaped input and let the rubric handle interpretation
    downstream."""

    answer: Any


class SubmitAnswerResponse(BaseModel):
    ok: Literal[True]
    next_index: int | None
    total: int


class SaveAnswerResponse(BaseModel):
    ok: Literal[True]
    saved_at: datetime


class HeartbeatRequest(BaseModel):
    focused_seconds_since_last: float = Field(ge=0, le=120)


class HeartbeatResponse(BaseModel):
    ok: Literal[True]
    applied: int
    attempt_id: str | None = None
    total_active_seconds: int | None = None


class IntegrityEventIn(BaseModel):
    type: str
    payload: dict[str, Any] | None = None
    client_timestamp: datetime | None = None
    attempt_id: str | None = None


class EventsRequest(BaseModel):
    events: list[IntegrityEventIn]


class EventsResponse(BaseModel):
    ok: Literal[True]
    accepted: int


class CompleteResponse(BaseModel):
    assignment_id: str
    status: Literal["completed"]
    completed_at: datetime


class CodeRunRequest(BaseModel):
    code: str = Field(max_length=200_000)
    question_index: int = Field(ge=0)


class CodeRunResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    runtime_ms: int
    timed_out: bool


class CodeTestRequest(BaseModel):
    code: str = Field(max_length=200_000)
    question_index: int = Field(ge=0)


class CodeTestResponse(BaseModel):
    passed: int
    failed: int
    errors: int
    total: int
    output: str
    runtime_ms: int
    timed_out: bool


class SqlQueryRequest(BaseModel):
    sql: str = Field(max_length=20_000)
    question_index: int = Field(ge=0)


class SqlQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    runtime_ms: int
    error: str | None = None
    timed_out: bool


class DiagramSubmitRequest(BaseModel):
    """React Flow JSON exported by the candidate."""

    question_index: int = Field(ge=0)
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class NotebookCell(BaseModel):
    type: Literal["code", "markdown"]
    source: str = Field(default="", max_length=200_000)


class NotebookRunRequest(BaseModel):
    question_index: int = Field(ge=0)
    cells: list[NotebookCell]


class NotebookCellOutputView(BaseModel):
    index: int
    type: str
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    runtime_ms: int = 0


class NotebookRunResponse(BaseModel):
    cells: list[NotebookCellOutputView]
    runtime_ms: int
    timed_out: bool


class N8nEmbedRequest(BaseModel):
    question_index: int = Field(ge=0)


class N8nEmbedResponse(BaseModel):
    workflow_id: str
    embed_url: str


class N8nExportRequest(BaseModel):
    question_index: int = Field(ge=0)
    workflow_id: str


class N8nExportResponse(BaseModel):
    workflow_id: str
    workflow: dict[str, Any]
