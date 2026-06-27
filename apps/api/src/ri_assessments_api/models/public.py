"""Request and response shapes for the unauthenticated public enrollment
endpoints (services/public_links.py, routers/public.py).

These power the shareable assessment link: a candidate opens
/a/enroll/{link_token}, the page reads PublicAssessmentView to render the
intro, and the name + email form posts PublicRegisterRequest to
self-provision a subject + assignment and receive a candidate token.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class PublicAssessmentView(BaseModel):
    """What the enrollment landing page shows before registration. Carries
    no admin internals (no ids, no module bank), just enough to describe
    the assessment and confirm the link is open."""

    title: str
    description: str | None = None
    module_count: int
    question_count: int
    total_duration_minutes: int


class PublicRegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    # The candidate must affirm they want to start; the full integrity
    # consent gate still runs on the /a/{token} screen afterwards.
    consent: bool = True


class PublicRegisterResponse(BaseModel):
    token: str
    # Relative path the candidate app redirects to in order to enter the
    # standard consent + attempt flow.
    redirect_path: str
    # True when the email already had an open assignment for this
    # assessment and we resumed it instead of minting a new one.
    resumed: bool = False
