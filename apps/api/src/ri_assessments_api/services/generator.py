"""AI generation pipeline (spec §6). Stage 1 (outline) and Stage 2
(per-topic questions) wrap Anthropic tool-use calls with prompt caching
on the static system prompt + competency taxonomy."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from fastapi import HTTPException, status
from postgrest.exceptions import APIError
from supabase import Client

from ..auth import AdminPrincipal, ensure_role
from ..config import get_settings
from ..models.admin import QuestionTemplateCreate
from ..models.generator import (
    EditedOutline,
    GeneratedOutline,
    GenerationBriefIn,
    OutlineRunResponse,
    QuestionGenerationResponse,
)
from ..models.interactive import validate_interactive_config
from ..prompts.outline import OUTLINE_SYSTEM_PROMPT, SUBMIT_OUTLINE_TOOL
from ..prompts.questions import QUESTIONS_SYSTEM_PROMPT, SUBMIT_QUESTIONS_TOOL
from ..prompts.revision import REVISION_SYSTEM_PROMPT, SUBMIT_REVISED_QUESTION_TOOL
from . import queue as queue_service
from . import references as references_service
from .randomizer import question_seed, render_prompt, sample_variables

log = logging.getLogger(__name__)

# Spec §15 names Sonnet 4.5 for generation; we use the latest in that family.
GENERATION_MODEL = "claude-sonnet-4-6"


def _client() -> Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key_generation:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY_GENERATION is not configured.",
        )
    return Anthropic(api_key=settings.anthropic_api_key_generation)


# -- Taxonomy injection ------------------------------------------------------


def _load_taxonomy_rows() -> list[dict[str, Any]]:
    """Parsed taxonomy rows from packages/competencies/src/taxonomy.json.
    Cached on first call. Used for both prompt injection and Stage-2
    competency_tag validation (spec §6.2 directive 5)."""

    global _CACHED_TAXONOMY_ROWS
    if _CACHED_TAXONOMY_ROWS is not None:
        return _CACHED_TAXONOMY_ROWS
    # __file__ -> apps/api/src/ri_assessments_api/services/generator.py
    # parents[0..4] climb to apps/, parents[5] is the repo root.
    repo_root = Path(__file__).resolve().parents[5]
    path = repo_root / "packages" / "competencies" / "src" / "taxonomy.json"
    if not path.exists():
        raise RuntimeError(f"Competency taxonomy not found at {path}")
    _CACHED_TAXONOMY_ROWS = json.loads(path.read_text(encoding="utf-8"))
    return _CACHED_TAXONOMY_ROWS


def _load_taxonomy_text() -> str:
    """Render the taxonomy as `id - label` lines for prompt injection."""

    global _CACHED_TAXONOMY
    if _CACHED_TAXONOMY is not None:
        return _CACHED_TAXONOMY
    rows = _load_taxonomy_rows()
    lines = [f"{row['id']} - {row['label']}" for row in rows]
    _CACHED_TAXONOMY = "\n".join(lines)
    return _CACHED_TAXONOMY


def _taxonomy_ids() -> set[str]:
    """Set of valid competency ids for membership checks."""

    global _CACHED_TAXONOMY_IDS
    if _CACHED_TAXONOMY_IDS is not None:
        return _CACHED_TAXONOMY_IDS
    _CACHED_TAXONOMY_IDS = {row["id"] for row in _load_taxonomy_rows()}
    return _CACHED_TAXONOMY_IDS


_CACHED_TAXONOMY: str | None = None
_CACHED_TAXONOMY_ROWS: list[dict[str, Any]] | None = None
_CACHED_TAXONOMY_IDS: set[str] | None = None


def _filter_competency_tags(tags: Any) -> list[str]:
    """Spec §6.2 directive 5: only emit competency tags present in the
    taxonomy. Returns a de-duplicated list preserving order."""

    valid = _taxonomy_ids()
    out: list[str] = []
    seen: set[str] = set()
    for t in tags or []:
        if isinstance(t, str) and t in valid and t not in seen:
            out.append(t)
            seen.add(t)
    return out


def _validate_stage2_question(
    raw: dict[str, Any], default_difficulty: str
) -> tuple[bool, str | None]:
    """Spec §6.1 Stage-2 validation. Returns (ok, reason).

    Fails fast on:
    - QuestionTemplateCreate (Pydantic) validation. We feed a synthesized
      shape, defaulting difficulty so the model isn't required to emit it.
    - interactive_config schema for typed question types.
    - Empty / out-of-taxonomy competency_tags after filtering.

    Failures cause the question to be skipped; v1 picks fail-the-question
    strictness so a single bad item doesn't poison the entire topic."""

    qtype = raw.get("type")
    if not isinstance(qtype, str):
        return False, "missing type"

    # Pre-filter competency_tags so a Pydantic min_length=1 check after the
    # filter still catches questions that had only invalid tags.
    filtered_tags = _filter_competency_tags(raw.get("competency_tags"))
    if not filtered_tags:
        return False, "no valid competency_tags after taxonomy filter"

    candidate_body: dict[str, Any] = {
        "type": qtype,
        "prompt_template": raw.get("prompt_template") or "",
        "variable_schema": raw.get("variable_schema") or {},
        "solver_code": raw.get("solver_code"),
        "solver_language": "python",
        "interactive_config": raw.get("interactive_config"),
        "rubric": raw.get("rubric") or {},
        "competency_tags": filtered_tags,
        "time_limit_seconds": raw.get("time_limit_seconds"),
        "max_points": float(raw.get("max_points") or 10),
        "difficulty": raw.get("difficulty") or default_difficulty,
        "metadata": raw.get("metadata") or {},
    }
    try:
        QuestionTemplateCreate.model_validate(candidate_body)
    except Exception as exc:
        return False, f"QuestionTemplate validation failed: {exc}"

    try:
        validate_interactive_config(qtype, raw.get("interactive_config"))
    except HTTPException as exc:
        # validate_interactive_config raises 422 with a structured detail.
        return False, f"interactive_config invalid: {exc.detail}"

    return True, None


def _system_blocks(prompt: str) -> list[dict[str, Any]]:
    """Cache the system prompt + taxonomy together. Stable across requests,
    so prompt caching saves the prefix on every subsequent call."""

    text = f"{prompt}\n\n<competency_taxonomy>\n{_load_taxonomy_text()}\n</competency_taxonomy>"
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


# -- Generation runs persistence --------------------------------------------


def _record_run(
    supabase: Client,
    *,
    stage: str,
    input_brief: dict[str, Any],
    output: dict[str, Any],
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    status_value: str,
    error: str | None = None,
    parent_run_id: str | None = None,
    created_by: str | None = None,
) -> str:
    payload = {
        "id": str(uuid.uuid4()),
        "stage": stage,
        "input_brief": input_brief,
        "output": output,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "status": status_value,
        "error": error,
        "parent_run_id": parent_run_id,
        "created_by": created_by,
    }
    res = supabase.table("generation_runs").insert(payload).execute()
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist generation run.",
        )
    return res.data[0]["id"]


def _extract_tool_input(response: Any, tool_name: str) -> dict[str, Any]:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return dict(block.input or {})
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=(
            f"Generation model did not invoke {tool_name}. "
            f"stop_reason={getattr(response, 'stop_reason', None)}"
        ),
    )


# -- Stage 1: outline -------------------------------------------------------


def _outline_user_prompt(brief: GenerationBriefIn) -> str:
    parts = [
        "Generate an assessment outline for the following role.",
        "",
        f"Role title: {brief.role_title}",
        f"Difficulty: {brief.difficulty}",
        f"Target duration: {brief.target_duration_minutes} minutes",
        f"Domains: {', '.join(brief.domains) if brief.domains else '(none specified)'}",
        "",
    ]

    mix = brief.question_mix
    if mix is None or mix.is_empty():
        parts.append(
            "Question mix: not specified. Pick a mix that fits the role's "
            "actual day-to-day work. Bias toward interactive types "
            "(code, sql, n8n, notebook, diagram) for hands-on roles; bias "
            "toward written types (mcq, short_answer, long_answer) for "
            "judgment / strategy roles. Buckets: mcq_pct, short_pct, "
            "long_pct, code_pct, interactive_pct (interactive covers n8n, "
            "notebook, diagram, sql)."
        )
    else:
        constrained = mix.constrained_total()
        if constrained > 100.5:  # tiny float slack
            raise HTTPException(
                status_code=400,
                detail=(
                    "question_mix constraints sum to more than 100% "
                    f"({constrained:.1f}%). Reduce values so the constrained "
                    "buckets total at most 100, or leave fields blank for "
                    "the AI to fill."
                ),
            )

        parts.append(
            "Question mix targets. Explicit percentages are HARD CONSTRAINTS "
            "set by the admin. The final outline must hit each explicit "
            "value within plus or minus 10 percent. Pick values for any "
            "bucket marked AI-pick. Do not substitute a different question "
            "type because you think the role does not justify it; design "
            "topics that exercise the requested types instead."
        )
        labels = [
            ("mcq", mix.mcq_pct),
            ("short_answer", mix.short_pct),
            ("long_answer", mix.long_pct),
            ("code", mix.code_pct),
            ("interactive (n8n / notebook / diagram / sql)", mix.interactive_pct),
        ]
        for label, value in labels:
            if value is None:
                parts.append(f"  {label}: AI-pick")
            else:
                parts.append(f"  {label}: {value}%")
        if 0 < constrained < 100:
            parts.append(
                f"  Total of explicit values is {constrained:.0f}%. Fill the "
                f"remaining {100 - constrained:.0f}% across AI-pick buckets."
            )

    parts.extend(
        [
            "",
            "Required competencies (must each appear in at least one topic):",
        ]
    )
    parts.extend(f"  - {tag}" for tag in brief.required_competencies) if (
        brief.required_competencies
    ) else parts.append("  (none specified)")
    parts.extend(
        [
            "",
            "Responsibilities text:",
            "<responsibilities>",
            brief.responsibilities,
            "</responsibilities>",
        ]
    )
    if brief.notes:
        parts.extend(["", "Author notes:", brief.notes])
    parts.append("\nReturn the outline via the submit_outline tool.")
    return "\n".join(parts)


def generate_outline(
    supabase: Client,
    principal: AdminPrincipal,
    brief: GenerationBriefIn,
) -> OutlineRunResponse:
    ensure_role(principal, "admin", "reviewer")

    started = time.monotonic()
    client = _client()
    response = client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=8000,
        output_config={"effort": "high"},
        system=_system_blocks(OUTLINE_SYSTEM_PROMPT),
        tools=[SUBMIT_OUTLINE_TOOL],
        tool_choice={"type": "tool", "name": "submit_outline"},
        messages=[{"role": "user", "content": _outline_user_prompt(brief)}],
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    raw_output = _sanitize_text(_extract_tool_input(response, "submit_outline"))
    try:
        outline = GeneratedOutline.model_validate(raw_output)
    except Exception as exc:
        log.exception("outline validation failed")
        _record_run(
            supabase,
            stage="outline",
            input_brief=brief.model_dump(),
            output={"raw": raw_output, "error": str(exc)},
            model=GENERATION_MODEL,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            latency_ms=latency_ms,
            status_value="failed",
            error=str(exc),
            created_by=principal.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Outline failed schema validation: {exc}",
        ) from exc

    run_id = _record_run(
        supabase,
        stage="outline",
        input_brief=brief.model_dump(),
        output=outline.model_dump(),
        model=GENERATION_MODEL,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        latency_ms=latency_ms,
        status_value="success",
        created_by=principal.user_id,
    )
    return OutlineRunResponse(
        run_id=run_id,
        outline=outline,
        model=GENERATION_MODEL,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        latency_ms=latency_ms,
    )


# -- Stage 2: per-topic questions -------------------------------------------


def _questions_user_prompt(
    brief: GenerationBriefIn,
    topic: dict[str, Any],
    reference_chunks: list[dict[str, Any]] | None = None,
) -> str:
    parts = [
        "Generate question templates for the following outline topic.\n",
        f"Role title: {brief.role_title}",
        f"Default difficulty: {brief.difficulty}",
        "",
        "Topic:",
        f"  name: {topic['name']}",
        f"  competency_tags: {', '.join(topic['competency_tags'])}",
        f"  weight_pct: {topic['weight_pct']}",
        f"  question_count: {topic['question_count']}",
        f"  recommended_types: {', '.join(topic['recommended_types'])}",
        f"  rationale: {topic['rationale']}",
    ]
    if reference_chunks:
        parts.extend(["", "<reference_material>"])
        for chunk in reference_chunks:
            sim = chunk.get("similarity")
            sim_str = f" (similarity {sim:.2f})" if isinstance(sim, (int, float)) else ""
            position = chunk.get("chunk_position", chunk.get("position"))
            parts.append(
                f"<chunk document_id=\"{chunk['document_id']}\" "
                f"position=\"{position}\"{sim_str}>"
            )
            parts.append(chunk["content"])
            parts.append("</chunk>")
        parts.append("</reference_material>")
        parts.append(
            "Use the reference material above to ground your questions. "
            "Cite document_ids you used in metadata.sources on each question."
        )
    parts.append("\nReturn the questions via the submit_questions tool.")
    return "\n".join(parts)


def _document_title_lookup(supabase: Client, document_ids: list[str]) -> dict[str, str]:
    if not document_ids:
        return {}
    res = (
        supabase.table("reference_documents")
        .select("id, title")
        .in_("id", document_ids)
        .execute()
    )
    return {row["id"]: row.get("title", "") for row in res.data or []}


_EMDASH = "\u2014"
_ENDASH = "\u2013"


def _sanitize_text(value: Any) -> Any:
    """Strip em / en dashes from generated copy (spec §2 codebase rule).
    Recurses into dicts and lists so we cover prompt_template, rubric
    text, interactive_config option labels, and any other free-form
    strings the model might emit."""

    if isinstance(value, str):
        return value.replace(_EMDASH, ", ").replace(_ENDASH, "-")
    if isinstance(value, list):
        return [_sanitize_text(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_text(v) for k, v in value.items()}
    return value


def _self_verify_question(raw_q: dict[str, Any]) -> bool:
    """Spec §6.3 rule 10. Returns True when the question's solver works
    on 3 sampled variable sets, or when there is no solver to run.
    Skips silently when E2B is unavailable so local dev / first-deploy
    flows aren't blocked."""

    solver = raw_q.get("solver_code")
    schema = raw_q.get("variable_schema") or {}
    if not isinstance(solver, str) or not solver.strip():
        return True
    from .solver_runner import fairness_check

    report = fairness_check(
        solver_code=solver,
        variable_schema=schema,
        sample_count=3,
    )
    # When E2B is offline every sample comes back with `solver returned
    # no result`, treat that as "could not verify, accept" so we don't
    # block all generated questions in dev.
    if report.get("failures"):
        all_no_result = all(
            f.get("error") == "solver returned no result"
            for f in report["failures"]
        )
        if all_no_result:
            return True
    return bool(report.get("passed"))


def _normalize_question_row(
    raw: dict[str, Any],
    *,
    module_id: str,
    position: int,
    cited_document_titles: dict[str, str] | None = None,
    source_generation_id: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"generated_difficulty": raw.get("difficulty")}
    if cited_document_titles:
        metadata["sources"] = [
            {"document_id": doc_id, "title": title}
            for doc_id, title in cited_document_titles.items()
        ]
    if source_generation_id:
        # Persisted so revision lookups (services.generator.revise_question)
        # can trace parent_run_id through the generation_runs tree.
        metadata["source_generation_id"] = source_generation_id
    return {
        "id": str(uuid.uuid4()),
        "module_id": module_id,
        "position": position,
        "type": raw["type"],
        "prompt_template": _sanitize_text(raw["prompt_template"]),
        "variable_schema": raw.get("variable_schema") or {},
        "solver_code": raw.get("solver_code"),
        "solver_language": "python",
        # Already validated upstream by _validate_stage2_question; run it
        # through validate_interactive_config one more time so the
        # round-tripped (alias-resolved) shape lands in storage.
        "interactive_config": validate_interactive_config(
            raw["type"], _sanitize_text(raw.get("interactive_config"))
        ),
        "rubric": _sanitize_text(raw["rubric"]),
        "competency_tags": _filter_competency_tags(raw.get("competency_tags")),
        "time_limit_seconds": raw.get("time_limit_seconds"),
        "max_points": float(raw.get("max_points") or 10),
        "metadata": metadata,
    }


def generate_questions(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    outline_run_id: str,
    brief: GenerationBriefIn,
    outline: EditedOutline,
    slug: str,
    domain: str,
) -> QuestionGenerationResponse:
    ensure_role(principal, "admin")

    client = _client()

    # Create the draft module first so we have an id for question_templates rows.
    # (slug, version) is the uniqueness key. A re-run of the wizard with the
    # same slug after an earlier failure leaves an orphan draft and would
    # collide with a 500. Translate that into a clean 409 so the wizard can
    # tell the admin to archive or rename.
    try:
        module_insert = (
            supabase.table("modules")
            .insert(
                {
                    "slug": slug,
                    "title": outline.title,
                    "description": outline.description,
                    "domain": domain,
                    "target_duration_minutes": outline.estimated_duration_minutes,
                    "difficulty": brief.difficulty,
                    "status": "draft",
                    "version": 1,
                    "created_by": principal.user_id,
                    "source_generation_id": outline_run_id,
                }
            )
            .execute()
        )
    except APIError as exc:
        message = str(getattr(exc, "message", exc) or "")
        code = getattr(exc, "code", "") or ""
        if code == "23505" or "modules_slug_version_key" in message:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A module with slug '{slug}' already exists. Archive the "
                    "existing draft or pick a different slug, then re-run "
                    "the wizard."
                ),
            ) from exc
        raise
    if not module_insert.data:
        raise HTTPException(
            status_code=500, detail="Failed to create draft module."
        )
    module_id = module_insert.data[0]["id"]

    document_titles: dict[str, str] = {}
    if brief.reference_document_ids:
        document_titles = _document_title_lookup(supabase, brief.reference_document_ids)

    # Spec §12.2 step 4: announce the run so admin SSE subscribers can
    # render "1 of N" progress. outline_run_id is the natural anchor: the
    # client already has it (it posted it on this request) and it ties
    # the progress channel to the lineage we already record in
    # generation_runs.
    topic_names = [topic.name for topic in outline.topics]
    queue_service.publish_generation_event(
        outline_run_id,
        {
            "type": "started",
            "topics": topic_names,
            "total_topics": len(topic_names),
        },
    )

    def _generate_for_topic(topic: Any) -> dict[str, Any]:
        """Worker: retrieve refs, call Claude, parse + verify questions.
        Returns a dict the main thread folds into the aggregate result."""

        topic_dict = topic.model_dump()
        reference_chunks: list[dict[str, Any]] = []
        cited_titles: dict[str, str] = {}
        if brief.reference_document_ids:
            try:
                query = f"{topic.name} - {' '.join(topic.competency_tags)}"
                reference_chunks = references_service.retrieve_top_k(
                    supabase,
                    query=query,
                    document_ids=brief.reference_document_ids,
                    k=10,
                )
                cited_doc_ids = {c["document_id"] for c in reference_chunks}
                cited_titles = {
                    doc_id: document_titles.get(doc_id, "")
                    for doc_id in cited_doc_ids
                }
            except HTTPException as exc:
                log.warning(
                    "reference retrieval failed for topic %s: %s",
                    topic.name,
                    exc.detail,
                )

        started = time.monotonic()
        try:
            response = client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=16_000,
                output_config={"effort": "high"},
                system=_system_blocks(QUESTIONS_SYSTEM_PROMPT),
                tools=[SUBMIT_QUESTIONS_TOOL],
                tool_choice={"type": "tool", "name": "submit_questions"},
                messages=[
                    {
                        "role": "user",
                        "content": _questions_user_prompt(
                            brief, topic_dict, reference_chunks
                        ),
                    }
                ],
            )
        except Exception as exc:
            log.exception("question generation failed for topic %s", topic.name)
            return {
                "topic_dict": topic_dict,
                "status": "failed",
                "error": str(exc),
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "raw_questions": [],
                "verified_questions": [],
                "cited_titles": {},
            }

        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            raw_output = _extract_tool_input(response, "submit_questions")
            raw_questions = list(raw_output.get("questions") or [])
        except HTTPException as exc:
            return {
                "topic_dict": topic_dict,
                "status": "failed",
                "error": exc.detail,
                "tokens_in": response.usage.input_tokens,
                "tokens_out": response.usage.output_tokens,
                "latency_ms": latency_ms,
                "raw_response_text": _stringify_text(response),
                "raw_questions": [],
                "verified_questions": [],
                "cited_titles": {},
            }

        # Spec §6.1 strictness: Pydantic shape + interactive_config schema
        # + competency_tag taxonomy membership are all enforced. A
        # question that fails any of these is dropped and logged so the
        # admin sees a smaller question_count rather than a malformed row.
        verified: list[dict[str, Any]] = []
        validation_errors: list[dict[str, Any]] = []
        for raw_q in raw_questions:
            if not _self_verify_question(raw_q):
                validation_errors.append(
                    {"reason": "self_verify failed", "type": raw_q.get("type")}
                )
                continue
            ok, reason = _validate_stage2_question(raw_q, brief.difficulty)
            if not ok:
                validation_errors.append(
                    {"reason": reason, "type": raw_q.get("type")}
                )
                log.warning(
                    "generator dropped stage-2 question for topic %s: %s",
                    topic.name,
                    reason,
                )
                continue
            verified.append(raw_q)
        return {
            "topic_dict": topic_dict,
            "status": "success",
            "tokens_in": response.usage.input_tokens,
            "tokens_out": response.usage.output_tokens,
            "latency_ms": latency_ms,
            "raw_questions": raw_questions,
            "verified_questions": verified,
            "validation_errors": validation_errors,
            "cited_titles": cited_titles,
        }

    # Run per-topic generation calls in parallel. Cap concurrency so we
    # don't blow past Anthropic rate limits - each topic request streams
    # 16K tokens and takes 10-30s; 4 in flight gets us a 4x speedup
    # without tripping the org-level RPS cap.
    #
    # Use submit + as_completed (not map) so we can publish a
    # `topic_completed` SSE event the moment each future resolves,
    # rather than waiting for the whole batch. Spec §12.2 step 4: live
    # "1 of N" progress.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    max_workers = min(len(outline.topics), 4) or 1
    topic_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_topic = {
            pool.submit(_generate_for_topic, topic): topic for topic in outline.topics
        }
        for completed_count, future in enumerate(
            as_completed(future_to_topic), start=1
        ):
            topic = future_to_topic[future]
            try:
                outcome = future.result()
            except Exception as exc:
                # Defensive: _generate_for_topic catches its own errors,
                # but a future-level crash should still publish a failed
                # event so the UI doesn't stall on "N of N".
                outcome = {
                    "topic_dict": topic.model_dump(),
                    "status": "failed",
                    "error": str(exc),
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "latency_ms": 0,
                    "raw_questions": [],
                    "verified_questions": [],
                    "cited_titles": {},
                }
            topic_results.append(outcome)
            queue_service.publish_generation_event(
                outline_run_id,
                {
                    "type": "topic_completed",
                    "topic_name": topic.name,
                    "status": outcome.get("status") or "failed",
                    "questions_count": len(outcome.get("verified_questions") or []),
                    "raw_count": len(outcome.get("raw_questions") or []),
                    "dropped_count": len(outcome.get("validation_errors") or []),
                    "error": outcome.get("error"),
                    "completed": completed_count,
                    "total_topics": len(topic_names),
                },
            )

    run_ids: list[str] = []
    total_tokens_in = 0
    total_tokens_out = 0
    questions_generated = 0
    position = 0
    for outcome in topic_results:
        topic_dict = outcome["topic_dict"]
        total_tokens_in += int(outcome.get("tokens_in") or 0)
        total_tokens_out += int(outcome.get("tokens_out") or 0)

        if outcome["status"] == "failed":
            run_id = _record_run(
                supabase,
                stage="full",
                input_brief={"brief": brief.model_dump(), "topic": topic_dict},
                output={
                    "error": outcome.get("error"),
                    "raw_response_text": outcome.get("raw_response_text"),
                },
                model=GENERATION_MODEL,
                tokens_in=int(outcome.get("tokens_in") or 0),
                tokens_out=int(outcome.get("tokens_out") or 0),
                latency_ms=int(outcome.get("latency_ms") or 0),
                status_value="failed",
                error=str(outcome.get("error") or ""),
                parent_run_id=outline_run_id,
                created_by=principal.user_id,
            )
            run_ids.append(run_id)
            continue

        # Record the run first so each persisted question can stamp
        # metadata.source_generation_id with this run's id. Without that
        # link the revise endpoint can't trace parent_run_id back to the
        # generating call (spec §6.5).
        run_id = _record_run(
            supabase,
            stage="full",
            input_brief={"brief": brief.model_dump(), "topic": topic_dict},
            output={
                "questions": outcome["raw_questions"],
                "validation_errors": outcome.get("validation_errors") or [],
            },
            model=GENERATION_MODEL,
            tokens_in=int(outcome.get("tokens_in") or 0),
            tokens_out=int(outcome.get("tokens_out") or 0),
            latency_ms=int(outcome.get("latency_ms") or 0),
            status_value="success",
            parent_run_id=outline_run_id,
            created_by=principal.user_id,
        )
        run_ids.append(run_id)

        rows: list[dict[str, Any]] = []
        for raw_q in outcome["verified_questions"]:
            rows.append(
                _normalize_question_row(
                    raw_q,
                    module_id=module_id,
                    position=position,
                    cited_document_titles=outcome["cited_titles"],
                    source_generation_id=run_id,
                )
            )
            position += 1
        if rows:
            supabase.table("question_templates").insert(rows).execute()
            questions_generated += len(rows)

    queue_service.publish_generation_event(
        outline_run_id,
        {
            "type": "finished",
            "module_id": module_id,
            "total_questions": questions_generated,
        },
    )

    return QuestionGenerationResponse(
        module_id=module_id,
        module_run_ids=run_ids,
        questions_generated=questions_generated,
        model=GENERATION_MODEL,
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
    )


def _stringify_text(response: Any) -> str:
    out = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            out.append(block.text)
    return "\n".join(out)


# -- Revision ---------------------------------------------------------------


_PRESERVABLE_FIELDS: frozenset[str] = frozenset(
    {"type", "competency_tags", "max_points", "difficulty", "time_limit_seconds", "rubric"}
)


def _question_row(supabase: Client, question_id: str) -> dict[str, Any]:
    res = (
        supabase.table("question_templates")
        .select(
            "id, module_id, position, type, prompt_template, variable_schema, "
            "solver_code, solver_language, interactive_config, rubric, "
            "competency_tags, time_limit_seconds, max_points, metadata"
        )
        .eq("id", question_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question template not found.",
        )
    return rows[0]


def revise_question(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    question_id: str,
    instruction: str,
    preserve: list[str],
) -> dict[str, Any]:
    ensure_role(principal, "admin")
    current = _question_row(supabase, question_id)
    bad = [f for f in preserve if f not in _PRESERVABLE_FIELDS]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported preserve fields: {bad}",
        )

    user_prompt = (
        "Revise the following question template. The admin's instruction is "
        "the authoritative ask; honor the preserve list strictly.\n\n"
        f"Admin instruction:\n<instruction>\n{instruction}\n</instruction>\n\n"
        f"Preserve list (do NOT change these fields): {preserve or 'none'}\n\n"
        "Current question (JSON):\n<current>\n"
        f"{json.dumps(_strip_for_prompt(current), indent=2)}\n"
        "</current>\n\n"
        "Return the revised QuestionTemplate via the submit_revised_question tool."
    )

    started = time.monotonic()
    client = _client()
    response = client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=10_000,
        output_config={"effort": "high"},
        system=_system_blocks(REVISION_SYSTEM_PROMPT),
        tools=[SUBMIT_REVISED_QUESTION_TOOL],
        tool_choice={"type": "tool", "name": "submit_revised_question"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    raw = _extract_tool_input(response, "submit_revised_question")

    # Apply preserve list, overwrite revised fields with the originals.
    for field in preserve:
        if field in current:
            raw[field] = current[field]

    # Spec §6.5: revised questions go through the same Stage-2 validators
    # so a regression on shape / taxonomy / interactive_config can't
    # silently land in the bank.
    ok, reason = _validate_stage2_question(
        {**raw, "competency_tags": raw.get("competency_tags") or current.get("competency_tags")},
        current.get("metadata", {}).get("generated_difficulty") or "mid",
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Revised question failed validation: {reason}",
        )

    parent_run_id = (current.get("metadata") or {}).get("source_generation_id")
    run_id = _record_run(
        supabase,
        stage="revision",
        input_brief={
            "question_id": question_id,
            "instruction": instruction,
            "preserve": preserve,
            "before": _strip_for_prompt(current),
        },
        output={"after": raw},
        model=GENERATION_MODEL,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        latency_ms=latency_ms,
        status_value="success",
        parent_run_id=parent_run_id,
        created_by=principal.user_id,
    )

    update_payload: dict[str, Any] = {
        "type": raw["type"],
        "prompt_template": _sanitize_text(raw["prompt_template"]),
        "variable_schema": raw.get("variable_schema") or {},
        "solver_code": raw.get("solver_code"),
        # Validated interactive_config (alias-resolved shape).
        "interactive_config": validate_interactive_config(
            raw["type"], _sanitize_text(raw.get("interactive_config"))
        ),
        "rubric": _sanitize_text(raw["rubric"]),
        "competency_tags": _filter_competency_tags(
            raw.get("competency_tags") or current.get("competency_tags") or []
        ),
        "time_limit_seconds": raw.get("time_limit_seconds"),
        "max_points": float(raw.get("max_points") or current.get("max_points") or 10),
        "metadata": {
            **(current.get("metadata") or {}),
            "last_revision_instruction": instruction,
            # Point future revisions at the latest revision run so the
            # parent_run_id chain reflects the actual lineage.
            "source_generation_id": run_id,
        },
        "updated_at": datetime.now(UTC).isoformat(),
    }
    supabase.table("question_templates").update(update_payload).eq("id", question_id).execute()

    return {
        "question_id": question_id,
        "run_id": run_id,
        "model": GENERATION_MODEL,
        "tokens_in": response.usage.input_tokens,
        "tokens_out": response.usage.output_tokens,
        "latency_ms": latency_ms,
        "revised": update_payload,
    }


def _strip_for_prompt(row: dict[str, Any]) -> dict[str, Any]:
    """Drop heavy or DB-internal fields when sending the current question to
    the model, keeps the prompt focused on user-meaningful template state."""
    return {
        k: v
        for k, v in row.items()
        if k not in {"id", "module_id", "position", "solver_language"}
    }


# -- Run lookup --------------------------------------------------------------


def get_run(supabase: Client, run_id: str) -> dict[str, Any]:
    res = (
        supabase.table("generation_runs")
        .select(
            "id, stage, status, model, tokens_in, tokens_out, latency_ms, "
            "error, parent_run_id, input_brief, output, created_at"
        )
        .eq("id", run_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation run not found.",
        )
    return rows[0]


# -- Variant preview --------------------------------------------------------


def preview_variants(
    variable_schema: dict[str, Any],
    prompt_template: str,
    seed_count: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(seed_count):
        seed = question_seed(int(datetime.now(UTC).timestamp()) + i, "preview")
        try:
            variables = sample_variables(variable_schema, seed)
            rendered = render_prompt(prompt_template, variables)
        except Exception as exc:  # render or sample failure
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Variant preview failed: {exc}",
            ) from exc
        out.append({"seed": seed, "variables": variables, "rendered_prompt": rendered})
    return out
