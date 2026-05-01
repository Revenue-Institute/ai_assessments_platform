"use client";

import { useMemo, useState, useTransition } from "react";
import type { ModuleSummary } from "@/lib/api";
import { createAssessmentAction } from "../actions";

function sluggify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

export function NewAssessmentForm({ modules }: { modules: ModuleSummary[] }) {
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, startTransition] = useTransition();

  const derivedSlug = useMemo(() => (slugTouched ? slug : sluggify(title)), [
    title,
    slug,
    slugTouched,
  ]);

  function toggleModule(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function moveUp(id: string) {
    setSelected((prev) => {
      const i = prev.indexOf(id);
      if (i <= 0) return prev;
      const next = prev.slice();
      [next[i - 1], next[i]] = [next[i] as string, next[i - 1] as string];
      return next;
    });
  }

  function moveDown(id: string) {
    setSelected((prev) => {
      const i = prev.indexOf(id);
      if (i < 0 || i >= prev.length - 1) return prev;
      const next = prev.slice();
      [next[i], next[i + 1]] = [next[i + 1] as string, next[i] as string];
      return next;
    });
  }

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    startTransition(async () => {
      await createAssessmentAction({
        slug: derivedSlug,
        title,
        description: description || null,
        module_ids: selected,
      });
    });
  }

  const modulesById = useMemo(() => {
    const m = new Map<string, ModuleSummary>();
    for (const mod of modules) m.set(mod.id, mod);
    return m;
  }, [modules]);

  const unselected = modules.filter((m) => !selected.includes(m.id));

  return (
    <form
      className="grid max-w-2xl gap-3 rounded-xl border border-border/50 bg-muted/20 p-4"
      onSubmit={onSubmit}
    >
      <label className="space-y-1">
        <span className="text-sm">Title</span>
        <input
          className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none"
          name="title"
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Q2 Sales Operations Assessment"
          required
          value={title}
        />
      </label>

      <label className="space-y-1">
        <span className="text-sm">Slug</span>
        <input
          className="block w-full rounded border border-border/60 bg-background px-3 py-2 font-mono text-sm focus:border-primary focus:outline-none"
          name="slug"
          onChange={(e) => {
            setSlug(e.target.value);
            setSlugTouched(true);
          }}
          onFocus={() => {
            if (!slugTouched) {
              setSlug(derivedSlug);
              setSlugTouched(true);
            }
          }}
          placeholder="q2-sales-ops"
          required
          value={derivedSlug}
        />
        <span className="text-muted-foreground text-xs">
          Auto-derived from the title until you edit it.
        </span>
      </label>

      <label className="space-y-1">
        <span className="text-sm">Description (optional)</span>
        <textarea
          className="block h-24 w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none"
          name="description"
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What this assessment covers and who it is for."
          value={description}
        />
      </label>

      <div className="space-y-2">
        <p className="text-sm">Modules</p>
        <p className="text-muted-foreground text-xs">
          Pick from published modules. Drag-free ordering with up and down
          buttons. You can add or rearrange modules later.
        </p>

        {modules.length === 0 ? (
          <p className="rounded border border-dashed border-border/60 bg-background/30 px-3 py-4 text-center text-muted-foreground text-xs">
            No published modules available yet. Publish at least one module
            first, then come back.
          </p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded border border-border/40 bg-background/30 p-2">
              <p className="mb-2 eyebrow-label">Selected ({selected.length})</p>
              {selected.length === 0 ? (
                <p className="px-2 py-3 text-muted-foreground text-xs">
                  Nothing selected yet.
                </p>
              ) : (
                <ol className="space-y-1">
                  {selected.map((id, i) => {
                    const m = modulesById.get(id);
                    if (!m) return null;
                    return (
                      <li
                        className="flex items-center gap-2 rounded border border-border/40 bg-muted/30 px-2 py-1 text-xs"
                        key={id}
                      >
                        <span className="w-5 text-muted-foreground">
                          {i + 1}.
                        </span>
                        <span className="min-w-0 flex-1 truncate">
                          {m.title}
                        </span>
                        <button
                          aria-label="Move up"
                          className="rounded border border-border/40 px-1 text-muted-foreground hover:bg-muted disabled:opacity-40"
                          disabled={i === 0}
                          onClick={() => moveUp(id)}
                          type="button"
                        >
                          {"↑"}
                        </button>
                        <button
                          aria-label="Move down"
                          className="rounded border border-border/40 px-1 text-muted-foreground hover:bg-muted disabled:opacity-40"
                          disabled={i === selected.length - 1}
                          onClick={() => moveDown(id)}
                          type="button"
                        >
                          {"↓"}
                        </button>
                        <button
                          className="rounded border border-destructive/40 px-1 text-destructive hover:bg-destructive/15"
                          onClick={() => toggleModule(id)}
                          type="button"
                        >
                          Remove
                        </button>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>
            <div className="rounded border border-border/40 bg-background/30 p-2">
              <p className="mb-2 eyebrow-label">
                Available ({unselected.length})
              </p>
              {unselected.length === 0 ? (
                <p className="px-2 py-3 text-muted-foreground text-xs">
                  All published modules are selected.
                </p>
              ) : (
                <ul className="space-y-1">
                  {unselected.map((m) => (
                    <li
                      className="flex items-center gap-2 rounded border border-border/40 bg-background/40 px-2 py-1 text-xs"
                      key={m.id}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">
                          {m.title}
                        </span>
                        <span className="block truncate text-muted-foreground">
                          {m.domain} · {m.difficulty} · {m.question_count}{" "}
                          questions
                        </span>
                      </span>
                      <button
                        className="rounded border border-primary/40 px-2 text-primary hover:bg-primary/15"
                        onClick={() => toggleModule(m.id)}
                        type="button"
                      >
                        Add
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>

      <button
        className="btn-primary mt-2 text-sm disabled:opacity-60"
        disabled={pending || !title || !derivedSlug}
        type="submit"
      >
        {pending ? "Creating..." : "Create draft"}
      </button>
    </form>
  );
}
