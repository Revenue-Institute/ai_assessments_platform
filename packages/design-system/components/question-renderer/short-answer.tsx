"use client";

import type { QuestionForRenderer, QuestionRendererMode } from "./types";

/**
 * Short-answer single-line input (spec §5.1).
 */
export function ShortAnswerRenderer({
  question,
  mode,
}: {
  question: QuestionForRenderer;
  mode: QuestionRendererMode;
}) {
  if (mode === "preview") {
    return (
      <input
        aria-label="Candidate would type a short answer here"
        className="w-full rounded border border-border/60 bg-card/40 px-3 py-2 text-sm"
        disabled
        placeholder="Candidate types a short answer"
        type="text"
      />
    );
  }
  const previous = (question.raw_answer?.value as { text?: string } | undefined)
    ?.text;
  return (
    <input
      aria-label="Your short answer"
      autoComplete="off"
      className="w-full rounded border border-border bg-card px-3 py-2 text-sm focus:border-primary focus:outline-none"
      defaultValue={previous ?? ""}
      maxLength={300}
      name="answer"
      placeholder="Your answer"
      required
      type="text"
    />
  );
}
