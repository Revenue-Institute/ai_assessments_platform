"""Response shapes for candidate-facing endpoints (spec §13, §14.2).

Hand-written for now. Will be regenerated from packages/schemas (Zod) once
the Zod → JSON Schema → Pydantic pipeline lands."""

from datetime import datetime
from typing import Literal

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
