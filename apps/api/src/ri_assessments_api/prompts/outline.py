"""Stage-1 outline generation prompt (spec §6.2)."""

OUTLINE_SYSTEM_PROMPT = """You are the Revenue Institute Assessments outline generator. Your job is to take a role brief and produce a balanced, time-budgeted outline of an assessment that a recruiter or operations leader can publish in minutes.

Hard rules:

1. Analyze the responsibilities text. Extract concrete skills, tools, and decision scenarios that an actual person in this role would face daily.
2. Propose 4 to 8 topics covering the role with weight_pct values that sum to exactly 100.
3. For each topic pick 1 to 2 recommended_types biased toward interactive question types where the underlying skill is practical: n8n for automation, code for engineering, notebook for data science, sql for analysts, diagram for process work. Use mcq, short_answer, or long_answer when written response is the most natural format.
4. Respect the question_mix percentages in the brief within plus or minus 10 percent for each bucket. The buckets are: mcq_pct, short_pct, long_pct, code_pct, interactive_pct (interactive covers n8n, notebook, diagram, sql).
5. Never invent competency_tags. Only use tags that exist in the competency taxonomy that follows. If the role does not map cleanly, pick the closest existing tags. Do not output tags that are not in the taxonomy.
6. Estimate time per question type using these defaults: mcq=45s, short=2min, long=5min, code=8min, notebook=12min, n8n=15min, diagram=8min, sql=5min, scenario=5min. Sum the estimates and confirm the total stays within target_duration_minutes plus or minus 15 percent. Adjust question_count if needed.
7. Prefer breadth across required_competencies. If a brief calls out specific competencies, ensure each appears in at least one topic.
8. Output only via the submit_outline tool call. Do not produce free text.

Style rules (mandatory across all generated content):

- No em dashes. Use commas, parentheses, or short sentences instead.
- No flowery language. Direct, operational tone.
- Avoid CRITICAL / MUST / NEVER unless describing a real hard constraint.

The competency taxonomy you are allowed to draw from is below. Each line is `id - label`."""


SUBMIT_OUTLINE_TOOL = {
    "name": "submit_outline",
    "description": (
        "Submit the assessment outline for the given role brief. Always use this "
        "tool exactly once to return the outline."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Concise assessment title, e.g. 'HubSpot Workflows Assessment'.",
            },
            "description": {
                "type": "string",
                "description": "1-2 sentence description shown on the consent screen.",
            },
            "topics": {
                "type": "array",
                "minItems": 4,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "competency_tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                        "weight_pct": {
                            "type": "number",
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "question_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 12,
                        },
                        "recommended_types": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 3,
                            "items": {
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
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this topic and these types fit the role.",
                        },
                    },
                    "required": [
                        "name",
                        "competency_tags",
                        "weight_pct",
                        "question_count",
                        "recommended_types",
                        "rationale",
                    ],
                },
            },
            "total_points": {
                "type": "number",
                "minimum": 1,
                "description": "Sum of expected max_points across all questions.",
            },
            "estimated_duration_minutes": {
                "type": "integer",
                "minimum": 5,
                "maximum": 480,
                "description": "Estimated total wall-clock time to complete the assessment.",
            },
        },
        "required": [
            "title",
            "description",
            "topics",
            "total_points",
            "estimated_duration_minutes",
        ],
    },
}
