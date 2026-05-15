import Link from "next/link";
import { type AssignmentSummary, listAssignments } from "@/lib/api";
import { loadOrApiError } from "@/lib/api-helpers";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

export default async function AssignmentsPage({
  searchParams,
}: {
  searchParams: Promise<{ review?: string }>;
}) {
  const { review } = await searchParams;
  const reviewOnly = review === "1";
  const { data, error } = await loadOrApiError(() =>
    listAssignments(reviewOnly ? { needsReview: true } : undefined)
  );
  const assignments: AssignmentSummary[] = data ?? [];

  return (
    <>
      <Header page="Assignments" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="flex items-start justify-between rounded-xl border border-border/50 bg-muted/30 p-4">
          <div>
            <h1 className="font-semibold text-xl">Assignments</h1>
            <p className="text-muted-foreground text-sm">
              Magic-link assignments. Status and scores update as candidates
              submit.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              aria-pressed={reviewOnly}
              className={`rounded border px-3 py-1.5 text-xs ${
                reviewOnly
                  ? "border-warning/60 bg-warning/15 text-warning"
                  : "border-border bg-card text-muted-foreground hover:border-primary/40"
              }`}
              href={reviewOnly ? "/assignments" : "/assignments?review=1"}
            >
              {reviewOnly ? "Showing review-flagged" : "Needs review only"}
            </Link>
            <Link className="btn-primary text-sm" href="/assignments/new">
              New assignment
            </Link>
          </div>
        </section>

        {error && (
          <p
            className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
            role="alert"
          >
            {error}
          </p>
        )}

        {assignments.length === 0 && !error ? (
          <div className="rounded-xl border border-border/60 border-dashed bg-muted/10 px-6 py-10 text-center">
            <p className="text-muted-foreground text-sm">No assignments yet.</p>
            <Link className="btn-primary mt-3 text-sm" href="/assignments/new">
              Issue magic links
            </Link>
          </div>
        ) : (
          <table className="w-full overflow-hidden rounded-xl border border-border/50 bg-muted/20 text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground text-xs uppercase">
              <tr>
                <th className="px-4 py-2" scope="col">
                  Subject
                </th>
                <th className="px-4 py-2" scope="col">
                  Assessment
                </th>
                <th className="px-4 py-2" scope="col">
                  Status
                </th>
                <th className="px-4 py-2" scope="col">
                  Created
                </th>
                <th className="px-4 py-2" scope="col">
                  Score
                </th>
                <th className="px-4 py-2" scope="col">
                  Review
                </th>
                <th className="px-4 py-2" scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {assignments.map((a) => (
                <tr key={a.id}>
                  <td className="px-4 py-2">
                    <p className="font-medium">{a.subject_full_name ?? "-"}</p>
                    <p className="text-muted-foreground text-xs">
                      {a.subject_email ?? ""}
                    </p>
                  </td>
                  <td className="px-4 py-2">
                    {a.assessment_title ?? a.module_title ?? "-"}
                  </td>
                  <td className="px-4 py-2">
                    <StatusPill status={a.status} />
                  </td>
                  <td className="px-4 py-2 text-muted-foreground text-xs">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2">
                    {a.final_score != null && a.max_possible_score != null
                      ? `${a.final_score} / ${a.max_possible_score}`
                      : "-"}
                  </td>
                  <td className="px-4 py-2">
                    {a.needs_review ? (
                      <span
                        className="rounded bg-warning/20 px-2 py-0.5 font-medium text-warning text-xs"
                        title="At least one attempt scored with low confidence"
                      >
                        Flagged
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">-</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      className="text-primary text-xs hover:underline"
                      href={`/assignments/${a.id}`}
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function StatusPill({ status }: { status: string }) {
  let tone = "bg-secondary text-secondary-foreground";
  if (status === "completed") {
    tone = "bg-primary/20 text-primary";
  } else if (status === "in_progress") {
    tone = "bg-warning/20 text-warning";
  } else if (status === "cancelled" || status === "expired") {
    tone = "bg-muted text-muted-foreground";
  }
  return (
    <span className={`rounded px-2 py-0.5 font-medium text-xs ${tone}`}>
      {status}
    </span>
  );
}
