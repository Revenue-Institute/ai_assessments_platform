"""Per-question revision prompt (spec §6.5)."""

REVISION_SYSTEM_PROMPT = """You are revising a single Revenue Institute assessment question. The admin will give you the current question template and a free-form instruction (e.g. 'make this harder', 'use a Fortune 500 SaaS context', 'switch from MCQ to short_answer'). Apply the instruction faithfully and emit a fully replaced QuestionTemplate.

Hard rules:

1. Apply the admin instruction. If the instruction conflicts with the spec rules below, ask via a clarifying note in the rationale field of the rubric, but still produce a valid template that prioritizes the spec rules.
2. variable_schema entries are typed and constrained (kind: int, float, choice, dataset, string_template).
3. solver_code is deterministic Python `def solve(variables: dict) -> dict` for numeric questions, omitted (null) for rubric_ai or long_answer.
4. Rubric criteria must be detailed enough to score without the original author. Include scoring_guidance.
5. competency_tags must come from the supplied taxonomy. Never invent tags.
6. Interactive questions get full interactive_config matching their type (code: language/starter_code/hidden_tests, mcq/multi_select: options/correct_index, sql: schema_sql/seed_sql, etc.).
7. No em dashes. No flowery language.
8. Use Jinja-style placeholders (e.g. `{{ revenue }}`) only for variables you declared.
9. Output only via the submit_revised_question tool call.

The admin may also pass a `preserve` list naming fields you must NOT change. Honor it strictly. Common values: type, competency_tags, max_points, difficulty.

The competency taxonomy is below."""


SUBMIT_REVISED_QUESTION_TOOL = {
    "name": "submit_revised_question",
    "description": (
        "Submit the revised QuestionTemplate. Always use this tool exactly once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "mcq",
                    "multi_select",
                    "short_answer",
                    "long_answer",
                    "code",
                    "notebook",
                    "sql",
                    "n8n",
                    "diagram",
                    "scenario",
                ],
            },
            "prompt_template": {"type": "string"},
            "variable_schema": {"type": "object", "additionalProperties": True},
            "solver_code": {"type": ["string", "null"]},
            "interactive_config": {"type": ["object", "null"], "additionalProperties": True},
            "rubric": {
                "type": "object",
                "properties": {
                    "version": {"type": "string"},
                    "scoring_mode": {
                        "type": "string",
                        "enum": [
                            "exact_match",
                            "numeric_tolerance",
                            "structural_match",
                            "rubric_ai",
                            "test_cases",
                        ],
                    },
                    "tolerance": {"type": ["number", "null"]},
                    "criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "weight": {"type": "number", "minimum": 0, "maximum": 1},
                                "description": {"type": "string"},
                                "scoring_guidance": {"type": "string"},
                            },
                            "required": ["id", "label", "weight", "description", "scoring_guidance"],
                        },
                    },
                },
                "required": ["version", "scoring_mode", "criteria"],
            },
            "competency_tags": {"type": "array", "items": {"type": "string"}},
            "max_points": {"type": "number", "minimum": 1, "maximum": 100},
            "difficulty": {
                "type": "string",
                "enum": ["junior", "mid", "senior", "expert"],
            },
            "time_limit_seconds": {"type": ["integer", "null"], "minimum": 30, "maximum": 1800},
        },
        "required": [
            "type",
            "prompt_template",
            "variable_schema",
            "rubric",
            "competency_tags",
            "max_points",
            "difficulty",
        ],
    },
}
