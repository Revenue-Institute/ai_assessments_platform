"""React Flow diagram grading (spec §7.4).

Structural mode: graph isomorphism with fuzzy node-label matching. We
canonicalize nodes by (type, normalized_label), match candidate nodes to
reference nodes greedily by best fuzzy score, then check that every edge
in the reference graph has a corresponding candidate edge between the
matched nodes.

AI narrative mode (spec §7.4: 'Claude reviews the structure + candidate
written rationale against rubric'): Claude Sonnet 4.6 scores the
diagram JSON + the candidate's rationale text. `both` mode combines
structural and narrative; `ai_narrative` is narrative-only."""

from __future__ import annotations

import json as _json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

from .narrative_grader import (
    grade as _narrative_grade_call,
)
from .narrative_grader import (
    serialize_criteria as _criteria_summary,
)

log = logging.getLogger(__name__)

LABEL_MATCH_THRESHOLD = 0.6


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def _label_similarity(a: str | None, b: str | None) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _node_summary(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "type": (node.get("type") or "default").lower(),
        "label": _norm(node.get("label") or (node.get("data") or {}).get("label")),
    }


def _edge_summary(edge: dict[str, Any]) -> tuple[str, str]:
    return (str(edge.get("source")), str(edge.get("target")))


def match_nodes(
    candidate_nodes: list[dict[str, Any]],
    reference_nodes: list[dict[str, Any]],
) -> tuple[dict[str, str], list[str], list[str]]:
    """Greedy best-similarity match. Returns (mapping ref_id → candidate_id,
    reference_unmatched, candidate_unmatched)."""

    cand = [_node_summary(n) for n in candidate_nodes]
    ref = [_node_summary(n) for n in reference_nodes]

    # Score every (ref, candidate) pair, then assign in descending order.
    pairs: list[tuple[float, int, int]] = []
    for i, r in enumerate(ref):
        for j, c in enumerate(cand):
            type_score = 1.0 if r["type"] == c["type"] else 0.5
            label_score = _label_similarity(r["label"], c["label"])
            pairs.append((label_score * type_score, i, j))

    pairs.sort(reverse=True)
    used_ref: set[int] = set()
    used_cand: set[int] = set()
    mapping: dict[str, str] = {}
    for score, i, j in pairs:
        if score < LABEL_MATCH_THRESHOLD:
            break
        if i in used_ref or j in used_cand:
            continue
        used_ref.add(i)
        used_cand.add(j)
        mapping[str(ref[i]["id"])] = str(cand[j]["id"])

    ref_unmatched = [str(r["id"]) for k, r in enumerate(ref) if k not in used_ref]
    cand_unmatched = [str(c["id"]) for k, c in enumerate(cand) if k not in used_cand]
    return mapping, ref_unmatched, cand_unmatched


def grade_diagram_attempt(
    *,
    submission: dict[str, Any],
    config: dict[str, Any],
    max_points: float,
    rubric: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score the candidate's React Flow JSON against the question's
    reference_structure. Returns an attempts-row update payload.

    `submission` shape (spec §7.4):
        - structural-only modes: {nodes: [...], edges: [...]}
        - ai_narrative / both: {diagram: {nodes, edges}, rationale: str}
    Both shapes are accepted; we unwrap `diagram` when present and
    default rationale to empty string when missing."""

    grading_mode = (config.get("grading_mode") or "structural").lower()

    # Accept both submission shapes. The candidate UI is expected to
    # add a rationale field for narrative modes (lands in another
    # agent's scope); until it does, an empty string is a valid default.
    if isinstance(submission.get("diagram"), dict):
        diagram = submission["diagram"]
        rationale_text = str(submission.get("rationale") or "")
    else:
        diagram = submission
        rationale_text = str(submission.get("rationale") or "")

    reference = config.get("reference_structure") or {}
    ref_nodes = list(reference.get("nodes") or [])
    ref_edges = list(reference.get("edges") or [])

    cand_nodes = list(diagram.get("nodes") or [])
    cand_edges = list(diagram.get("edges") or [])

    structural_pct: float | None = None
    structural_bits: list[str] = []
    missing_edges: list[tuple[str, str]] = []

    if grading_mode in ("structural", "both"):
        if not ref_nodes:
            if grading_mode == "structural":
                return {
                    "score": 0.0,
                    "score_rationale": (
                        "No reference_structure on the question; cannot grade."
                    ),
                    "scorer_model": "diagram-structural",
                    "scorer_version": "1",
                }
        else:
            mapping, ref_unmatched, _cand_unmatched = match_nodes(
                cand_nodes, ref_nodes
            )
            cand_edge_set = {_edge_summary(e) for e in cand_edges}
            matched_edges = 0
            for re_edge in ref_edges:
                ref_pair = _edge_summary(re_edge)
                if ref_pair[0] in mapping and ref_pair[1] in mapping:
                    mapped = (mapping[ref_pair[0]], mapping[ref_pair[1]])
                    if mapped in cand_edge_set:
                        matched_edges += 1
                        continue
                missing_edges.append(ref_pair)

            node_pct = (
                (len(ref_nodes) - len(ref_unmatched)) / len(ref_nodes)
                if ref_nodes
                else 1.0
            )
            edge_pct = (
                (matched_edges / len(ref_edges)) if ref_edges else 1.0
            )
            structural_pct = (node_pct + edge_pct) / 2 if ref_edges else node_pct

            structural_bits.append(
                f"Matched {len(ref_nodes) - len(ref_unmatched)}/{len(ref_nodes)} "
                "reference nodes"
            )
            if ref_edges:
                structural_bits.append(
                    f"matched {matched_edges}/{len(ref_edges)} reference edges"
                )
            if ref_unmatched:
                structural_bits.append(
                    f"{len(ref_unmatched)} expected node(s) had no match"
                )
            if missing_edges:
                structural_bits.append(
                    f"{len(missing_edges)} expected edge(s) missing"
                )

    narrative: dict[str, Any] | None = None
    if grading_mode in ("ai_narrative", "both"):
        narrative = _narrative_grade(
            diagram=diagram,
            rationale_text=rationale_text,
            rubric=rubric or {},
        )

    if grading_mode == "ai_narrative":
        if narrative is None:
            return {
                "score": 0.0,
                "score_rationale": (
                    "Narrative grading unavailable; admin can rescore once "
                    "Anthropic key is configured."
                ),
                "scorer_model": "diagram-narrative",
                "scorer_version": "1",
            }
        overall = float(narrative.get("pct") or 0.0)
        scorer_model = "diagram-narrative"
        rationale_bits = [narrative.get("rationale") or "Narrative graded."]
    elif grading_mode == "both":
        narr_pct = (
            float(narrative.get("pct"))
            if narrative is not None and isinstance(narrative.get("pct"), (int, float))
            else None
        )
        if structural_pct is None and narr_pct is None:
            return {
                "score": 0.0,
                "score_rationale": "Could not compute structural or narrative score.",
                "scorer_model": "diagram-structural+narrative",
                "scorer_version": "1",
            }
        if structural_pct is not None and narr_pct is not None:
            overall = 0.5 * structural_pct + 0.5 * narr_pct
        else:
            overall = structural_pct if structural_pct is not None else narr_pct or 0.0
        scorer_model = "diagram-structural+narrative"
        rationale_bits = list(structural_bits)
        if narrative is not None and narrative.get("rationale"):
            rationale_bits.append(f"narrative: {narrative['rationale']}")
    else:
        overall = structural_pct if structural_pct is not None else 0.0
        scorer_model = "diagram-structural"
        rationale_bits = list(structural_bits) or ["Structural grading complete."]

    overall = max(0.0, min(1.0, overall))
    score = round(overall * max_points, 2)
    return {
        "score": score,
        "score_rationale": ". ".join(rationale_bits) + ".",
        "scorer_model": scorer_model,
        "scorer_version": "1",
    }


def _narrative_grade(
    *,
    diagram: dict[str, Any],
    rationale_text: str,
    rubric: dict[str, Any],
) -> dict[str, Any] | None:
    """Score the diagram JSON + candidate's rationale text against the
    rubric. Returns {pct, rationale} or None on any failure. Shared call
    shape lives in services.narrative_grader."""

    system = (
        "You are reviewing a process diagram (React Flow JSON) plus "
        "the candidate's written rationale. Score against the rubric "
        "criteria below. Respond with a single JSON object: "
        '{"pct": <float 0..1>, "rationale": "<one or two sentences>"}. '
        "No prose outside the JSON."
    )
    user = (
        "Rubric criteria:\n"
        f"{_criteria_summary(rubric)}\n\n"
        "Diagram JSON:\n"
        f"{_json.dumps(diagram, default=str)[:8000]}\n\n"
        "Candidate rationale:\n"
        f"{(rationale_text or '')[:4000]}"
    )
    return _narrative_grade_call(
        subject_label="diagram", system=system, user=user
    )
