"use client";

import { useEffect, useId, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@repo/api-client";
import { PromptMarkdown } from "@repo/design-system/components/prompt-markdown";

import type { PreviewVariantRow } from "@/lib/api";

import {
  previewVariantsAction,
  reviseQuestionAction,
} from "./question-actions.actions";

interface QuestionShape {
  id: string;
  prompt_template: string;
  rubric?: Record<string, unknown>;
  type: string;
  variable_schema?: Record<string, unknown>;
}

export function QuestionActions({
  question,
  editable,
}: {
  question: QuestionShape;
  editable: boolean;
}) {
  const [open, setOpen] = useState<null | "variants" | "regenerate">(null);

  return (
    <div className="flex items-center gap-1">
      <button
        className="rounded border border-border/40 px-2 py-0.5 text-xs hover:bg-muted"
        onClick={() => setOpen("variants")}
        type="button"
      >
        Preview 5 variants
      </button>
      {editable && (
        <button
          className="rounded border border-primary/40 bg-primary/10 px-2 py-0.5 text-primary text-xs hover:bg-primary/20"
          onClick={() => setOpen("regenerate")}
          type="button"
        >
          Regenerate
        </button>
      )}
      {open === "variants" && (
        <VariantsPanel onClose={() => setOpen(null)} question={question} />
      )}
      {open === "regenerate" && (
        <RegeneratePanel
          onClose={() => setOpen(null)}
          questionId={question.id}
        />
      )}
    </div>
  );
}

function VariantsPanel({
  question,
  onClose,
}: {
  question: QuestionShape;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<PreviewVariantRow[]>([]);

  useEffect(() => {
    previewVariantsAction({
      prompt_template: question.prompt_template,
      variable_schema: question.variable_schema ?? {},
      seed_count: 5,
    })
      .then((r) => {
        setRows(r.variants);
        setLoading(false);
      })
      .catch((e) => {
        setError(
          e instanceof ApiError ? e.message : "Could not load variants."
        );
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const variableKeys = Object.keys(question.variable_schema ?? {});
  const rubricShape = (question.rubric ?? {}) as {
    criteria?: unknown[];
    scoring_mode?: unknown;
  };
  const rubricCriteria = Array.isArray(rubricShape.criteria)
    ? (rubricShape.criteria as Record<string, unknown>[])
    : [];
  const scoringMode =
    typeof rubricShape.scoring_mode === "string"
      ? rubricShape.scoring_mode
      : null;

  return (
    <Modal onClose={onClose} title="5 sampled variants">
      <div className="mb-3 rounded border border-border/40 bg-background/40 p-3 text-xs">
        <p className="font-medium text-sm">Template context</p>
        <dl className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
          <div>
            <dt className="text-muted-foreground uppercase tracking-wide">
              Variables
            </dt>
            <dd className="mt-0.5">
              {variableKeys.length === 0 ? "(none)" : variableKeys.join(", ")}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground uppercase tracking-wide">
              Scoring mode
            </dt>
            <dd className="mt-0.5">{scoringMode ?? "-"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground uppercase tracking-wide">
              Rubric criteria
            </dt>
            <dd className="mt-0.5">{rubricCriteria.length}</dd>
          </div>
        </dl>
        {rubricCriteria.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer text-muted-foreground hover:text-primary">
              Inspect rubric
            </summary>
            <ul className="mt-2 space-y-1">
              {rubricCriteria.map((c, i) => {
                const id =
                  typeof c.id === "string" ? c.id : `criterion-${i + 1}`;
                const label =
                  typeof c.label === "string" ? c.label : "(no label)";
                const weight = typeof c.weight === "number" ? c.weight : null;
                return (
                  <li className="text-[11px]" key={id}>
                    <span className="font-medium">{label}</span>
                    {weight != null && (
                      <span className="text-muted-foreground">
                        {" "}
                        - weight {Math.round(weight * 100)}%
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </details>
        )}
      </div>

      {loading && (
        <p className="text-muted-foreground text-sm">Sampling variants...</p>
      )}
      {error && (
        <p
          className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
          role="alert"
        >
          {error}
        </p>
      )}
      {!(loading || error) && rows.length > 0 && (
        <ol className="grid gap-3 md:grid-cols-2">
          {rows.map((v) => (
            <li
              className="rounded border border-border/40 bg-background/40 p-3 text-sm"
              key={v.seed}
            >
              <p className="text-muted-foreground text-xs uppercase tracking-wide">
                Seed {v.seed}
              </p>
              <div className="mt-1">
                <PromptMarkdown source={v.rendered_prompt} />
              </div>
              {Object.keys(v.variables ?? {}).length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-muted-foreground text-xs hover:text-primary">
                    Variables
                  </summary>
                  <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/40 p-2 text-xs">
                    {JSON.stringify(v.variables, null, 2)}
                  </pre>
                </details>
              )}
              {v.expected_answer !== undefined && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-muted-foreground text-xs hover:text-primary">
                    Expected answer
                  </summary>
                  <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/40 p-2 text-xs">
                    {JSON.stringify(v.expected_answer, null, 2)}
                  </pre>
                </details>
              )}
            </li>
          ))}
        </ol>
      )}
      {!(loading || error) && rows.length === 0 && (
        <p className="text-muted-foreground text-sm">
          No variants returned. This question may not have a randomized variable
          schema attached.
        </p>
      )}
    </Modal>
  );
}

type PreserveKey =
  | "type"
  | "competency_tags"
  | "max_points"
  | "difficulty"
  | "time_limit_seconds"
  | "rubric";

const PRESERVE_OPTIONS: Array<{ value: PreserveKey; label: string }> = [
  { value: "type", label: "Question type" },
  { value: "competency_tags", label: "Competency tags" },
  { value: "max_points", label: "Max points" },
  { value: "difficulty", label: "Difficulty" },
  { value: "time_limit_seconds", label: "Time limit" },
  { value: "rubric", label: "Rubric" },
];

function RegeneratePanel({
  questionId,
  onClose,
}: {
  questionId: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [instruction, setInstruction] = useState("");
  const [preserve, setPreserve] = useState<Set<PreserveKey>>(
    new Set(["type", "competency_tags"])
  );
  const [error, setError] = useState<string | null>(null);

  function togglePreserve(key: PreserveKey) {
    setPreserve((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function submit() {
    setError(null);
    if (instruction.trim().length === 0) {
      setError("Tell the model what to change.");
      return;
    }
    startTransition(async () => {
      try {
        await reviseQuestionAction(questionId, {
          instruction: instruction.trim(),
          preserve: Array.from(preserve) as Parameters<
            typeof reviseQuestionAction
          >[1]["preserve"],
        });
        onClose();
        router.refresh();
      } catch (e) {
        setError(
          e instanceof ApiError ? e.message : "Could not revise question."
        );
      }
    });
  }

  return (
    <Modal onClose={onClose} title="Regenerate question">
      <div className="space-y-3">
        <label className="block space-y-1">
          <span className="text-sm">Revision instruction</span>
          <textarea
            autoFocus
            className="block h-24 w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none"
            disabled={pending}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="e.g. make this harder, use a Fortune 500 context, use a SaaS scenario"
            value={instruction}
          />
        </label>
        <fieldset className="space-y-1">
          <legend className="text-muted-foreground text-xs uppercase tracking-wide">
            Preserve
          </legend>
          <div className="flex flex-wrap gap-2">
            {PRESERVE_OPTIONS.map((opt) => (
              <label
                className="inline-flex cursor-pointer items-center gap-1.5 rounded border border-border/40 bg-background/40 px-2 py-1 text-xs"
                key={opt.value}
              >
                <input
                  checked={preserve.has(opt.value)}
                  disabled={pending}
                  onChange={() => togglePreserve(opt.value)}
                  type="checkbox"
                />
                <span>{opt.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {error && (
          <p
            className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
            role="alert"
          >
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button
            className="rounded border border-border/50 px-3 py-1.5 text-sm hover:bg-muted"
            disabled={pending}
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="btn-primary text-sm disabled:opacity-60"
            disabled={pending}
            onClick={submit}
            type="button"
          >
            {pending ? "Revising..." : "Submit revision"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  children: React.ReactNode;
  onClose: () => void;
  title: string;
}) {
  const titleId = useId();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      aria-labelledby={titleId}
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4"
      role="dialog"
    >
      <button
        aria-label="Close dialog"
        className="fixed inset-0 -z-10 cursor-default bg-background/80 backdrop-blur"
        onClick={onClose}
        type="button"
      />
      <div className="mt-12 w-full max-w-3xl rounded-xl border border-border/60 bg-card p-4 shadow-lg">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-medium text-sm" id={titleId}>{title}</h3>
          <button
            aria-label="Close"
            className="rounded border border-border/50 px-2 py-0.5 text-xs hover:bg-muted"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
