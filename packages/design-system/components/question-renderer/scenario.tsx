"use client";

import type { QuestionForRenderer, QuestionRendererMode } from "./types";

interface ScenarioPart {
  id?: string;
  label?: string;
  placeholder?: string;
}

/**
 * Scenario renderer (spec §5.1). When `interactive_config.parts` is a
 * non-empty array, render one labeled textarea per part. Otherwise a
 * single free-form textarea spans the prompt. Same dispatch on both
 * sides; the `mode` prop only flips disabled / required.
 */
export function ScenarioRenderer({
  question,
  mode,
}: {
  question: QuestionForRenderer;
  mode: QuestionRendererMode;
}) {
  const config = (question.interactive_config ?? {}) as Record<string, unknown>;
  const parts = config.parts as ScenarioPart[] | undefined;
  const previousResponses =
    mode === "interactive"
      ? ((question.raw_answer?.value as
          | { responses?: Record<string, string>; text?: string }
          | undefined) ?? {})
      : {};

  if (Array.isArray(parts) && parts.length > 0) {
    return (
      <div className="space-y-3">
        {parts.map((part, i) => {
          const partId = part.id ?? `part_${i + 1}`;
          const previous = previousResponses.responses?.[partId] ?? "";
          return (
            <label className="block space-y-1" key={partId}>
              <span className="block font-medium text-foreground text-sm">
                {part.label ?? `Part ${i + 1}`}
              </span>
              <textarea
                className={
                  mode === "interactive"
                    ? "h-32 w-full rounded border border-border bg-card px-3 py-2 text-sm leading-6 focus:border-primary focus:outline-none"
                    : "h-24 w-full rounded border border-border/60 bg-card/40 px-3 py-2 text-sm leading-6"
                }
                defaultValue={previous}
                disabled={mode === "preview"}
                maxLength={4000}
                name={
                  mode === "interactive"
                    ? `scenario_part:${partId}`
                    : `preview_part:${partId}`
                }
                placeholder={part.placeholder ?? "Your response"}
                required={mode === "interactive"}
              />
            </label>
          );
        })}
      </div>
    );
  }

  if (mode === "preview") {
    return (
      <textarea
        aria-label="Candidate would write a scenario response here"
        className="h-40 w-full rounded border border-border/60 bg-card/40 px-3 py-2 text-sm leading-6"
        disabled
        placeholder="Candidate walks through each part of the scenario"
      />
    );
  }
  return (
    <textarea
      aria-label="Scenario response"
      className="h-56 w-full rounded border border-border bg-card px-3 py-2 text-sm leading-6 focus:border-primary focus:outline-none"
      defaultValue={previousResponses.text ?? ""}
      maxLength={6000}
      name="answer"
      placeholder="Walk through each part of the scenario."
      required
    />
  );
}
