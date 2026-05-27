"use client";

import { parseMcqConfig } from "@repo/schemas";
import type { QuestionForRenderer, QuestionRendererMode } from "./types";

/**
 * MCQ (single-choice) renderer. Was duplicated between
 * apps/admin/.../question-preview-renderer.tsx (preview shell) and
 * apps/candidate/.../renderer.tsx (interactive shell); now a single
 * component with a `mode` prop.
 *
 * `interactive` mode emits a real radio fieldset bound to `name="answer"`
 * with the JSON-encoded selection as the value (matching the candidate
 * form submission contract). `preview` mode disables every input so an
 * admin reviewer can scan the bank without form-submit risk.
 */
export function McqRenderer({
  question,
  mode,
}: {
  question: QuestionForRenderer;
  mode: QuestionRendererMode;
}) {
  const config = parseMcqConfig(question.interactive_config);
  const options = config.options ?? [];
  const previous =
    mode === "interactive"
      ? (question.raw_answer?.value as { selected?: string } | undefined)
          ?.selected
      : undefined;

  if (options.length === 0) {
    return <EmptyOptions mode={mode} />;
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
        Choose one
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
            defaultChecked={previous === opt}
            disabled={mode === "preview"}
            name={mode === "interactive" ? "answer" : "preview"}
            required={mode === "interactive"}
            type="radio"
            value={JSON.stringify({ selected_index: i, selected: opt })}
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

function EmptyOptions({ mode }: { mode: QuestionRendererMode }) {
  // Preview mode shows this when an admin is auditing a half-authored
  // module; interactive mode would only see this if the snapshot was
  // corrupted, so the language is closer to "we can't proceed".
  const message =
    mode === "preview"
      ? "No options configured for this choice question."
      : "Question is missing its option list; contact your administrator.";
  return (
    <p
      className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-warning text-xs"
      role="alert"
    >
      {message}
    </p>
  );
}
