"""Pydantic mirrors of packages/schemas/src/interactive.ts.

Until v1 these were carried as `dict[str, Any]` and not validated server-side,
so a malformed interactive_config from the admin form or the AI generator
would only blow up when the candidate flow or scorer dereferenced it.
Validating at write time gives a 422 with a clear path instead.

Models use `extra='allow'` so the AI generator can attach extra context
fields without tripping validation; the goal is to enforce required keys
and type-correctness on the critical fields, not to reject unknown ones."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _BaseConfig(BaseModel):
    model_config = ConfigDict(extra="allow")


class McqConfig(_BaseConfig):
    options: list[str] = Field(min_length=2)
    correct_index: int = Field(ge=0)


class MultiSelectConfig(_BaseConfig):
    options: list[str] = Field(min_length=2)
    correct_indices: list[int] = Field(min_length=1)


class CodeConfig(_BaseConfig):
    language: Literal["python", "javascript", "typescript", "sql", "bash"]
    starter_code: str
    hidden_tests: str
    visible_tests: str | None = None
    allow_internet: bool = False
    packages: list[str] = Field(default_factory=list)
    time_limit_exec_ms: int = 10_000


class N8nConnection(_BaseConfig):
    from_: str = Field(alias="from")
    to: str


class N8nConfig(_BaseConfig):
    mode: Literal["build", "fix"]
    starter_workflow: Any
    reference_workflow: Any
    required_nodes: list[str]
    required_connections: list[N8nConnection]
    test_payloads: list[Any]
    credentials_provided: list[str]


class NotebookConfig(_BaseConfig):
    starter_notebook: Any
    dataset_urls: list[str]
    validation_script: str
    required_outputs: list[str]


class DiagramConfig(_BaseConfig):
    mode: Literal["build", "analyze"]
    starter_nodes: list[Any]
    reference_structure: Any
    grading_mode: Literal["structural", "ai_narrative", "both"]


class SqlConfig(_BaseConfig):
    schema_sql: str
    seed_sql: str
    expected_query_result: Any | None = None
    expected_sql_patterns: list[str] | None = None


# Question types that carry a typed interactive_config. Types absent from this
# map (eg. short_answer, scenario) accept anything and are passed through.
_VALIDATORS: dict[str, type[BaseModel]] = {
    "mcq": McqConfig,
    "multi_select": MultiSelectConfig,
    "code": CodeConfig,
    "n8n": N8nConfig,
    "notebook": NotebookConfig,
    "diagram": DiagramConfig,
    "sql": SqlConfig,
}


def validate_interactive_config(
    qtype: str, config: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Validate an interactive_config payload against the schema for `qtype`.

    Returns the round-tripped dict on success (preserves extra keys), None
    if the input was None, or raises HTTPException(422) on validation
    failure. Types without a registered validator pass through unchanged."""

    if config is None:
        return None
    model = _VALIDATORS.get(qtype)
    if model is None:
        return config
    try:
        parsed = model.model_validate(config)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    f"interactive_config for type '{qtype}' failed validation"
                ),
                "errors": exc.errors(),
            },
        ) from exc
    return parsed.model_dump(by_alias=True, exclude_none=False)
