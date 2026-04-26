"""Candidate magic-link endpoints (spec §14.2)."""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from supabase import Client

from ..db import get_supabase
from ..models.candidate import (
    CandidateAssignmentView,
    CandidateQuestionView,
    CodeRunRequest,
    CodeRunResponse,
    CodeTestRequest,
    CodeTestResponse,
    CompleteResponse,
    ConsentResponse,
    EventsRequest,
    EventsResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    NotebookCellOutputView,
    NotebookRunRequest,
    NotebookRunResponse,
    SqlQueryRequest,
    SqlQueryResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from ..services.assignments import record_consent, resolve_token
from ..services.attempts import (
    complete_assignment,
    get_assignment_for_token,
    get_or_create_attempt_view,
    submit_answer,
)
from ..services.code_runner import run_test_suite, run_user_code
from ..services.integrity import record_events, record_heartbeat
from ..services.notebook_runner import run_notebook
from ..services.sql_runner import run_sql

router = APIRouter(tags=["candidate"])


def _ip_hash_from_request(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    raw_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    if not raw_ip:
        return None
    return hashlib.sha256(raw_ip.encode("utf-8")).hexdigest()


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.get("/{token}/resolve", response_model=CandidateAssignmentView)
def resolve(
    token: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> CandidateAssignmentView:
    return resolve_token(supabase, token)


@router.post("/{token}/consent", response_model=ConsentResponse)
def consent(
    token: str,
    request: Request,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ConsentResponse:
    return record_consent(
        supabase,
        token,
        ip_hash=_ip_hash_from_request(request),
    )


@router.get(
    "/{token}/questions/{index}",
    response_model=CandidateQuestionView,
)
def get_question(
    token: str,
    index: int,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> CandidateQuestionView:
    view = get_or_create_attempt_view(supabase, token, index)
    return CandidateQuestionView(**view)


@router.post(
    "/{token}/questions/{index}/submit",
    response_model=SubmitAnswerResponse,
)
def submit_question(
    token: str,
    index: int,
    body: SubmitAnswerRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SubmitAnswerResponse:
    result = submit_answer(supabase, token, index, body.answer)
    return SubmitAnswerResponse(**result)


@router.post("/{token}/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    token: str,
    body: HeartbeatRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> HeartbeatResponse:
    result = record_heartbeat(supabase, token, body.focused_seconds_since_last)
    return HeartbeatResponse(**result)


@router.post("/{token}/events", response_model=EventsResponse)
def events(
    token: str,
    body: EventsRequest,
    request: Request,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> EventsResponse:
    accepted = record_events(
        supabase,
        token,
        [event.model_dump() for event in body.events],
        user_agent=_user_agent(request),
        ip_hash=_ip_hash_from_request(request),
    )
    return EventsResponse(ok=True, accepted=accepted)


@router.post("/{token}/complete", response_model=CompleteResponse)
def complete(
    token: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> CompleteResponse:
    result = complete_assignment(supabase, token)
    return CompleteResponse(**result)


# Code runner endpoints ------------------------------------------------------


def _config_for_code_question(
    supabase: Client, token: str, index: int
) -> dict:
    """Resolve a code question's interactive_config from the assignment
    snapshot. Validates the question type is `code` so the endpoint cannot
    be used to introspect non-code questions."""

    assignment = get_assignment_for_token(supabase, token)
    questions = (assignment.get("module_snapshot") or {}).get("questions") or []
    if index < 0 or index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question index out of range.",
        )
    question = questions[index]
    if question["type"] != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Endpoint is only valid for code questions.",
        )
    config = question.get("interactive_config") or {}
    return config


@router.post("/{token}/code/run", response_model=CodeRunResponse)
def code_run(
    token: str,
    body: CodeRunRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> CodeRunResponse:
    config = _config_for_code_question(supabase, token, body.question_index)
    result = run_user_code(
        code=body.code,
        language=config.get("language", "python"),
        packages=list(config.get("packages") or []),
        time_limit_ms=int(config.get("time_limit_exec_ms") or 10_000),
    )
    return CodeRunResponse(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        runtime_ms=result.runtime_ms,
        timed_out=result.timed_out,
    )


@router.post("/{token}/code/test", response_model=CodeTestResponse)
def code_test(
    token: str,
    body: CodeTestRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> CodeTestResponse:
    """Runs the visible_tests bundled with the question against the
    candidate's current buffer. Hidden tests are never exposed here."""

    config = _config_for_code_question(supabase, token, body.question_index)
    visible_tests = config.get("visible_tests")
    if not visible_tests:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This question has no visible tests.",
        )
    result = run_test_suite(
        code=body.code,
        tests=visible_tests,
        language=config.get("language", "python"),
        packages=list(config.get("packages") or []),
        time_limit_ms=int(config.get("time_limit_exec_ms") or 15_000),
    )
    return CodeTestResponse(
        passed=result.passed,
        failed=result.failed,
        errors=result.errors,
        total=result.total,
        output=result.output,
        runtime_ms=result.runtime_ms,
        timed_out=result.timed_out,
    )


# SQL runner --------------------------------------------------------------


def _config_for_sql_question(supabase: Client, token: str, index: int) -> dict:
    assignment = get_assignment_for_token(supabase, token)
    questions = (assignment.get("module_snapshot") or {}).get("questions") or []
    if index < 0 or index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question index out of range.",
        )
    question = questions[index]
    if question["type"] != "sql":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Endpoint is only valid for sql questions.",
        )
    return question.get("interactive_config") or {}


@router.post("/{token}/sql/query", response_model=SqlQueryResponse)
def sql_query(
    token: str,
    body: SqlQueryRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SqlQueryResponse:
    config = _config_for_sql_question(supabase, token, body.question_index)
    result = run_sql(
        schema_sql=config.get("schema_sql") or "",
        seed_sql=config.get("seed_sql") or "",
        query_sql=body.sql,
    )
    return SqlQueryResponse(
        columns=result.columns,
        rows=result.rows,
        runtime_ms=result.runtime_ms,
        error=result.error,
        timed_out=result.timed_out,
    )


# Notebook runner ----------------------------------------------------------


def _config_for_notebook_question(
    supabase: Client, token: str, index: int
) -> dict:
    assignment = get_assignment_for_token(supabase, token)
    questions = (assignment.get("module_snapshot") or {}).get("questions") or []
    if index < 0 or index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question index out of range.",
        )
    question = questions[index]
    if question["type"] != "notebook":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Endpoint is only valid for notebook questions.",
        )
    return question.get("interactive_config") or {}


@router.post("/{token}/notebook/run", response_model=NotebookRunResponse)
def notebook_run(
    token: str,
    body: NotebookRunRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> NotebookRunResponse:
    config = _config_for_notebook_question(supabase, token, body.question_index)
    result = run_notebook(
        cells=[c.model_dump() for c in body.cells],
        dataset_urls=list(config.get("dataset_urls") or []),
    )
    return NotebookRunResponse(
        cells=[
            NotebookCellOutputView(
                index=row.index,
                type=row.type,
                stdout=row.stdout,
                stderr=row.stderr,
                error=row.error,
                runtime_ms=row.runtime_ms,
            )
            for row in result.cells
        ],
        runtime_ms=result.runtime_ms,
        timed_out=result.timed_out,
    )
