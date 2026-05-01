import Link from "next/link";
import {
  ApiError,
  type AssessmentSummary,
  listAssessments,
} from "@/lib/api";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

export default async function AssessmentsPage() {
  let assessments: AssessmentSummary[] = [];
  let error: string | null = null;
  try {
    assessments = await listAssessments();
  } catch (e) {
    if (e instanceof ApiError) error = e.message;
    else throw e;
  }

  return (
    <>
      <Header page="Assessments" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="flex items-start justify-between rounded-xl border border-border/50 bg-muted/30 p-4">
          <div>
            <h1 className="font-semibold text-xl">Assessments</h1>
            <p className="text-muted-foreground text-sm">
              Composed of modules. Publish to assign to subjects.
            </p>
          </div>
          <Link className="btn-primary text-sm" href="/assessments/new">
            New assessment
          </Link>
        </section>

        {error && (
          <p
            className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
            role="alert"
          >
            {error}
          </p>
        )}

        {assessments.length === 0 && !error ? (
          <div className="rounded-xl border border-dashed border-border/60 bg-muted/10 px-6 py-10 text-center">
            <p className="text-muted-foreground text-sm">
              No assessments yet. Create your first assessment.
            </p>
            <Link className="btn-primary mt-3 text-sm" href="/assessments/new">
              New assessment
            </Link>
          </div>
        ) : (
          <ul className="divide-y divide-border/40 rounded-xl border border-border/50 bg-muted/20">
            {assessments.map((a) => (
              <li
                className="flex items-center justify-between gap-4 px-4 py-3"
                key={a.id}
              >
                <div className="min-w-0 flex-1">
                  <Link
                    className="block font-medium hover:underline"
                    href={`/assessments/${a.id}`}
                  >
                    {a.title}
                  </Link>
                  <p className="truncate text-muted-foreground text-xs">
                    {a.slug} · {a.module_count}{" "}
                    {a.module_count === 1 ? "module" : "modules"} ·{" "}
                    {a.question_count}{" "}
                    {a.question_count === 1 ? "question" : "questions"} ·{" "}
                    {a.total_duration_minutes} min
                  </p>
                </div>
                <StatusBadge status={a.status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "published"
      ? "bg-primary/20 text-primary"
      : status === "archived"
        ? "bg-muted text-muted-foreground"
        : "bg-warning/20 text-warning";
  return (
    <span className={`rounded px-2 py-0.5 font-medium text-xs ${tone}`}>
      {status}
    </span>
  );
}
