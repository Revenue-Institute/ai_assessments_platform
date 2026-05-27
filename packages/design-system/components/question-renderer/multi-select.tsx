"use client";

import { parseMultiSelectConfig } from "@repo/schemas";
import type { QuestionForRenderer, QuestionRendererMode } from "./types";

/**
 * Multi-select renderer (spec §5.1). Shared between the candidate
 * runtime and the admin preview via the `mode` prop. See McqRenderer
 * for the shared contract.
 */
export function MultiSelectRenderer({
  question,
  mode,
}: {
  question: QuestionForRenderer;
  mode: QuestionRendererMode;
}) {
  const config = parseMultiSelectConfig(question.interactive_config);
  const options = config.options ?? [];
  const previousIndices =
    mode === "interactive"
      ? ((
          question.raw_answer?.value as
            | { selected_indices?: number[] }
            | undefined
        )?.selected_indices ?? [])
      : [];

  if (options.length === 0) {
    return (
      <p
        className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-warning text-xs"
        role="alert"
      >
        No options configured for this choice question.
      </p>
    );
  }

  return (
    <fieldset
      className={
        mode === "interactive"
          ? "space-y-2 rounded border border-border bg-card p-4"
          : "space-y-2 rounded border border-border/60 bg-card/50 p-3"
      }
      disabled={mode === "preview"}
    >
      <legend
        className={
          mode === "interactive"
            ? "eyebrow-label px-1"
            : "px-1 text-muted-foreground text-xs"
        }
      >
        Choose all that apply
      </legend>
      {options.map((opt, i) => (
        <label
          className={
            mode === "interactive"
              ? "flex cursor-pointer items-start gap-3 rounded border border-transparent px-2 py-2 hover:border-primary/40 hover:bg-primary/5"
              : "flex items-start gap-3 rounded px-2 py-1.5 text-sm"
          }
          key={opt}
        >
          <input
            className="mt-1"
            defaultChecked={previousIndices.includes(i)}
            disabled={mode === "preview"}
            name={mode === "interactive" ? "answer_indices" : "preview"}
            type="checkbox"
            value={String(i)}
          />
          <span
            className={
              mode === "interactive" ? "text-sm leading-6" : "leading-6"
            }
          >
            {opt}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
