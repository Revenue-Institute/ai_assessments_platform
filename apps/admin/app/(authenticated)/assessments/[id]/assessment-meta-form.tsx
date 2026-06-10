"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { AlertBanner } from "@/components/alert-banner";
import { FormField, FormInput, FormTextarea } from "@/components/form-fields";
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
  const [saved, setSaved] = useState(false);

  const dirty =
    title.trim() !== initialTitle.trim() ||
    description.trim() !== initialDescription.trim();

  function onSave() {
    setError(null);
    setSaved(false);
    startTransition(async () => {
      const result = await patchAssessmentAction(id, {
        title,
        description: description || null,
      });
      if (result.ok) {
        setSaved(true);
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

      <AlertBanner className="mb-2">{error}</AlertBanner>

      <div className="grid gap-3">
        <FormField label="Title">
          <FormInput
            className="focus:border-primary focus:outline-none"
            onChange={(e) => setTitle(e.target.value)}
            value={title}
          />
        </FormField>
        <FormField label="Description">
          <FormTextarea
            className="h-24 focus:border-primary focus:outline-none"
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional"
            value={description}
          />
        </FormField>
        <div className="flex items-center gap-3">
          <button
            className="btn-primary text-sm disabled:opacity-60"
            disabled={!dirty || pending || !title.trim()}
            onClick={onSave}
            type="button"
          >
            {pending ? "Saving..." : "Save"}
          </button>
          {saved && !dirty && !pending && (
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
