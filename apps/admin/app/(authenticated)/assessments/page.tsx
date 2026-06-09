import Link from "next/link";

import { type AssessmentSummary, listAssessments } from "@/lib/api";
import { loadOrApiError } from "@/lib/api-helpers";
import { AlertBanner } from "@/components/alert-banner";
import { StatusBadge } from "@/components/status-badge";

import { Header } from "../components/header";

export const dynamic = "force-dynamic";

export default async function AssessmentsPage() {
  const { data, error } = await loadOrApiError(listAssessments);
  const assessments: AssessmentSummary[] = data ?? [];

  return (
    <>
      <Header page="Assessments" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="flex items-start justify-between rounded-xl border border-border/50 bg-muted/30 p-4">
          <div>
            <h2 className="font-semibold text-xl">Assessments</h2>
            <p className="text-muted-foreground text-sm">
              Composed of modules. Publish to assign to subjects.
            </p>
          </div>
          <Link className="btn-primary text-sm" href="/assessments/new">
            New assessment
          </Link>
        </section>

        <AlertBanner>{error}</AlertBanner>

        {assessments.length === 0 && !error ? (
          <div className="rounded-xl border border-border/60 border-dashed bg-muted/10 px-6 py-10 text-center">
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

