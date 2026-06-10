"use client";

import { useEffect, useRef, useState } from "react";

import { ActionButton } from "@/components/action-button";
import type { GeneratedOutline, OutlineTopic } from "@/lib/api";

// Inlined to avoid importing from `@/lib/api`, which would bundle the server-only Supabase chain into the client.
function generationRunEventsUrl(runId: string): string {
  return `/api/generation-events?run_id=${encodeURIComponent(runId)}`;
}

interface Props {
  formAction: (formData: FormData) => Promise<void>;
  outline: GeneratedOutline;
  runId: string;
}

type TopicStatus = "pending" | "running" | "done" | "failed";

interface TopicProgressEvent {
  error?: string;
  status: TopicStatus;
  topic_name: string;
}

interface FinishedEvent {
  module_id?: string;
}

interface TopicRow extends OutlineTopic {
  uid: string;
}

function makeUid() {
  return Math.random().toString(36).slice(2);
}

export function OutlineReviewForm({ formAction, outline, runId }: Props) {
  const [topics, setTopics] = useState<TopicRow[]>(() =>
    outline.topics.map((t) => ({ ...t, uid: makeUid() }))
  );
  const [submitting, setSubmitting] = useState(false);
  // Per-topic progress map keyed by topic_name. Lives outside React render
  // path during SSE updates to keep the topic ordering stable.
  const [topicStatus, setTopicStatus] = useState<Record<string, TopicStatus>>(
    {}
  );
  const [topicError, setTopicError] = useState<Record<string, string>>({});
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, []);

  function move(index: number, delta: -1 | 1) {
    setTopics((prev) => {
      const next = prev.slice();
      const target = index + delta;
      if (target < 0 || target >= next.length) {
        return prev;
      }
      [next[index], next[target]] = [
        next[target] as TopicRow,
        next[index] as TopicRow,
      ];
      return next;
    });
  }

  function updateField<K extends keyof TopicRow>(
    uid: string,
    key: K,
    value: TopicRow[K]
  ) {
    setTopics((prev) =>
      prev.map((t) => (t.uid === uid ? { ...t, [key]: value } : t))
    );
  }

  let totalQuestions = 0;
  let totalWeight = 0;
  for (const t of topics) {
    totalQuestions += Number(t.question_count) || 0;
    totalWeight += Number(t.weight_pct) || 0;
  }

  function openProgressStream() {
    // Seed every known topic as pending so the UI renders the full list
    // immediately, then SSE events transition individual rows to running /
    // done / failed. Re-open is a no-op if the previous source is alive.
    const initial: Record<string, TopicStatus> = {};
    for (const t of topics) {
      initial[t.name] = "pending";
    }
    setTopicStatus(initial);
    setTopicError({});
    eventSourceRef.current?.close();
    let source: EventSource;
    try {
      source = new EventSource(generationRunEventsUrl(runId));
    } catch {
      // Browsers without EventSource fall back to the awaited server
      // action with no live progress.
      return;
    }
    eventSourceRef.current = source;

    const handleTopic = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as TopicProgressEvent;
        setTopicStatus((prev) => ({
          ...prev,
          [data.topic_name]: data.status,
        }));
        if (data.error) {
          setTopicError((prev) => ({
            ...prev,
            [data.topic_name]: data.error as string,
          }));
        }
      } catch {
        // Malformed payload; skip silently.
      }
    };
    source.addEventListener("topic_completed", handleTopic);
    source.addEventListener("topic_started", handleTopic);
    source.addEventListener("topic_failed", handleTopic);
    source.addEventListener("finished", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as FinishedEvent;
        if (data.module_id) {
          // Navigate ahead of the server action's redirect when SSE delivers
          // the module id first. The server action will also redirect to the
          // same place; whichever fires first wins.
          window.location.assign(`/modules/${data.module_id}`);
        }
      } catch {
        // No-op
      }
      source.close();
      eventSourceRef.current = null;
    });
    // On hard SSE error, fall back to the awaited server action; nothing
    // else to do, the server action still drives the redirect.
    source.onerror = () => {
      source.close();
      eventSourceRef.current = null;
    };
  }

  async function handleSubmit(formData: FormData) {
    setSubmitting(true);
    openProgressStream();
    try {
      await formAction(formData);
    } finally {
      // Server action either redirects or returns; if it returns, restore.
      setSubmitting(false);
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    }
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        void handleSubmit(new FormData(e.currentTarget));
      }}
    >
      <div className="grid gap-3 rounded-xl border border-border/50 bg-muted/20 p-4 md:grid-cols-2">
        <Field label="Slug" name="slug" required />
        <Field label="Domain" name="domain" required />
        <Field defaultValue={outline.title} label="Title" name="title" />
        <Field
          defaultValue={String(outline.estimated_duration_minutes)}
          label="Estimated duration (min)"
          name="estimated_duration_minutes"
          type="number"
        />
        <Field
          defaultValue={String(outline.total_points)}
          label="Total points"
          name="total_points"
          type="number"
        />
        <Field
          defaultValue={outline.description}
          label="Description"
          name="description"
          textarea
        />
      </div>

      <p className="text-muted-foreground text-xs">
        {topics.length} topics, {totalQuestions} questions, weight sum{" "}
        <span
          className={
            Math.abs(totalWeight - 100) > 1 ? "text-warning" : undefined
          }
        >
          {totalWeight}%
        </span>
        . Use the arrows to reorder topics before generating.
      </p>

      <ol className="space-y-3">
        {topics.map((t, i) => (
          <li
            className="grid gap-2 rounded-xl border border-border/50 bg-muted/20 p-4 text-sm md:grid-cols-12"
            key={t.uid}
          >
            <div className="flex items-center justify-between gap-2 md:col-span-12">
              <p className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
                Topic {i + 1}
              </p>
              <div className="flex items-center gap-1">
                <ActionButton
                  aria-label={`Move topic ${i + 1} up`}
                  disabled={i === 0 || submitting}
                  onClick={() => move(i, -1)}
                >
                  ↑
                </ActionButton>
                <ActionButton
                  aria-label={`Move topic ${i + 1} down`}
                  disabled={i === topics.length - 1 || submitting}
                  onClick={() => move(i, 1)}
                >
                  ↓
                </ActionButton>
              </div>
            </div>
            <Field
              className="md:col-span-6"
              label={`Topic ${i + 1} name`}
              name={`topics[${i}].name`}
              onChange={(v) => updateField(t.uid, "name", v)}
              value={t.name}
            />
            <Field
              className="md:col-span-3"
              label="Weight %"
              name={`topics[${i}].weight_pct`}
              onChange={(v) =>
                updateField(t.uid, "weight_pct", Number.parseFloat(v) || 0)
              }
              type="number"
              value={String(t.weight_pct)}
            />
            <Field
              className="md:col-span-3"
              label="Question count"
              name={`topics[${i}].question_count`}
              onChange={(v) =>
                updateField(
                  t.uid,
                  "question_count",
                  Number.parseInt(v, 10) || 0
                )
              }
              type="number"
              value={String(t.question_count)}
            />
            <Field
              className="md:col-span-6"
              label="Competency tags (comma-separated)"
              name={`topics[${i}].competency_tags`}
              onChange={(v) =>
                updateField(
                  t.uid,
                  "competency_tags",
                  v
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean)
                )
              }
              value={t.competency_tags.join(", ")}
            />
            <Field
              className="md:col-span-6"
              label="Recommended types"
              name={`topics[${i}].recommended_types`}
              onChange={(v) =>
                updateField(
                  t.uid,
                  "recommended_types",
                  v
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean)
                )
              }
              value={t.recommended_types.join(", ")}
            />
            <Field
              className="md:col-span-12"
              label="Rationale"
              name={`topics[${i}].rationale`}
              onChange={(v) => updateField(t.uid, "rationale", v)}
              textarea
              value={t.rationale}
            />
          </li>
        ))}
      </ol>

      <div className="flex flex-col gap-2">
        <button
          className="btn-primary text-sm disabled:opacity-60"
          disabled={submitting}
          type="submit"
        >
          {submitting ? (
            <span className="inline-flex items-center gap-1">
              <span>Generating {topics.length} topics</span>
              <span aria-hidden="true" className="loading-dots">
                <span>.</span>
                <span>.</span>
                <span>.</span>
              </span>
            </span>
          ) : (
            `Generate questions for ${topics.length} topics`
          )}
        </button>
        {submitting && (
          <TopicProgressList
            error={topicError}
            status={topicStatus}
            topics={topics.map((t) => t.name)}
          />
        )}
        <p className="text-muted-foreground text-xs">
          {submitting
            ? `Generating ${topics.length} topics in parallel (about 10-20 seconds). You will be redirected to the module editor when complete.`
            : "One Claude call per topic in parallel. Expect about 10 to 20 seconds total. The module is created as a draft; review and publish from the module detail page."}
        </p>
      </div>

      <style>{`
        .loading-dots span {
          display: inline-block;
          animation: ri-bounce 1.2s infinite ease-in-out;
        }
        .loading-dots span:nth-child(2) {
          animation-delay: 0.15s;
        }
        .loading-dots span:nth-child(3) {
          animation-delay: 0.3s;
        }
        @keyframes ri-bounce {
          0%, 80%, 100% { opacity: 0.2; transform: translateY(0); }
          40% { opacity: 1; transform: translateY(-2px); }
        }
      `}</style>
    </form>
  );
}

function TopicProgressList({
  topics,
  status,
  error,
}: {
  topics: string[];
  status: Record<string, TopicStatus>;
  error: Record<string, string>;
}) {
  return (
    <ul
      aria-live="polite"
      className="space-y-1 rounded border border-border/40 bg-background/40 p-3 text-xs"
    >
      {topics.map((name) => {
        const current = status[name] ?? "pending";
        const message = error[name];
        return (
          <li className="flex items-baseline justify-between gap-3" key={name}>
            <span className="truncate">{name}</span>
            <span className="inline-flex items-center gap-2">
              {message && (
                <span className="truncate text-destructive">{message}</span>
              )}
              <StatusBadge status={current} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

const STATUS_LABELS: Record<TopicStatus, string> = {
  pending: "Pending",
  running: "Running",
  done: "Done",
  failed: "Failed",
};

const STATUS_TONE: Record<TopicStatus, string> = {
  pending: "border-border/40 bg-muted/40 text-muted-foreground",
  running: "border-primary/40 bg-primary/10 text-primary",
  done: "border-primary/50 bg-primary/15 text-primary",
  failed: "border-destructive/50 bg-destructive/15 text-destructive",
};

function StatusBadge({ status }: { status: TopicStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 font-medium text-[10px] uppercase tracking-wide ${STATUS_TONE[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

interface FieldProps {
  className?: string;
  defaultValue?: string;
  label: string;
  name: string;
  onChange?: (value: string) => void;
  required?: boolean;
  textarea?: boolean;
  type?: string;
  value?: string;
}

function Field({
  label,
  name,
  defaultValue,
  value,
  onChange,
  required,
  type = "text",
  textarea = false,
  className = "",
}: FieldProps) {
  const inputClass =
    "block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none";
  const controlled = value !== undefined && onChange !== undefined;
  return (
    <label className={`space-y-1 ${className}`} htmlFor={name}>
      <span className="text-muted-foreground text-xs">{label}</span>
      {textarea ? (
        <textarea
          className={`${inputClass} h-20`}
          defaultValue={controlled ? undefined : defaultValue}
          id={name}
          name={name}
          onChange={controlled ? (e) => onChange(e.target.value) : undefined}
          value={controlled ? value : undefined}
        />
      ) : (
        <input
          className={inputClass}
          defaultValue={controlled ? undefined : defaultValue}
          id={name}
          name={name}
          onChange={controlled ? (e) => onChange(e.target.value) : undefined}
          required={required}
          type={type}
          value={controlled ? value : undefined}
        />
      )}
    </label>
  );
}
