"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { patchAssessmentAction } from "../actions";

export function AssessmentMetaForm({
  id,
  slug,
  title: initialTitle,
  description: initialDescription,
}: {
  id: string;
  slug: string;
  title: string;
  description: string;
}) {
  const router = useRouter();
  const [title, setTitle] = useState(initialTitle);
  const [description, setDescription] = useState(initialDescription);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const dirty =
    title.trim() !== initialTitle.trim() ||
    description.trim() !== initialDescription.trim();

  function onSave() {
    setError(null);
    startTransition(async () => {
      const result = await patchAssessmentAction(id, {
        title,
        description: description || null,
      });
      if (result.ok) {
        setSavedAt(Date.now());
        router.refresh();
      } else {
        setError(result.error);
      }
    });
  }

  return (
    <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-medium text-sm">Details</h2>
        <p className="text-muted-foreground text-xs">
          Slug (read only):{" "}
          <code className="rounded bg-muted px-1 font-mono">{slug}</code>
        </p>
      </div>

      {error && (
        <p
          className="mb-2 rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
          role="alert"
        >
          {error}
        </p>
      )}

      <div className="grid gap-3">
        <label className="space-y-1">
          <span className="text-sm">Title</span>
          <input
            className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none"
            onChange={(e) => setTitle(e.target.value)}
            value={title}
          />
        </label>
        <label className="space-y-1">
          <span className="text-sm">Description</span>
          <textarea
            className="block h-24 w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none"
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional"
            value={description}
          />
        </label>
        <div className="flex items-center gap-3">
          <button
            className="btn-primary text-sm disabled:opacity-60"
            disabled={!dirty || pending || !title.trim()}
            onClick={onSave}
            type="button"
          >
            {pending ? "Saving..." : "Save"}
          </button>
          {savedAt && !dirty && !pending && (
            <span className="text-muted-foreground text-xs">Saved.</span>
          )}
          {dirty && !pending && (
            <span className="text-muted-foreground text-xs">
              Unsaved changes.
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
