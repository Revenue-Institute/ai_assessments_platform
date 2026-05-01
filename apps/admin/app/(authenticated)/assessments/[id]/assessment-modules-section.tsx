"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import type {
  AssessmentDetail,
  AssessmentStatus,
  ModuleSummary,
} from "@/lib/api";
import {
  addAssessmentModuleAction,
  removeAssessmentModuleAction,
  reorderAssessmentAction,
} from "../actions";

export function AssessmentModulesSection({
  assessment,
  available,
  status,
}: {
  assessment: AssessmentDetail;
  available: ModuleSummary[];
  status: AssessmentStatus;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [pickerValue, setPickerValue] = useState("");

  const editable = status === "draft";

  function handle(promise: Promise<{ ok: true } | { ok: false; error: string }>) {
    setError(null);
    startTransition(async () => {
      const r = await promise;
      if (r.ok) {
        router.refresh();
      } else {
        setError(r.error);
      }
    });
  }

  function moveUp(index: number) {
    if (index <= 0) return;
    const ids = assessment.modules.map((m) => m.module_id);
    const next = ids.slice();
    [next[index - 1], next[index]] = [
      next[index] as string,
      next[index - 1] as string,
    ];
    handle(reorderAssessmentAction(assessment.id, next));
  }

  function moveDown(index: number) {
    const ids = assessment.modules.map((m) => m.module_id);
    if (index < 0 || index >= ids.length - 1) return;
    const next = ids.slice();
    [next[index], next[index + 1]] = [
      next[index + 1] as string,
      next[index] as string,
    ];
    handle(reorderAssessmentAction(assessment.id, next));
  }

  function remove(moduleId: string) {
    handle(removeAssessmentModuleAction(assessment.id, moduleId));
  }

  function addPicked() {
    if (!pickerValue) return;
    const id = pickerValue;
    setPickerValue("");
    handle(addAssessmentModuleAction(assessment.id, id));
  }

  return (
    <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-medium text-sm">Modules</h2>
        {!editable && (
          <p className="text-muted-foreground text-xs">
            {status === "published"
              ? "Published. Archive to edit modules."
              : "Archived."}
          </p>
        )}
      </div>

      {error && (
        <p
          className="mb-2 rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
          role="alert"
        >
          {error}
        </p>
      )}

      {assessment.modules.length === 0 ? (
        <p className="rounded border border-dashed border-border/60 bg-background/30 px-3 py-4 text-center text-muted-foreground text-sm">
          No modules in this assessment yet.
        </p>
      ) : (
        <ol className="space-y-2 text-sm">
          {assessment.modules.map((m, i) => (
            <li
              className="flex items-center gap-3 rounded border border-border/40 bg-background/30 p-3"
              key={m.module_id}
            >
              <span className="w-6 text-muted-foreground">{i + 1}.</span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{m.title}</p>
                <p className="truncate text-muted-foreground text-xs">
                  {m.domain} · {m.difficulty} · {m.question_count} questions ·{" "}
                  {m.target_duration_minutes} min
                </p>
              </div>
              {editable && (
                <div className="flex items-center gap-1">
                  <button
                    aria-label="Move up"
                    className="rounded border border-border/40 px-2 py-0.5 text-xs hover:bg-muted disabled:opacity-40"
                    disabled={i === 0 || pending}
                    onClick={() => moveUp(i)}
                    type="button"
                  >
                    {"↑"}
                  </button>
                  <button
                    aria-label="Move down"
                    className="rounded border border-border/40 px-2 py-0.5 text-xs hover:bg-muted disabled:opacity-40"
                    disabled={i === assessment.modules.length - 1 || pending}
                    onClick={() => moveDown(i)}
                    type="button"
                  >
                    {"↓"}
                  </button>
                  <button
                    className="rounded border border-destructive/40 px-2 py-0.5 text-destructive text-xs hover:bg-destructive/15 disabled:opacity-40"
                    disabled={pending}
                    onClick={() => remove(m.module_id)}
                    type="button"
                  >
                    Remove
                  </button>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}

      {editable && (
        <div className="mt-3 flex flex-wrap items-end gap-2 border-border/40 border-t pt-3">
          <label className="min-w-0 flex-1 space-y-1">
            <span className="text-sm">Add module</span>
            <select
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none"
              onChange={(e) => setPickerValue(e.target.value)}
              value={pickerValue}
            >
              <option value="">
                {available.length === 0
                  ? "No more published modules to add"
                  : "Pick a published module..."}
              </option>
              {available.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title} ({m.domain}, {m.question_count}q,{" "}
                  {m.target_duration_minutes}m)
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn-primary text-sm disabled:opacity-60"
            disabled={!pickerValue || pending}
            onClick={addPicked}
            type="button"
          >
            {pending ? "Working..." : "Add"}
          </button>
        </div>
      )}
    </section>
  );
}
