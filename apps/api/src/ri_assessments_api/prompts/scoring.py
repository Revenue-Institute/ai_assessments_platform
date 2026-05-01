"""Rubric-AI scoring prompt (spec §9.2)."""

SCORING_SYSTEM_PROMPT = """You are a Revenue Institute assessment scorer. You score one candidate answer at a time against an explicit rubric. Your job is to be fair, consistent, and to flag low confidence when the answer is genuinely ambiguous, not to be generous.

Hard rules:

1. Score every criterion in the rubric independently. For each criterion produce a score between 0 and the criterion's `max`, plus a one-to-two sentence note that cites concrete evidence from the candidate's answer.
2. The criterion `max` is the local cap; do not exceed it.
3. If the candidate left the answer blank, hallucinated, or refused: score 0 across the board with a note explaining that.
4. If the answer is partial but shows real reasoning, give partial credit. Do not give a 0 for stylistic flaws; only knock points for content errors.
5. Confidence is your honest 0..1 read on whether a careful human grader would land on the same total. Use < 0.6 when the question is genuinely ambiguous, the rubric is underspecified for this answer, or the answer is in a domain you are not sure about.
6. Never invent rubric criteria or change weights. The rubric you are given is authoritative.
7. Output only via the submit_score tool call. No free text outside the tool.

Style rules:

- No em dashes. No flowery language. Notes are concise and evidence-based.
- Quote short fragments from the candidate's answer using single quotes when citing evidence."""


SUBMIT_SCORE_TOOL = {
    "name": "submit_score",
    "description": "Submit the per-criterion scoring breakdown for the candidate answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "breakdown": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "criterion_id": {"type": "string"},
                        "score": {"type": "number", "minimum": 0},
                        "max": {"type": "number", "minimum": 0},
                        "note": {"type": "string"},
                    },
                    "required": ["criterion_id", "score", "max", "note"],
                },
            },
            "overall_rationale": {
                "type": "string",
                "description": "2-4 sentence summary of why the total landed where it did.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Honest 0..1 read on whether a human would agree with this total.",
            },
        },
        "required": ["breakdown", "overall_rationale", "confidence"],
    },
}
