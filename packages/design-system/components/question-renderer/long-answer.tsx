"use client";

import type { QuestionForRenderer, QuestionRendererMode } from "./types";

/**
 * Long-answer free-form textarea (spec §5.1).
 */
export function LongAnswerRenderer({
  question,
  mode,
}: {
  question: QuestionForRenderer;
  mode: QuestionRendererMode;
}) {
  if (mode === "preview") {
    return (
      <textarea
        aria-label="Candidate would type a long answer here"
        className="h-32 w-full rounded border border-border/60 bg-card/40 px-3 py-2 text-sm leading-6"
        disabled
        placeholder="Candidate types a paragraph response"
      />
    );
  }
  const previous = (question.raw_answer?.value as { text?: string } | undefined)
    ?.text;
  return (
    <textarea
      aria-label="Your long-form answer"
      className="h-48 w-full rounded border border-border bg-card px-3 py-2 text-sm leading-6 focus:border-primary focus:outline-none"
      defaultValue={previous ?? ""}
      maxLength={4000}
      name="answer"
      placeholder="Write your answer"
      required
    />
  );
}
