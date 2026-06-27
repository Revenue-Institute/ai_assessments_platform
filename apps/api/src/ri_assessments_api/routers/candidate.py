"""Candidate magic-link endpoints (spec §14.2)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from supabase import Client

from ..config import get_settings
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
    N8nEmbedRequest,
    N8nEmbedResponse,
    N8nExportRequest,
    N8nExportResponse,
    NotebookCellOutputView,
    NotebookCellRunRequest,
    NotebookRunRequest,
    NotebookRunResponse,
    SaveAnswerResponse,
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
    record_n8n_workflow_id,
    resolve_snapshot,
    save_draft_answer,
    submit_answer,
    verify_n8n_workflow_owner,
)
from ..services.code_runner import (
    run_test_suite,
    run_user_code,
    run_user_code_streaming,
)
from ..services.integrity import record_events, record_heartbeat
from ..services.n8n_runner import (
    export_workflow,
    provision_workspace,
)
from ..services.notebook_runner import run_notebook
from ..services.sql_runner import run_sql

# Rate limiting (spec §14.3, §18: bound abuse on the runner endpoints).
# slowapi is declared in apps/api/pyproject.toml; the try/except guard
# below stays so a stripped-down dev image (no slowapi) still serves
# routes, just without per-token throttling.
try:  # pragma: no cover - environment-dependent import
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    def _rate_limit_key(request: Request) -> str:
        """Per-token keying: the candidate token in the path is the unit
        of work we want to bound. Falls back to remote_address (admin
        clients hitting these via curl in dev) so the limiter never
        crashes when the path param isn't a candidate token."""
        params = request.path_params if hasattr(request, "path_params") else {}
        token = params.get("token")
        if token:
            return f"candidate:{token}"
        link = params.get("link_token")
        if link:
            # Public enrollment (/p/{link_token}/register) is internal-only:
            # the candidate Next server is the sole caller and forwards the
            # real client IP in x-forwarded-for. Key per (link, client) so a
            # single peer doesn't collapse every candidate into one bucket.
            forwarded = request.headers.get("x-forwarded-for")
            client = (
                forwarded.split(",")[0].strip()
                if forwarded
                else get_remote_address(request)
            )
            return f"enroll:{link}:{client}"
        return get_remote_address(request)

    _limiter: Limiter | None = Limiter(key_func=_rate_limit_key)

    def _rate_limit(spec: str):
        return _limiter.limit(spec)

    _RATE_LIMIT_ENABLED = True
except Exception:  # pragma: no cover - slowapi missing
    _limiter = None
    RateLimitExceeded = None  # type: ignore[assignment]

    def _rate_limit(spec: str):
        """No-op when slowapi is unavailable. Routes still serve, just
        without per-token throttling. Replace once slowapi is on the
        dependency list."""

        def _decorator(func):
            return func

        return _decorator

    _RATE_LIMIT_ENABLED = False


router = APIRouter(tags=["candidate"])

log = logging.getLogger(__name__)


def _resolve_client_ip(request: Request) -> str | None:
    """Spec §18: hash candidate IPs, never store raw, and only honor
    X-Forwarded-For when the immediate peer is a configured trusted proxy.
    An untrusted peer setting that header could otherwise spoof arbitrary
    client IPs into the integrity log. `settings.trusted_proxy_ips` is
    empty by default so the unsafe header is ignored unless an operator
    explicitly opts in via TRUSTED_PROXY_IPS."""

    settings = get_settings()
    peer = request.client.host if request.client else None
    trusted = set(settings.trusted_proxy_ips or [])
    if peer and peer in trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # First entry is the original client per RFC 7239 conventions.
            return forwarded.split(",")[0].strip() or peer
    return peer


def _ip_hash_from_request(request: Request) -> str | None:
    """Hash the resolved client IP with HMAC-SHA256 keyed by
    SESSION_COOKIE_SECRET. Using a keyed hash (rather than a bare
    sha256()) prevents trivial rainbow-table lookups against the
    attempt_events.ip_hash column; the secret stays server-side so an
    attacker holding only DB rows cannot reverse the IPs."""

    raw_ip = _resolve_client_ip(request)
    if not raw_ip:
        return None
    settings = get_settings()
    secret = (settings.session_cookie_secret or "").encode("utf-8")
    if not secret:
        # Local dev path with no secret configured: degrade to a plain
        # SHA-256 so the column is still populated. config.py refuses to
        # start in staging / production without a secret, so the keyed
        # path is the only one that runs there.
        return hashlib.sha256(raw_ip.encode("utf-8")).hexdigest()
    return hmac.new(secret, raw_ip.encode("utf-8"), hashlib.sha256).hexdigest()


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
        user_agent=_user_agent(request),
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


@router.post(
    "/{token}/questions/{index}/save",
    response_model=SaveAnswerResponse,
)
def save_question(
    token: str,
    index: int,
    body: SubmitAnswerRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SaveAnswerResponse:
    """Autosave the candidate's draft answer without scoring or advancing.
    Idempotent; the candidate can keep editing and call /submit later."""

    result = save_draft_answer(supabase, token, index, body.answer)
    return SaveAnswerResponse(**result)


@router.post("/{token}/heartbeat", response_model=HeartbeatResponse)
@_rate_limit("60/minute")
def heartbeat(
    request: Request,
    token: str,
    body: HeartbeatRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> HeartbeatResponse:
    result = record_heartbeat(supabase, token, body.focused_seconds_since_last)
    return HeartbeatResponse(**result)


@router.post("/{token}/events", response_model=EventsResponse)
@_rate_limit("30/minute")
def events(
    request: Request,
    token: str,
    body: EventsRequest,
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


@router.post("/{token}/start")
def start(
    token: str,
    request: Request,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict:
    """Spec §14.2: explicit start signal. Records consent (idempotent) and
    returns the assignment's started_at. The first question fetch already
    flips status to in_progress; this endpoint just gives the candidate
    UI a hook for the consent -> start transition."""

    consent = record_consent(
        supabase,
        token,
        ip_hash=_ip_hash_from_request(request),
        user_agent=_user_agent(request),
    )
    return {
        "ok": True,
        "assignment_id": consent.assignment_id,
        "status": consent.status,
        "started_at": consent.started_at.isoformat(),
        "server_deadline": consent.server_deadline.isoformat(),
    }


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
    questions = resolve_snapshot(assignment).get("questions") or []
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


@router.post("/{token}/code/run", response_model=None)
@_rate_limit("30/minute")
async def code_run(
    request: Request,
    token: str,
    body: CodeRunRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
    stream: Annotated[bool, Query()] = False,
) -> CodeRunResponse | StreamingResponse:
    """Execute the candidate's current buffer in an E2B sandbox
    (spec §7.1, §14.3).

    Default (`stream=false`): returns a buffered `CodeRunResponse` with
    aggregated stdout/stderr/exit_code (existing behavior, kept for
    back-compat).

    `stream=true`: returns `text/event-stream` SSE frames emitted as
    each stdout/stderr line arrives in the sandbox. Frame shapes:
      data: {"type": "started", "language": str, "time_limit_ms": int}
      data: {"type": "stdout",  "chunk": str}
      data: {"type": "stderr",  "chunk": str}
      data: {"type": "exit",    "exit_code": int, "runtime_ms": int,
              "timed_out": bool, "error": str|None}
    Plus periodic ": keepalive" comments to defeat proxy idle timeouts.
    The candidate frontend wires EventSource against this URL with
    `?stream=true`; this router only exposes the variant. Rate limit
    and the upstream JWT-token / question-type verification in
    _config_for_code_question apply identically to both shapes."""

    config = _config_for_code_question(supabase, token, body.question_index)
    language = config.get("language", "python")
    packages = list(config.get("packages") or [])
    time_limit_ms = int(config.get("time_limit_exec_ms") or 10_000)

    if stream:
        return StreamingResponse(
            run_user_code_streaming(
                code=body.code,
                language=language,
                packages=packages,
                time_limit_ms=time_limit_ms,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    result = run_user_code(
        code=body.code,
        language=language,
        packages=packages,
        time_limit_ms=time_limit_ms,
    )
    return CodeRunResponse(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        runtime_ms=result.runtime_ms,
        timed_out=result.timed_out,
    )


@router.post("/{token}/code/test", response_model=CodeTestResponse)
@_rate_limit("30/minute")
def code_test(
    request: Request,
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
    questions = resolve_snapshot(assignment).get("questions") or []
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
@_rate_limit("60/minute")
def sql_query(
    request: Request,
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
    questions = resolve_snapshot(assignment).get("questions") or []
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
@_rate_limit("30/minute")
def notebook_run(
    request: Request,
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


@router.post("/{token}/notebook/run-cell", response_model=NotebookRunResponse)
@_rate_limit("60/minute")
def notebook_run_cell(
    request: Request,
    token: str,
    body: NotebookCellRunRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> NotebookRunResponse:
    """Spec §14.3: run a single cell. Reuses run_notebook with a one-cell
    list since the v1 sandbox is fresh-per-call."""

    config = _config_for_notebook_question(supabase, token, body.question_index)
    result = run_notebook(
        cells=[body.cell.model_dump()],
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


@router.post("/{token}/notebook/save", response_model=SaveAnswerResponse)
def notebook_save(
    token: str,
    body: SubmitAnswerRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SaveAnswerResponse:
    """Spec §14.3 alias for autosaving a notebook answer. Body should
    include `question_index` plus the {cells: [...]} payload, we forward
    to save_draft_answer."""

    payload = body.answer
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="notebook/save expects an object body with question_index.",
        )
    qi = payload.get("question_index")
    if not isinstance(qi, int):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="question_index is required.",
        )
    answer = {k: v for k, v in payload.items() if k != "question_index"}
    result = save_draft_answer(supabase, token, qi, answer)
    return SaveAnswerResponse(**result)


@router.post("/{token}/diagram/save", response_model=SaveAnswerResponse)
def diagram_save(
    token: str,
    body: SubmitAnswerRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SaveAnswerResponse:
    """Spec §14.3 alias for autosaving a diagram answer. Body shape:
    {"question_index": N, "diagram": {nodes, edges}}."""

    payload = body.answer
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="diagram/save expects an object body with question_index.",
        )
    qi = payload.get("question_index")
    if not isinstance(qi, int):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="question_index is required.",
        )
    answer = {k: v for k, v in payload.items() if k != "question_index"}
    result = save_draft_answer(supabase, token, qi, answer)
    return SaveAnswerResponse(**result)


# n8n runner --------------------------------------------------------------


def _config_for_n8n_question(supabase: Client, token: str, index: int) -> dict:
    assignment = get_assignment_for_token(supabase, token)
    questions = resolve_snapshot(assignment).get("questions") or []
    if index < 0 or index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question index out of range.",
        )
    question = questions[index]
    if question["type"] != "n8n":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Endpoint is only valid for n8n questions.",
        )
    return question.get("interactive_config") or {}


def _provision_n8n(
    supabase: Client, token: str, question_index: int
) -> N8nEmbedResponse:
    config = _config_for_n8n_question(supabase, token, question_index)
    starter = config.get("starter_workflow") or {}
    assignment = get_assignment_for_token(supabase, token)
    title = resolve_snapshot(assignment).get("title") or "RI Workflow"
    result = provision_workspace(starter_workflow=starter, title=str(title))
    # Spec §7.2 + §14.3: bind the freshly provisioned workflow to the
    # attempt's metadata so /n8n/export can refuse any other workflow id.
    # n8n_runner.py owns the actual provisioning call; ownership tracking
    # lives in services/attempts.py (in this agent's scope) which is why
    # the recording lives here rather than inside provision_workspace.
    try:
        record_n8n_workflow_id(
            supabase,
            raw_token=token,
            question_index=question_index,
            workflow_id=result.workflow_id,
        )
    except HTTPException:
        # Refuse the embed if we can't record ownership, leaving an
        # un-owned workflow would defeat the export check.
        raise
    return N8nEmbedResponse(workflow_id=result.workflow_id, embed_url=result.embed_url)


@router.post("/{token}/n8n/embed", response_model=N8nEmbedResponse)
@_rate_limit("10/minute")
def n8n_embed(
    request: Request,
    token: str,
    body: N8nEmbedRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> N8nEmbedResponse:
    return _provision_n8n(supabase, token, body.question_index)


@router.get("/{token}/n8n/embed", response_model=N8nEmbedResponse)
def n8n_embed_get(
    token: str,
    question_index: int,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> N8nEmbedResponse:
    """Spec §14.3 alias: GET form takes question_index as a query
    parameter. Provisioning is a side effect, so POST is preferred for
    new clients, but GET matches the literal spec."""

    return _provision_n8n(supabase, token, question_index)


@router.post("/{token}/n8n/export", response_model=N8nExportResponse)
def n8n_export(
    token: str,
    body: N8nExportRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> N8nExportResponse:
    # Validates question type and ensures we own the workflow lookup path.
    _config_for_n8n_question(supabase, token, body.question_index)
    # Spec §7.2 + §14.3 ownership check: only the workflow_id that we
    # recorded on the attempt's metadata at provision time may be
    # exported through this token. Any other id (a candidate guessing,
    # or a leaked id from another tenant) is rejected.
    verify_n8n_workflow_owner(
        supabase,
        raw_token=token,
        question_index=body.question_index,
        workflow_id=body.workflow_id,
    )
    workflow = export_workflow(body.workflow_id)
    return N8nExportResponse(workflow_id=body.workflow_id, workflow=workflow)
