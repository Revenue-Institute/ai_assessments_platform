"""React Flow diagram grading (spec §7.4).

Structural mode: graph isomorphism with fuzzy node-label matching. We
canonicalize nodes by (type, normalized_label), match candidate nodes to
reference nodes greedily by best fuzzy score, then check that every edge
in the reference graph has a corresponding candidate edge between the
matched nodes.

Spec also calls for ai_narrative + both modes; those go through the
existing scoring orchestrator's rubric_ai path. Only structural grading
lives here."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

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
) -> dict[str, Any]:
    """Score the candidate's React Flow JSON against the question's
    reference_structure. Returns an attempts-row update payload."""

    reference = config.get("reference_structure") or {}
    ref_nodes = list(reference.get("nodes") or [])
    ref_edges = list(reference.get("edges") or [])

    cand_nodes = list(submission.get("nodes") or [])
    cand_edges = list(submission.get("edges") or [])

    if not ref_nodes:
        return {
            "score": 0.0,
            "score_rationale": "No reference_structure on the question; cannot grade.",
            "scorer_model": "diagram-structural",
            "scorer_version": "1",
        }

    mapping, ref_unmatched, _cand_unmatched = match_nodes(cand_nodes, ref_nodes)

    # Edge match: a reference edge counts as matched when both endpoints
    # have a node in the mapping AND a candidate edge exists between the
    # mapped node ids.
    cand_edge_set = {_edge_summary(e) for e in cand_edges}
    matched_edges = 0
    missing_edges: list[tuple[str, str]] = []
    for re_edge in ref_edges:
        ref_pair = _edge_summary(re_edge)
        if ref_pair[0] in mapping and ref_pair[1] in mapping:
            mapped = (mapping[ref_pair[0]], mapping[ref_pair[1]])
            if mapped in cand_edge_set:
                matched_edges += 1
                continue
        missing_edges.append(ref_pair)

    node_pct = (
        (len(ref_nodes) - len(ref_unmatched)) / len(ref_nodes) if ref_nodes else 1.0
    )
    edge_pct = (matched_edges / len(ref_edges)) if ref_edges else 1.0
    overall = (node_pct + edge_pct) / 2 if ref_edges else node_pct
    score = round(overall * max_points, 2)

    rationale_bits = [
        f"Matched {len(ref_nodes) - len(ref_unmatched)}/{len(ref_nodes)} reference nodes",
    ]
    if ref_edges:
        rationale_bits.append(
            f"matched {matched_edges}/{len(ref_edges)} reference edges"
        )
    if ref_unmatched:
        rationale_bits.append(
            f"{len(ref_unmatched)} expected node(s) had no match"
        )
    if missing_edges:
        rationale_bits.append(f"{len(missing_edges)} expected edge(s) missing")

    return {
        "score": score,
        "score_rationale": ". ".join(rationale_bits) + ".",
        "scorer_model": "diagram-structural",
        "scorer_version": "1",
    }
