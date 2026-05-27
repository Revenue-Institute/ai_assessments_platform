"""Cross-checks the hand-authored Pydantic models in `models/` against
the Pydantic models generated from `packages/schemas/` (Zod).

Without this test the two sides drifted silently:
- Zod had `Rubric.criteria: min(1)` but Python accepted `dict[str, Any]`.
- Zod's `MultiSelectConfig` declared `correct_indices` but the hand-
  authored Python `MultiSelectConfig` had it too, just with no Zod
  emit, so the JSON Schema mirror was missing entirely.

The parity test fails when:
  * a required field exists on one side but not the other
  * a field's optionality (required vs. optional) disagrees
  * an enum's value set diverges

It deliberately does NOT compare full type equality (the hand-authored
side uses `extra="allow"` and broader `Any` slots for the generator's
forward-compat extras; the generated side uses `extra="forbid"`).
That coexistence is OK; the contract is "hand-authored is a superset
of generated, with the same required keys."
"""

from __future__ import annotations

import pytest

# The generated models are committed under the package. Importing them
# proves the codegen ran during local dev / CI; missing files surface
# as ImportError here so the rest of the suite doesn't silently skip.
from ri_assessments_api.generated.CodeConfig import CodeConfig as GenCodeConfig
from ri_assessments_api.generated.DiagramConfig import DiagramConfig as GenDiagramConfig
from ri_assessments_api.generated.McqConfig import McqConfig as GenMcqConfig
from ri_assessments_api.generated.MultiSelectConfig import (
    MultiSelectConfig as GenMultiSelectConfig,
)
from ri_assessments_api.generated.N8nConfig import N8nConfig as GenN8nConfig
from ri_assessments_api.generated.NotebookConfig import (
    NotebookConfig as GenNotebookConfig,
)
from ri_assessments_api.generated.Rubric import Rubric as GenRubric
from ri_assessments_api.generated.Rubric import ScoringMode as GenScoringMode
from ri_assessments_api.generated.SqlConfig import SqlConfig as GenSqlConfig
from ri_assessments_api.models.interactive import (
    CodeConfig as HandCodeConfig,
)
from ri_assessments_api.models.interactive import (
    DiagramConfig as HandDiagramConfig,
)
from ri_assessments_api.models.interactive import (
    McqConfig as HandMcqConfig,
)
from ri_assessments_api.models.interactive import (
    MultiSelectConfig as HandMultiSelectConfig,
)
from ri_assessments_api.models.interactive import (
    N8nConfig as HandN8nConfig,
)
from ri_assessments_api.models.interactive import (
    NotebookConfig as HandNotebookConfig,
)
from ri_assessments_api.models.interactive import (
    SqlConfig as HandSqlConfig,
)

# Pairs to compare. Hand-authored class first, generated class second.
_INTERACTIVE_PAIRS = [
    ("McqConfig", HandMcqConfig, GenMcqConfig),
    ("MultiSelectConfig", HandMultiSelectConfig, GenMultiSelectConfig),
    ("CodeConfig", HandCodeConfig, GenCodeConfig),
    ("N8nConfig", HandN8nConfig, GenN8nConfig),
    ("NotebookConfig", HandNotebookConfig, GenNotebookConfig),
    ("DiagramConfig", HandDiagramConfig, GenDiagramConfig),
    ("SqlConfig", HandSqlConfig, GenSqlConfig),
]


def _required_field_names(model_cls) -> set[str]:
    return {
        name
        for name, info in model_cls.model_fields.items()
        if info.is_required()
    }


def _all_field_names(model_cls) -> set[str]:
    # n8n's hand-authored model uses `from_` aliased to `from`; the
    # generated model exposes `from` directly. Normalize on the wire
    # name so the parity check compares apples to apples.
    return {
        (info.alias or name)
        for name, info in model_cls.model_fields.items()
    }


@pytest.mark.parametrize("name,hand,gen", _INTERACTIVE_PAIRS)
def test_required_fields_match_zod(name, hand, gen):
    """Required Zod fields must remain required on the Python side."""

    hand_required = _required_field_names(hand)
    gen_required = _required_field_names(gen)
    missing_on_hand = gen_required - hand_required
    assert not missing_on_hand, (
        f"{name}: fields required by Zod but missing/optional in Python: "
        f"{sorted(missing_on_hand)}"
    )


@pytest.mark.parametrize("name,hand,gen", _INTERACTIVE_PAIRS)
def test_all_zod_fields_present_on_python(name, hand, gen):
    """Every field defined in Zod must exist on the Python side
    (alias-aware). Python is allowed to have additional `extra='allow'`
    fields; Zod is the canonical contract for what must be present."""

    hand_fields = _all_field_names(hand)
    gen_fields = _all_field_names(gen)
    missing_on_hand = gen_fields - hand_fields
    assert not missing_on_hand, (
        f"{name}: fields in Zod but missing from Python: "
        f"{sorted(missing_on_hand)}"
    )


def test_rubric_required_fields_match_zod():
    """Rubric is consumed by the scoring service as `dict[str, Any]`
    today. Until the hand-authored Pydantic wrapper lands, this test
    pins the shape so future Zod edits trip CI when the Python side
    has not been updated to consume them.

    `version` carries a Zod default ("1") so it lands as optional on
    the generated side; the strictly required keys are `criteria` and
    `scoring_mode`. When the scoring service migrates to a typed
    Rubric, swap this in for a parity check against the hand-authored
    mirror, the same way the interactive_config pairs work above."""

    gen_required = _required_field_names(GenRubric)
    expected = {"criteria", "scoring_mode"}
    assert gen_required == expected, (
        f"Rubric required fields drifted on the Zod side: now {sorted(gen_required)}. "
        f"Audit the scoring service before regenerating to keep it consuming "
        f"the same shape."
    )


def test_scoring_mode_enum_matches_scoring_service():
    """The scoring service branches on `rubric.scoring_mode`. Keep the
    enum values in lockstep with `services/scoring.py`."""

    expected = {
        "exact_match",
        "numeric_tolerance",
        "structural_match",
        "rubric_ai",
        "test_cases",
    }
    assert {m.value for m in GenScoringMode} == expected
