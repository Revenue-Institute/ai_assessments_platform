"""n8n workspace provisioning + structural grading (spec §7.2).

v1 scope: a shared self-hosted n8n instance with admin API access.
- Provision: POST /workflows with starter_workflow → get a workflow_id.
- Embed URL: ${N8N_HOST}/workflow/{id}. Candidate edits in the iframe.
- Export on submit: GET /workflows/:id → save the JSON as the artifact.
- Grade: structural diff against reference_workflow (positions / ids
  stripped, fuzzy node match by type + name + parameter signature, edge
  set equality after the node mapping).

Behavioral execution diff (spec §7.2 'compare execution outputs to
reference execution outputs') is on by default; failures fall back to
structural-only so a flaky n8n instance doesn't penalize candidates.

Narrative rubric pass (spec §7.2 'Claude reviews the candidate's
workflow JSON against the rubric for style criteria') is invoked when
the rubric has scoring_mode=rubric_ai or any criterion with a
positive weight. Failures (missing Anthropic key, network error)
fall through silently and the structural+behavioral score stands.

Fails soft when N8N_HOST or N8N_ADMIN_API_KEY are unset (returns 503 on
the embed endpoint, leaves auto-grade null on submit so an admin
rescore can pick it up later)."""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import httpx
from fastapi import HTTPException, status

from ..config import get_settings

NARRATIVE_MODEL = "claude-sonnet-4-6"
NARRATIVE_VERSION = "1"

log = logging.getLogger(__name__)

LABEL_MATCH_THRESHOLD = 0.55


@dataclass(slots=True, frozen=True)
class N8nProvisionResult:
    workflow_id: str
    embed_url: str


def _headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.n8n_admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="n8n runner is not configured (N8N_ADMIN_API_KEY missing).",
        )
    return {
        "X-N8N-API-KEY": settings.n8n_admin_api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    settings = get_settings()
    if not settings.n8n_host:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="n8n runner is not configured (N8N_HOST missing).",
        )
    return settings.n8n_host.rstrip("/")


# -- API operations --------------------------------------------------------


def provision_workspace(
    *,
    starter_workflow: dict[str, Any] | None,
    title: str,
    credentials_provided: list[str] | None = None,
) -> N8nProvisionResult:
    """Create a fresh workflow on the shared n8n instance and return the
    embed URL the candidate's iframe should load.

    Return shape (contract for callers in services/attempts.py):
        N8nProvisionResult(workflow_id, embed_url)
    The caller is expected to persist `workflow_id` on the attempt row so
    teardown via `cleanup_workflow(workflow_id)` can run from
    complete_assignment / submit_answer without re-deriving it from the
    embed URL.

    `credentials_provided` (spec §5.2 N8nConfig.credentials_provided): for
    each credential name, attempt to create a stubbed httpHeaderAuth
    credential against the n8n REST API so the candidate's nodes can save
    without filling in real auth. Failures are logged and skipped, never
    fatal: missing endpoints across n8n versions shouldn't block
    provisioning."""

    base = _base_url()
    payload = dict(starter_workflow or {})
    payload.setdefault("name", title or "RI Assessment Workflow")
    payload.setdefault("nodes", [])
    payload.setdefault("connections", {})
    payload.setdefault("settings", {})
    # n8n requires `active: false` on creation; we leave the workflow inactive.
    payload["active"] = False

    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(
                f"{base}/api/v1/workflows", headers=_headers(), json=payload
            )
            res.raise_for_status()
            body = res.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"n8n returned {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"n8n provision failure: {exc}",
        ) from exc

    workflow_id = str(body.get("id") or body.get("data", {}).get("id") or "")
    if not workflow_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="n8n did not return a workflow id.",
        )

    # Stub credentials so the candidate's nodes can save without real auth.
    # Per spec §5.2, `credentials_provided` is a list of credential type
    # names. We create one mock httpHeaderAuth credential per name. n8n
    # accepts empty values on this type, that gives us a placeholder the
    # candidate can attach without prompting for real secrets.
    for cred_name in credentials_provided or []:
        _stub_credential(cred_name)

    return N8nProvisionResult(
        workflow_id=workflow_id,
        embed_url=f"{base}/workflow/{workflow_id}",
    )


def _stub_credential(name: str) -> None:
    """Best-effort creation of a placeholder credential. Different n8n
    versions expose /api/v1/credentials with slightly different schemas;
    on any failure we log WARN and move on, the candidate can still build
    the workflow without these stubs."""

    base = _base_url()
    payload = {
        "name": f"ri-stub-{name}",
        "type": "httpHeaderAuth",
        "data": {"name": "", "value": ""},
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.post(
                f"{base}/api/v1/credentials",
                headers=_headers(),
                json=payload,
            )
            if res.status_code >= 400:
                log.warning(
                    "n8n stub credential %r failed (%s): %s",
                    name,
                    res.status_code,
                    res.text[:200],
                )
    except Exception as exc:
        log.warning("n8n stub credential %r failed: %s", name, exc)


def export_workflow(workflow_id: str) -> dict[str, Any]:
    base = _base_url()
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.get(
                f"{base}/api/v1/workflows/{workflow_id}", headers=_headers()
            )
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"n8n export {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"n8n export failure: {exc}",
        ) from exc


def delete_workflow(workflow_id: str) -> None:
    """Best-effort teardown. We log on failure but don't raise, leaving
    a stale workflow on the n8n instance is preferable to failing the
    candidate's submission."""

    if not workflow_id:
        return
    try:
        base = _base_url()
        with httpx.Client(timeout=15.0) as client:
            client.delete(
                f"{base}/api/v1/workflows/{workflow_id}", headers=_headers()
            )
    except HTTPException as exc:
        # Configuration error (host / api key missing). Swallow: teardown
        # should never crash the calling submission flow.
        log.warning("n8n delete_workflow %s skipped: %s", workflow_id, exc.detail)
    except Exception as exc:
        log.warning("n8n delete_workflow %s failed: %s", workflow_id, exc)


def cleanup_workflow(workflow_id: str | None) -> None:
    """Idempotent teardown entry point for services/attempts.py callers.

    Accepts None / empty string (no-op), swallows HTTPException raised by
    `_headers` / `_base_url` when n8n isn't configured, and swallows any
    network failure from the underlying DELETE call. Safe to call from
    complete_assignment and submit_answer without try/except wrapping at
    the call site."""

    if not workflow_id:
        return
    try:
        delete_workflow(workflow_id)
    except Exception as exc:
        # delete_workflow already swallows everything; this is belt and
        # suspenders for the contract: cleanup_workflow never raises.
        log.warning("n8n cleanup_workflow %s failed: %s", workflow_id, exc)


def execute_workflow(
    workflow_id: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """POST /workflows/:id/execute. Returns the execution data n8n streams
    back. Used for the optional behavioral diff."""

    base = _base_url()
    try:
        with httpx.Client(timeout=120.0) as client:
            res = client.post(
                f"{base}/api/v1/workflows/{workflow_id}/execute",
                headers=_headers(),
                json=payload or {},
            )
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"n8n execute {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"n8n execute failure: {exc}",
        ) from exc


# -- Structural grading ----------------------------------------------------


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).split()).lower()


def _node_signature(node: dict[str, Any]) -> dict[str, Any]:
    """Drop ids + positions; keep the structural attributes that matter:
    node `type`, `name`, and a stable parameters representation."""

    params = node.get("parameters") or {}
    return {
        "raw_id": node.get("id"),
        "raw_name": node.get("name"),
        "type": _norm(node.get("type")),
        "name": _norm(node.get("name")),
        # parameters are typically deeply nested, we hash the flattened
        # JSON to compare structure without comparing positions.
        "params_keys": sorted(params.keys()) if isinstance(params, dict) else [],
    }


def _node_score(a: dict[str, Any], b: dict[str, Any]) -> float:
    type_score = 1.0 if a["type"] == b["type"] else 0.3
    name_score = SequenceMatcher(None, a["name"], b["name"]).ratio()
    # Parameter-key overlap: how many of the reference node's keys does
    # the candidate node have?
    ref_keys = set(b["params_keys"])
    cand_keys = set(a["params_keys"])
    param_score = (
        len(ref_keys & cand_keys) / len(ref_keys) if ref_keys else 1.0
    )
    return type_score * (0.5 * name_score + 0.5 * param_score)


def _connection_pairs(
    workflow: dict[str, Any], name_to_id: dict[str, str] | None = None
) -> set[tuple[str, str]]:
    """n8n stores connections as
    `connections: {source_node_name: {main: [[{node: target_name, ...}]]}}`.
    We flatten to a set of (source_id, target_id) using the optional
    name→id mapping when grading; otherwise we use names directly."""

    pairs: set[tuple[str, str]] = set()
    conns = workflow.get("connections") or {}
    for source_name, by_kind in conns.items():
        if not isinstance(by_kind, dict):
            continue
        outputs = by_kind.get("main") or []
        for output_pin in outputs:
            for target in output_pin or []:
                target_name = target.get("node") if isinstance(target, dict) else None
                if not target_name:
                    continue
                src = (
                    name_to_id.get(_norm(source_name), _norm(source_name))
                    if name_to_id
                    else _norm(source_name)
                )
                tgt = (
                    name_to_id.get(_norm(target_name), _norm(target_name))
                    if name_to_id
                    else _norm(target_name)
                )
                pairs.add((src, tgt))
    return pairs


def grade_n8n_attempt(
    *,
    submission: dict[str, Any],
    config: dict[str, Any],
    max_points: float,
    rubric: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reference = config.get("reference_workflow") or {}
    ref_nodes = list(reference.get("nodes") or [])
    cand_nodes = list(submission.get("nodes") or [])

    if not ref_nodes:
        return {
            "score": 0.0,
            "score_rationale": "No reference_workflow on the question; cannot grade.",
            "scorer_model": "n8n-structural",
            "scorer_version": "1",
        }

    cand_sigs = [_node_signature(n) for n in cand_nodes]
    ref_sigs = [_node_signature(n) for n in ref_nodes]

    # Greedy best-fuzzy matching (same shape as diagram_runner).
    pairs: list[tuple[float, int, int]] = []
    for i, ref in enumerate(ref_sigs):
        for j, cand in enumerate(cand_sigs):
            pairs.append((_node_score(cand, ref), i, j))
    pairs.sort(reverse=True)

    used_ref: set[int] = set()
    used_cand: set[int] = set()
    name_mapping: dict[str, str] = {}  # ref name → candidate name (both normalized)
    for score_, i, j in pairs:
        if score_ < LABEL_MATCH_THRESHOLD:
            break
        if i in used_ref or j in used_cand:
            continue
        used_ref.add(i)
        used_cand.add(j)
        name_mapping[ref_sigs[i]["name"]] = cand_sigs[j]["name"]

    matched_nodes = len(used_ref)
    missing_node_count = len(ref_sigs) - matched_nodes

    cand_pairs = _connection_pairs(submission)
    ref_pairs = _connection_pairs(reference)
    matched_edges = 0
    missing_edges: list[tuple[str, str]] = []
    for ref_pair in ref_pairs:
        mapped = (
            name_mapping.get(ref_pair[0], ref_pair[0]),
            name_mapping.get(ref_pair[1], ref_pair[1]),
        )
        if mapped in cand_pairs:
            matched_edges += 1
        else:
            missing_edges.append(ref_pair)

    # Required-nodes / required-connections checks from the spec config:
    # we treat them as a hard floor, a missing required item drops the score
    # to 0 to mirror "the candidate didn't build the workflow we asked for".
    required_nodes = set(_norm(n) for n in (config.get("required_nodes") or []))
    if required_nodes and not required_nodes.issubset(
        {sig["type"] for sig in cand_sigs}
    ):
        missing = required_nodes - {sig["type"] for sig in cand_sigs}
        return {
            "score": 0.0,
            "score_rationale": (
                "Required node types missing: " + ", ".join(sorted(missing))
            ),
            "scorer_model": "n8n-structural",
            "scorer_version": "1",
        }

    required_conns = config.get("required_connections") or []
    for required in required_conns:
        if not isinstance(required, dict):
            continue
        from_node = _norm(required.get("from"))
        to_node = _norm(required.get("to"))
        from_mapped = name_mapping.get(from_node, from_node)
        to_mapped = name_mapping.get(to_node, to_node)
        if (from_mapped, to_mapped) not in cand_pairs:
            return {
                "score": 0.0,
                "score_rationale": (
                    f"Required connection missing: {from_node} → {to_node}"
                ),
                "scorer_model": "n8n-structural",
                "scorer_version": "1",
            }

    node_pct = matched_nodes / len(ref_sigs) if ref_sigs else 1.0
    edge_pct = matched_edges / len(ref_pairs) if ref_pairs else 1.0
    overall = (node_pct + edge_pct) / 2 if ref_pairs else node_pct

    # Behavioral diff (spec §7.2): when the question pins an
    # `expected_execution_output`, provision the candidate workflow on the
    # shared n8n instance, execute it once, and award a 10% bonus on a
    # match (clamped at 1.0 overall). On by default, per spec; failures
    # of any kind fall through to structural-only, the candidate isn't
    # penalized for sandbox outages.
    behavioral_match: bool | None = None
    expected_output = config.get("expected_execution_output")
    if expected_output is not None:
        try:
            provisioned = provision_workspace(
                starter_workflow=submission,
                title="behavioral-diff",
            )
            try:
                result = execute_workflow(
                    provisioned.workflow_id,
                    config.get("execution_payload") or {},
                )
                actual = _last_node_output(result)
                behavioral_match = _outputs_equivalent(actual, expected_output)
            finally:
                cleanup_workflow(provisioned.workflow_id)
        except Exception as exc:
            log.info("n8n behavioral diff skipped: %s", exc)
            behavioral_match = None
    if behavioral_match is True:
        overall = min(1.0, overall + 0.10)

    # Narrative rubric pass (spec §7.2): Claude reviews the candidate's
    # workflow JSON for style criteria (error handling, node naming,
    # expression quality). Skipped silently when the rubric has no
    # criteria or the Anthropic key is unavailable.
    narrative: dict[str, Any] | None = None
    if _rubric_wants_narrative(rubric):
        narrative = _narrative_grade(submission, rubric or {})
    if narrative is not None:
        narr_pct = narrative.get("pct")
        if isinstance(narr_pct, (int, float)):
            # Combine: structural+behavioral overall already represents
            # 70% of the signal; narrative adds 30% blended in. This keeps
            # the existing structural ceiling intact when narrative is
            # absent and gives style criteria meaningful weight when
            # present.
            overall = max(0.0, min(1.0, 0.7 * overall + 0.3 * float(narr_pct)))

    score = round(overall * max_points, 2)
    rationale_bits = [
        f"Matched {matched_nodes}/{len(ref_sigs)} reference nodes",
    ]
    if ref_pairs:
        rationale_bits.append(
            f"matched {matched_edges}/{len(ref_pairs)} reference connections"
        )
    if missing_node_count:
        rationale_bits.append(f"{missing_node_count} expected node(s) missing")
    if missing_edges:
        rationale_bits.append(f"{len(missing_edges)} expected connection(s) missing")
    if behavioral_match is True:
        rationale_bits.append("execution output matched expected (+10%)")
    elif behavioral_match is False:
        rationale_bits.append("execution output did not match expected")
    if narrative is not None and narrative.get("rationale"):
        rationale_bits.append(f"narrative: {narrative['rationale']}")

    return {
        "score": score,
        "score_rationale": ". ".join(rationale_bits) + ".",
        "scorer_model": (
            "n8n-structural+narrative" if narrative is not None else "n8n-structural"
        ),
        "scorer_version": "1",
    }


def _rubric_wants_narrative(rubric: dict[str, Any] | None) -> bool:
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


def _narrative_grade(
    workflow_json: dict[str, Any], rubric: dict[str, Any]
) -> dict[str, Any] | None:
    """Call Claude Sonnet 4.6 to score the candidate's workflow JSON
    against the rubric's narrative criteria. Returns
    {pct: float in [0,1], rationale: str} on success, None on any failure
    (missing API key, network error, malformed model response). Never
    raises: the structural score is authoritative when this is absent."""

    settings = get_settings()
    api_key = settings.anthropic_api_key_scoring
    if not api_key:
        log.warning("n8n narrative grade skipped: ANTHROPIC_API_KEY_SCORING unset")
        return None
    try:
        from anthropic import Anthropic  # type: ignore[import-not-found]
    except ImportError:
        log.warning("n8n narrative grade skipped: anthropic SDK not installed")
        return None

    try:
        client = Anthropic(api_key=api_key)
        criteria_summary = _json.dumps(rubric.get("criteria") or [], indent=2)[:4000]
        workflow_summary = _json.dumps(workflow_json, default=str)[:12000]
        system = (
            "You are reviewing an n8n workflow JSON for style criteria "
            "(error handling, node naming, expression quality). Respond "
            "with a single JSON object: "
            '{"pct": <float 0..1>, "rationale": "<one or two sentences>"}. '
            "No prose outside the JSON."
        )
        user = (
            "Rubric criteria:\n"
            f"{criteria_summary}\n\n"
            "Candidate workflow JSON:\n"
            f"{workflow_summary}"
        )
        msg = client.messages.create(
            model=NARRATIVE_MODEL,
            max_tokens=512,
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
        # Tolerate fenced code blocks.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        parsed = _json.loads(text)
        pct = float(parsed.get("pct") or 0.0)
        pct = max(0.0, min(1.0, pct))
        return {"pct": pct, "rationale": str(parsed.get("rationale") or "")[:300]}
    except Exception as exc:
        log.warning("n8n narrative grade failed: %s", exc)
        return None


def _last_node_output(execution_result: dict[str, Any]) -> Any:
    """Best-effort extraction of the last node's output from an n8n
    execution payload. n8n's shape varies across versions; we walk the
    common keys and stop at whatever resolves first."""

    data = execution_result.get("data") or execution_result
    result_data = data.get("resultData") or data
    run_data = result_data.get("runData") or {}
    if not isinstance(run_data, dict) or not run_data:
        return data
    last_node = list(run_data.keys())[-1]
    runs = run_data.get(last_node) or []
    if not runs:
        return None
    final = runs[-1]
    return (
        ((final.get("data") or {}).get("main") or [None])[0]
        if isinstance(final, dict)
        else final
    )


def _outputs_equivalent(actual: Any, expected: Any) -> bool:
    """Stable JSON comparison: round-trip through json.dumps with sorted
    keys so dict ordering doesn't matter. Strings are stripped to tolerate
    trailing newlines from n8n nodes."""

    def _normalize(v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, dict):
            return {k: _normalize(v[k]) for k in sorted(v)}
        if isinstance(v, list):
            return [_normalize(x) for x in v]
        return v

    return _json.dumps(_normalize(actual)) == _json.dumps(_normalize(expected))
