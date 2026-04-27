import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import {
  ApiError,
  type AttemptEvent,
  cancelAssignment,
  getAssignment,
  listAssignmentEvents,
  resendAssignmentEmail,
  rescoreAssignment,
  rescoreAttempt,
} from "@/lib/api";
import { Header } from "../../components/header";
import { IntegrityEventTimeline } from "./integrity-timeline";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

export default async function AssignmentDetailPage({
  params,
}: {
  params: Params;
}) {
  const { id } = await params;

  let detail: Awaited<ReturnType<typeof getAssignment>>;
  try {
    detail = await getAssignment(id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  let events: AttemptEvent[] = [];
  try {
    events = await listAssignmentEvents(id);
  } catch {
    // Soft fail: timeline is auxiliary; the rest of the page still loads.
  }

  async function cancel(): Promise<void> {
    "use server";
    try {
      await cancelAssignment(id);
      redirect(`/assignments/${id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/assignments/${id}`);
      }
      throw e;
    }
  }

  async function rescoreAll(): Promise<void> {
    "use server";
    try {
      await rescoreAssignment(id);
      redirect(`/assignments/${id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/assignments/${id}`);
      }
      throw e;
    }
  }

  async function resendEmail(): Promise<void> {
    "use server";
    try {
      await resendAssignmentEmail(id);
      redirect(`/assignments/${id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/assignments/${id}`);
      }
      throw e;
    }
  }

  async function rescoreOne(formData: FormData): Promise<void> {
    "use server";
    const attemptId = String(formData.get("attempt_id") ?? "");
    if (!attemptId) return;
    try {
      await rescoreAttempt(attemptId);
      redirect(`/assignments/${id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/assignments/${id}`);
      }
      throw e;
    }
  }

  return (
    <>
      <Header page={detail.subject_full_name ?? "Assignment"} pages={["Assignments"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <nav
          aria-label="Related entities"
          className="flex flex-wrap gap-3 text-muted-foreground text-xs"
        >
          {detail.subject_id && (
            <Link
              className="hover:text-primary hover:underline"
              href={`/subjects/${detail.subject_id}`}
            >
              ↗ Subject: {detail.subject_full_name ?? detail.subject_id.slice(0, 8)}
            </Link>
          )}
          {detail.module_id && (
            <Link
              className="hover:text-primary hover:underline"
              href={`/modules/${detail.module_id}`}
            >
              ↗ Module: {detail.module_title ?? detail.module_id.slice(0, 8)}
            </Link>
          )}
        </nav>

        <section className="grid grid-cols-1 gap-4 rounded-xl border border-border/50 bg-muted/30 p-4 sm:grid-cols-2 md:grid-cols-4">
          <Stat label="Status" value={detail.status} />
          <Stat label="Module" value={detail.module_title ?? "—"} />
          <Stat
            label="Score"
            value={
              detail.final_score != null && detail.max_possible_score != null
                ? `${detail.final_score} / ${detail.max_possible_score}`
                : "—"
            }
          />
          <Stat
            label="Integrity"
            value={
              detail.integrity_score != null ? `${detail.integrity_score}` : "—"
            }
          />
          <Stat
            label="Started"
            value={
              detail.started_at
                ? new Date(detail.started_at).toLocaleString()
                : "—"
            }
          />
          <Stat
            label="Completed"
            value={
              detail.completed_at
                ? new Date(detail.completed_at).toLocaleString()
                : "—"
            }
          />
          <Stat
            label="Expires"
            value={new Date(detail.expires_at).toLocaleString()}
          />
          <Stat
            label="Active time"
            value={
              detail.total_time_seconds != null
                ? `${Math.round(detail.total_time_seconds / 60)} min`
                : "—"
            }
          />
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <h2 className="mb-3 font-medium text-sm">Attempts</h2>
          {detail.attempts.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No attempts yet. Attempts are created lazily when the candidate views each question.
            </p>
          ) : (
            <ol className="space-y-3 text-sm">
              {detail.attempts.map((a, i) => (
                <li
                  className="rounded border border-border/40 bg-background/30 p-3"
                  key={a.id}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium">
                      Question {i + 1}
                      {a.needs_review && (
                        <span className="ml-2 rounded bg-warning/20 px-2 py-0.5 text-[10px] font-medium text-warning uppercase tracking-wide">
                          Needs review
                        </span>
                      )}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {a.submitted_at ? "submitted" : "in progress"}
                    </p>
                  </div>
                  <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-muted-foreground text-xs">
                    {a.rendered_prompt}
                  </p>
                  {a.raw_answer && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-muted-foreground text-xs hover:text-primary">
                        View raw answer
                      </summary>
                      <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted/40 p-2 text-xs">
                        {JSON.stringify(a.raw_answer, null, 2)}
                      </pre>
                    </details>
                  )}
                  {a.score_rationale && (
                    <p className="mt-2 rounded border border-border/40 bg-muted/30 p-2 text-muted-foreground text-xs">
                      {a.score_rationale}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-muted-foreground text-xs">
                    <span>
                      Score:{" "}
                      {a.score != null
                        ? `${a.score} / ${a.max_score}`
                        : `— / ${a.max_score}`}
                    </span>
                    {a.scorer_model && (
                      <span>
                        Scorer: <code>{a.scorer_model}</code>
                      </span>
                    )}
                    {a.scorer_confidence != null && (
                      <span>Confidence: {a.scorer_confidence}</span>
                    )}
                    {a.active_time_seconds != null && (
                      <span>Active: {a.active_time_seconds}s</span>
                    )}
                    {a.submitted_at && (
                      <form action={rescoreOne} className="ml-auto">
                        <input name="attempt_id" type="hidden" value={a.id} />
                        <button
                          className="rounded border border-primary/40 bg-primary/10 px-2 py-1 text-primary text-xs hover:bg-primary/20"
                          type="submit"
                        >
                          Rescore
                        </button>
                      </form>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <h2 className="mb-3 font-medium text-sm">Integrity timeline</h2>
          <IntegrityEventTimeline events={events} />
        </section>

        <div className="flex flex-wrap gap-2">
          {detail.status === "completed" && (
            <form action={rescoreAll}>
              <button
                className="rounded border border-primary/50 bg-primary/10 px-3 py-2 text-primary text-sm hover:bg-primary/20"
                type="submit"
              >
                Rescore all attempts
              </button>
            </form>
          )}
          {detail.status !== "completed" &&
            detail.status !== "cancelled" &&
            detail.status !== "expired" && (
              <>
                <form action={resendEmail}>
                  <button
                    className="rounded border border-primary/50 bg-primary/10 px-3 py-2 text-primary text-sm hover:bg-primary/20"
                    type="submit"
                  >
                    Resend magic link
                  </button>
                </form>
                <form action={cancel}>
                  <button
                    className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm hover:bg-destructive/25"
                    type="submit"
                  >
                    Cancel assignment
                  </button>
                </form>
              </>
            )}
        </div>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs uppercase tracking-wide">
        {label}
      </p>
      <p className="font-medium text-sm">{value}</p>
    </div>
  );
}
