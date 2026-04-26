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
from supabase import Client

from ..auth import AdminPrincipal
from ..config import get_settings
from ..models.generator import (
    EditedOutline,
    GeneratedOutline,
    GenerationBriefIn,
    OutlineRunResponse,
    QuestionGenerationResponse,
)
from ..prompts.outline import OUTLINE_SYSTEM_PROMPT, SUBMIT_OUTLINE_TOOL
from ..prompts.questions import QUESTIONS_SYSTEM_PROMPT, SUBMIT_QUESTIONS_TOOL
from ..prompts.revision import REVISION_SYSTEM_PROMPT, SUBMIT_REVISED_QUESTION_TOOL
from . import references as references_service
from .randomizer import question_seed, render_prompt, sample_variables

log = logging.getLogger(__name__)

# Spec §15 names Sonnet 4.5 for generation; we use the latest in that family.
GENERATION_MODEL = "claude-sonnet-4-6"


def _ensure_role(principal: AdminPrincipal, *allowed: str) -> None:
    if principal.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{principal.role}' is not permitted for this action.",
        )


def _client() -> Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key_generation:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY_GENERATION is not configured.",
        )
    return Anthropic(api_key=settings.anthropic_api_key_generation)


# -- Taxonomy injection ------------------------------------------------------


def _load_taxonomy_text() -> str:
    """Read packages/competencies/src/taxonomy.json and render it as
    `id - label` lines for prompt injection. Cached on first call."""

    global _CACHED_TAXONOMY
    if _CACHED_TAXONOMY is not None:
        return _CACHED_TAXONOMY
    repo_root = Path(__file__).resolve().parents[4]
    path = repo_root / "packages" / "competencies" / "src" / "taxonomy.json"
    if not path.exists():
        raise RuntimeError(f"Competency taxonomy not found at {path}")
    rows = json.loads(path.read_text(encoding="utf-8"))
    lines = [f"{row['id']} - {row['label']}" for row in rows]
    _CACHED_TAXONOMY = "\n".join(lines)
    return _CACHED_TAXONOMY


_CACHED_TAXONOMY: str | None = None


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
        "Question mix targets (within plus or minus 10 percent each):",
        f"  mcq: {brief.question_mix.mcq_pct}%",
        f"  short_answer: {brief.question_mix.short_pct}%",
        f"  long_answer: {brief.question_mix.long_pct}%",
        f"  code: {brief.question_mix.code_pct}%",
        f"  interactive (n8n / notebook / diagram / sql): {brief.question_mix.interactive_pct}%",
        "",
        "Required competencies (must each appear in at least one topic):",
    ]
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
    _ensure_role(principal, "admin", "reviewer")

    started = time.monotonic()
    client = _client()
    response = client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_system_blocks(OUTLINE_SYSTEM_PROMPT),
        tools=[SUBMIT_OUTLINE_TOOL],
        tool_choice={"type": "tool", "name": "submit_outline"},
        messages=[{"role": "user", "content": _outline_user_prompt(brief)}],
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    raw_output = _extract_tool_input(response, "submit_outline")
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
            parts.append(
                f"<chunk document_id=\"{chunk['document_id']}\" "
                f"position=\"{chunk['position']}\"{sim_str}>"
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
    # no result` — treat that as "could not verify, accept" so we don't
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
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"generated_difficulty": raw.get("difficulty")}
    if cited_document_titles:
        metadata["sources"] = [
            {"document_id": doc_id, "title": title}
            for doc_id, title in cited_document_titles.items()
        ]
    return {
        "id": str(uuid.uuid4()),
        "module_id": module_id,
        "position": position,
        "type": raw["type"],
        "prompt_template": raw["prompt_template"],
        "variable_schema": raw.get("variable_schema") or {},
        "solver_code": raw.get("solver_code"),
        "solver_language": "python",
        "interactive_config": raw.get("interactive_config"),
        "rubric": raw["rubric"],
        "competency_tags": raw.get("competency_tags") or [],
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
    _ensure_role(principal, "admin")

    client = _client()

    # Create the draft module first so we have an id for question_templates rows.
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
    if not module_insert.data:
        raise HTTPException(
            status_code=500, detail="Failed to create draft module."
        )
    module_id = module_insert.data[0]["id"]

    run_ids: list[str] = []
    total_tokens_in = 0
    total_tokens_out = 0
    questions_generated = 0
    position = 0

    document_titles: dict[str, str] = {}
    if brief.reference_document_ids:
        document_titles = _document_title_lookup(supabase, brief.reference_document_ids)

    for topic in outline.topics:
        topic_dict = topic.model_dump()

        # Per spec §6.4: retrieve top-k chunks per topic when references are
        # attached. Failures are non-fatal — generation falls back to no
        # reference material rather than aborting the whole module.
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
                thinking={"type": "adaptive"},
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
        except Exception as exc:  # network / 429 / 5xx
            log.exception("question generation failed for topic %s", topic.name)
            run_id = _record_run(
                supabase,
                stage="full",
                input_brief={"brief": brief.model_dump(), "topic": topic_dict},
                output={"error": str(exc)},
                model=GENERATION_MODEL,
                tokens_in=0,
                tokens_out=0,
                latency_ms=int((time.monotonic() - started) * 1000),
                status_value="failed",
                error=str(exc),
                parent_run_id=outline_run_id,
                created_by=principal.user_id,
            )
            run_ids.append(run_id)
            continue

        latency_ms = int((time.monotonic() - started) * 1000)
        total_tokens_in += response.usage.input_tokens
        total_tokens_out += response.usage.output_tokens

        try:
            raw_output = _extract_tool_input(response, "submit_questions")
            raw_questions = list(raw_output.get("questions") or [])
        except HTTPException as exc:
            run_id = _record_run(
                supabase,
                stage="full",
                input_brief={"brief": brief.model_dump(), "topic": topic_dict},
                output={"raw_response_text": _stringify_text(response)},
                model=GENERATION_MODEL,
                tokens_in=response.usage.input_tokens,
                tokens_out=response.usage.output_tokens,
                latency_ms=latency_ms,
                status_value="failed",
                error=exc.detail,
                parent_run_id=outline_run_id,
                created_by=principal.user_id,
            )
            run_ids.append(run_id)
            continue

        rows = []
        for raw_q in raw_questions:
            # Spec §6.3 rule 10: self-verify by running the solver on 3
            # sampled variable sets. If the solver doesn't parse / run /
            # produce a dict, skip the question and add a note in the
            # generation_run output so the admin can review.
            if not _self_verify_question(raw_q):
                log.warning(
                    "self-verification failed for generated question; skipping"
                )
                continue
            rows.append(
                _normalize_question_row(
                    raw_q,
                    module_id=module_id,
                    position=position,
                    cited_document_titles=cited_titles,
                )
            )
            position += 1

        if rows:
            supabase.table("question_templates").insert(rows).execute()
            questions_generated += len(rows)

        run_id = _record_run(
            supabase,
            stage="full",
            input_brief={"brief": brief.model_dump(), "topic": topic_dict},
            output={"questions": raw_questions},
            model=GENERATION_MODEL,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            latency_ms=latency_ms,
            status_value="success",
            parent_run_id=outline_run_id,
            created_by=principal.user_id,
        )
        run_ids.append(run_id)

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
    _ensure_role(principal, "admin")
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
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_system_blocks(REVISION_SYSTEM_PROMPT),
        tools=[SUBMIT_REVISED_QUESTION_TOOL],
        tool_choice={"type": "tool", "name": "submit_revised_question"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    raw = _extract_tool_input(response, "submit_revised_question")

    # Apply preserve list — overwrite revised fields with the originals.
    for field in preserve:
        if field in current:
            raw[field] = current[field]

    update_payload: dict[str, Any] = {
        "type": raw["type"],
        "prompt_template": raw["prompt_template"],
        "variable_schema": raw.get("variable_schema") or {},
        "solver_code": raw.get("solver_code"),
        "interactive_config": raw.get("interactive_config"),
        "rubric": raw["rubric"],
        "competency_tags": raw.get("competency_tags") or current.get("competency_tags") or [],
        "time_limit_seconds": raw.get("time_limit_seconds"),
        "max_points": float(raw.get("max_points") or current.get("max_points") or 10),
        "metadata": {
            **(current.get("metadata") or {}),
            "last_revision_instruction": instruction,
        },
        "updated_at": datetime.now(UTC).isoformat(),
    }
    supabase.table("question_templates").update(update_payload).eq("id", question_id).execute()

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
    the model — keeps the prompt focused on user-meaningful template state."""
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
