import { notFound, redirect } from "next/navigation";
import {
  ApiError,
  cancelAssignment,
  getAssignment,
  rescoreAssignment,
  rescoreAttempt,
} from "@/lib/api";
import { Header } from "../../components/header";

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
        <section className="grid grid-cols-2 gap-4 rounded-xl border border-border/50 bg-muted/30 p-4 md:grid-cols-4">
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
                        <span className="ml-2 rounded bg-amber-900/40 px-2 py-0.5 text-[10px] font-medium text-amber-200 uppercase tracking-wide">
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
                    <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted/40 p-2 text-xs">
                      {JSON.stringify(a.raw_answer, null, 2)}
                    </pre>
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
                          className="rounded border border-emerald-900/40 bg-emerald-950/30 px-2 py-1 text-emerald-200 text-xs hover:bg-emerald-950/50"
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

        <div className="flex flex-wrap gap-2">
          {detail.status === "completed" && (
            <form action={rescoreAll}>
              <button
                className="rounded border border-emerald-900/50 bg-emerald-950/30 px-3 py-2 text-emerald-200 text-sm hover:bg-emerald-950/50"
                type="submit"
              >
                Rescore all attempts
              </button>
            </form>
          )}
          {detail.status !== "completed" &&
            detail.status !== "cancelled" &&
            detail.status !== "expired" && (
              <form action={cancel}>
                <button
                  className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm hover:bg-red-950/50"
                  type="submit"
                >
                  Cancel assignment
                </button>
              </form>
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
