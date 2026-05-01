import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ApiError,
  type AssessmentDetail,
  getAssessment,
  listModules,
  type ModuleSummary,
} from "@/lib/api";
import { Header } from "../../components/header";
import {
  archiveAssessmentAction,
  publishAssessmentAction,
} from "../actions";
import { AssessmentMetaForm } from "./assessment-meta-form";
import { AssessmentModulesSection } from "./assessment-modules-section";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;
type SearchParams = Promise<{ error?: string; ok?: string }>;

export default async function AssessmentDetailPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const { id } = await params;
  const { error, ok } = await searchParams;

  let detail: AssessmentDetail;
  let modules: ModuleSummary[] = [];
  try {
    [detail, modules] = await Promise.all([getAssessment(id), listModules()]);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const publishedModules = modules.filter((m) => m.status === "published");
  const usedIds = new Set(detail.modules.map((m) => m.module_id));
  const available = publishedModules.filter((m) => !usedIds.has(m.id));

  const publishDisabled = detail.modules.length === 0;

  const publish = publishAssessmentAction.bind(null, id);
  const archive = archiveAssessmentAction.bind(null, id);

  return (
    <>
      <Header page={detail.title} pages={["Assessments"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        {(error || ok) && (
          <p
            className={`rounded px-3 py-2 text-sm ${
              error
                ? "border border-destructive/50 bg-destructive/15 text-destructive"
                : "border border-primary/50 bg-primary/15 text-primary"
            }`}
            role={error ? "alert" : "status"}
          >
            {error || ok}
          </p>
        )}

        <section className="grid grid-cols-2 gap-4 rounded-xl border border-border/50 bg-muted/30 p-4 md:grid-cols-4">
          <Stat label="Status" value={detail.status} />
          <Stat label="Modules" value={String(detail.module_count)} />
          <Stat label="Questions" value={String(detail.question_count)} />
          <Stat
            label="Total duration"
            value={`${detail.total_duration_minutes} min`}
          />
        </section>

        <AssessmentMetaForm
          description={detail.description ?? ""}
          id={id}
          slug={detail.slug}
          title={detail.title}
        />

        <AssessmentModulesSection
          assessment={detail}
          available={available}
          status={detail.status}
        />

        <section className="flex flex-wrap items-center gap-2">
          {detail.status === "draft" && (
            <form action={publish}>
              <button
                className="btn-primary text-sm disabled:opacity-50"
                disabled={publishDisabled}
                title={
                  publishDisabled
                    ? "Add at least one module before publishing."
                    : undefined
                }
                type="submit"
              >
                Publish
              </button>
            </form>
          )}
          {detail.status === "published" && (
            <form action={archive}>
              <button
                className="rounded border border-border/50 bg-background px-3 py-2 text-sm hover:bg-muted"
                type="submit"
              >
                Archive
              </button>
            </form>
          )}
          <Link
            className="rounded border border-border/50 bg-background px-3 py-2 text-sm hover:bg-muted"
            href={`/assessments/${id}/preview`}
          >
            Preview as candidate
          </Link>
          {detail.status === "published" && (
            <p className="text-muted-foreground text-xs">
              This assessment is published and can be assigned.
            </p>
          )}
        </section>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="eyebrow-label">{label}</p>
      <p className="mt-0.5 font-medium text-sm">{value}</p>
    </div>
  );
}
