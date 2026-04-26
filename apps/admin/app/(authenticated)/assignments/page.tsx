import Link from "next/link";
import {
  ApiError,
  type AssignmentSummary,
  listAssignments,
} from "@/lib/api";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

export default async function AssignmentsPage() {
  let assignments: AssignmentSummary[] = [];
  let error: string | null = null;
  try {
    assignments = await listAssignments();
  } catch (e) {
    if (e instanceof ApiError) error = e.message;
    else throw e;
  }

  return (
    <>
      <Header page="Assignments" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="flex items-start justify-between rounded-xl border border-border/50 bg-muted/30 p-4">
          <div>
            <h1 className="font-semibold text-xl">Assignments</h1>
            <p className="text-muted-foreground text-sm">
              Magic-link assignments. Status and scores update as candidates submit.
            </p>
          </div>
          <Link
            className="rounded bg-emerald-500 px-3 py-2 text-emerald-950 text-sm hover:bg-emerald-400"
            href="/assignments/new"
          >
            New assignment
          </Link>
        </section>

        {error && (
          <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
            {error}
          </p>
        )}

        {assignments.length === 0 && !error ? (
          <p className="text-muted-foreground text-sm">No assignments yet.</p>
        ) : (
          <table className="w-full overflow-hidden rounded-xl border border-border/50 bg-muted/20 text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground text-xs uppercase">
              <tr>
                <th className="px-4 py-2">Subject</th>
                <th className="px-4 py-2">Module</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Created</th>
                <th className="px-4 py-2">Score</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {assignments.map((a) => (
                <tr key={a.id}>
                  <td className="px-4 py-2">
                    <p className="font-medium">{a.subject_full_name ?? "—"}</p>
                    <p className="text-muted-foreground text-xs">
                      {a.subject_email ?? ""}
                    </p>
                  </td>
                  <td className="px-4 py-2">{a.module_title ?? "—"}</td>
                  <td className="px-4 py-2">
                    <StatusPill status={a.status} />
                  </td>
                  <td className="px-4 py-2 text-muted-foreground text-xs">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2">
                    {a.final_score != null && a.max_possible_score != null
                      ? `${a.final_score} / ${a.max_possible_score}`
                      : "—"}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      className="text-emerald-300 text-xs hover:underline"
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
  const tone =
    status === "completed"
      ? "bg-emerald-900/40 text-emerald-200"
      : status === "in_progress"
        ? "bg-amber-900/40 text-amber-200"
        : status === "cancelled" || status === "expired"
          ? "bg-zinc-800 text-zinc-300"
          : "bg-blue-900/40 text-blue-200";
  return (
    <span className={`rounded px-2 py-0.5 font-medium text-xs ${tone}`}>
      {status}
    </span>
  );
}
