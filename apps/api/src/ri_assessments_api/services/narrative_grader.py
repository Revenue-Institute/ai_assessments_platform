"""Shared narrative-grading helper (spec §11.4 rubric_ai mode).

Three runners (code, n8n, diagram) call Claude with the same shape:
look at the candidate's submission plus the rubric criteria, return
{pct: 0..1, rationale: str}. Before this module the three runners each
carried their own copy of the API-key check, JSON-parse, fenced-block
strip, and pct clamp. They are now one function.

The caller owns the system + user prompt because the framing is
subject-specific (code language, workflow JSON, diagram + rationale),
but the request shape, model, parse, and error handling are uniform."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)

# Hoisted from the runners that each named this NARRATIVE_MODEL. Same
# model as services/scoring.py SCORING_MODEL by design (both call Claude
# Sonnet 4.6); they're declared here separately because the narrative
# grader has different prompt + parse expectations than the rubric
# scorer in services/scoring.py.
NARRATIVE_MODEL = "claude-sonnet-4-6"
NARRATIVE_MAX_TOKENS = 512
# Max chars we pass into the model. Bigger than this almost never helps
# the model and risks hitting context limits with long rubrics.
RUBRIC_CRITERIA_LIMIT = 4000


def serialize_criteria(rubric: dict[str, Any] | None) -> str:
    """Render the rubric criteria as truncated JSON for the user prompt."""
    return json.dumps((rubric or {}).get("criteria") or [], indent=2)[
        :RUBRIC_CRITERIA_LIMIT
    ]


def rubric_wants_narrative(rubric: dict[str, Any] | None) -> bool:
    """True when the rubric calls for an AI narrative grade (either
    explicit rubric_ai scoring_mode, or any criterion with positive
    weight). Was triplicated as `_rubric_wants_narrative` in code_runner,
    n8n_runner, and diagram_runner; same body, same return."""

    if not rubric:
        return False
    if (rubric.get("scoring_mode") or "").lower() == "rubric_ai":
        return True
    for c in rubric.get("criteria") or []:
        try:
            if float(c.get("weight") or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def grade(
    *,
    subject_label: str,
    system: str,
    user: str,
) -> dict[str, Any] | None:
    """Call Claude with the given system + user prompts and parse the
    canonical {pct, rationale} response. Returns None on any failure
    (missing API key, missing SDK, network error, malformed model
    output). Never raises: callers fall back to whatever non-narrative
    score they computed first.

    `subject_label` is used only for log lines so a triage of "narrative
    grade skipped" entries can tell code/n8n/diagram apart."""

    settings = get_settings()
    api_key = settings.anthropic_api_key_scoring
    if not api_key:
        log.warning(
            "%s narrative grade skipped: ANTHROPIC_API_KEY_SCORING unset",
            subject_label,
        )
        return None
    try:
        from anthropic import Anthropic  # type: ignore[import-not-found]
    except ImportError:
        log.warning(
            "%s narrative grade skipped: anthropic SDK not installed",
            subject_label,
        )
        return None

    try:
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=NARRATIVE_MODEL,
            max_tokens=NARRATIVE_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "") or ""
        text = text.strip()
        if not text:
            return None
        # Tolerate fenced code blocks (the model sometimes wraps the
        # JSON in ```json ... ``` despite the prompt's "no prose").
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        parsed = json.loads(text)
        pct = float(parsed.get("pct") or 0.0)
        pct = max(0.0, min(1.0, pct))
        return {"pct": pct, "rationale": str(parsed.get("rationale") or "")[:300]}
    except Exception as exc:
        log.warning("%s narrative grade failed: %s", subject_label, exc)
        return None
