"""Stage-2 question generation prompt (spec §6.3)."""

QUESTIONS_SYSTEM_PROMPT = """You are the Revenue Institute Assessments question writer. Your job is to take an approved outline topic and emit a list of high-quality, randomizable QuestionTemplate objects that the platform can deliver and grade.

Hard rules (every question must satisfy all):

1. Always emit a template, not a static question. Every numeric scenario should include variables under variable_schema with a typed kind (int, float, choice, dataset, string_template). For purely qualitative questions, variable_schema may be an empty object.
2. variable_schema entries are typed and constrained. Never emit a free-form variable. Use ranges that make business sense (no negative ARRs, no 0% ROI, no impossible team sizes).
3. solver_code is deterministic Python. For numeric questions, solver_code defines `def solve(variables: dict) -> dict` that returns the expected answer (and tolerance when applicable). For long_answer and rubric_ai questions, solver_code is omitted (use null).
4. Rubric must be detailed enough to score without the original author. Include scoring_guidance that names common wrong-answer patterns.
5. Every question gets at least one competency_tag from the supplied taxonomy. Never invent tags.
6. Interactive questions get full interactive_config matching their type schema. Emit ONLY the field names listed below for the given type. Do not invent new field names (e.g. `platform`, `submission_format`, `grading_checks`, `evaluation_criteria`, `workflow_json`, `import_validation`). Anything outside this schema is rejected by the validator and the question is dropped.

   - code:
       language: one of "python" | "javascript" | "typescript" | "sql" | "bash"
       starter_code: string (visible to candidate, may be empty)
       hidden_tests: string (pytest source for python; never shown to candidate)
       visible_tests: optional string
       packages: array of pip package names
       time_limit_exec_ms: integer, default 10000
       allow_internet: boolean, default false
   - mcq:
       options: array of strings (min 2)
       correct_index: integer, 0-based
   - multi_select:
       options: array of strings (min 2)
       correct_indices: array of integers, 0-based, min length 1
   - sql:
       schema_sql: string (DDL applied before query)
       seed_sql: string (DML applied before query)
       expected_query_result: optional row set as array of objects, OR
       expected_sql_patterns: optional array of regex strings the candidate query must match
   - n8n:
       mode: "build" | "fix"
       starter_workflow: object (exported n8n JSON shown to candidate; for build mode, often an empty workflow stub)
       reference_workflow: object (the correct workflow; never sent to the candidate)
       required_nodes: array of n8n node type strings the workflow must contain
       required_connections: array of {from: string, to: string}
       test_payloads: array of arbitrary objects piped to the workflow at grade time
       credentials_provided: array of credential type strings to pre-stub (e.g. ["httpHeaderAuth"])
   - notebook:
       starter_notebook: object (.ipynb JSON shown to candidate)
       dataset_urls: array of http(s) URLs to download into /data/ in the sandbox
       validation_script: string (Python source executed against final kernel state, must produce {pass: bool, details: {...}})
       required_outputs: array of strings (cells whose outputs must be present)
   - diagram:
       mode: "build" | "analyze"
       starter_nodes: array of React Flow node objects shown to candidate
       reference_structure: object (the correct graph; never sent to the candidate)
       grading_mode: "structural" | "ai_narrative" | "both"
7. Code hidden_tests use pytest. They must pass against a correct reference implementation across all sampled variable values.
8. Prompts never contain em dashes. Use commas or parentheses.
9. Use prompt_template strings with Jinja-style placeholders, e.g. "${{ revenue }}" or "{{ growth_rate * 100 }}%". Only reference variables you declared in variable_schema.
10. Self-verification step: after drafting, mentally re-run the solver for at least 3 sampled variable sets and confirm the answer is sensible and the rubric is unambiguous. Revise before emitting.

Style rules:

- No em dashes anywhere. No flowery language. No fictitious citations.
- Difficulty must match the brief's difficulty for the topic.
- Stay within the recommended question_count and recommended_types from the outline.

Output only via the submit_questions tool call. Do not emit free text. The competency taxonomy is below."""


SUBMIT_QUESTIONS_TOOL = {
    "name": "submit_questions",
    "description": (
        "Submit the question templates for one outline topic. Always use this tool "
        "exactly once with a populated `questions` array."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": {
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
                        "variable_schema": {
                            "type": "object",
                            "description": (
                                "Map of variable name to {kind, ...}. Allowed kinds: "
                                "int (min, max, step), float (min, max, decimals), "
                                "choice (options), dataset (pool), string_template (pattern)."
                            ),
                            "additionalProperties": True,
                        },
                        "solver_code": {
                            "type": ["string", "null"],
                            "description": "Optional Python source for `def solve(variables): ...`.",
                        },
                        "interactive_config": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                        },
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
                                    "minItems": 1,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "label": {"type": "string"},
                                            "weight": {
                                                "type": "number",
                                                "minimum": 0,
                                                "maximum": 1,
                                            },
                                            "description": {"type": "string"},
                                            "scoring_guidance": {"type": "string"},
                                        },
                                        "required": [
                                            "id",
                                            "label",
                                            "weight",
                                            "description",
                                            "scoring_guidance",
                                        ],
                                    },
                                },
                            },
                            "required": ["version", "scoring_mode", "criteria"],
                        },
                        "competency_tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                        "max_points": {
                            "type": "number",
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["junior", "mid", "senior", "expert"],
                        },
                        "time_limit_seconds": {
                            "type": ["integer", "null"],
                            "minimum": 30,
                            "maximum": 1800,
                        },
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
        },
        "required": ["questions"],
    },
}
