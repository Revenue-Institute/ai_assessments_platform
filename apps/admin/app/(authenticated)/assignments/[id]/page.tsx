import { notFound, redirect } from "next/navigation";
import {
  ApiError,
  cancelAssignment,
  getAssignment,
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
                    <p className="font-medium">Question {i + 1}</p>
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
                  <div className="mt-2 flex gap-3 text-muted-foreground text-xs">
                    <span>
                      Score:{" "}
                      {a.score != null
                        ? `${a.score} / ${a.max_score}`
                        : `— / ${a.max_score}`}
                    </span>
                    {a.active_time_seconds != null && (
                      <span>Active: {a.active_time_seconds}s</span>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

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
