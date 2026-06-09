import { listModules, type ModuleSummary } from "@/lib/api";
import { loadOrApiError } from "@/lib/api-helpers";
import { AlertBanner } from "@/components/alert-banner";

import { Header } from "../../components/header";
import { NewAssessmentForm } from "./new-assessment-form";

export const dynamic = "force-dynamic";

export default async function NewAssessmentPage() {
  const { data, error } = await loadOrApiError(listModules);
  const modules: ModuleSummary[] = data ?? [];

  const publishedModules = modules.filter((m) => m.status === "published");

  return (
    <>
      <Header page="New assessment" pages={["Assessments"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <h2 className="font-semibold text-xl">Create draft assessment</h2>
          <p className="mt-1 text-muted-foreground text-sm">
            Bundle published modules into an ordered assessment. Drafts can be
            edited; publish before issuing assignments.
          </p>
        </section>

        <AlertBanner>{error}</AlertBanner>

        <NewAssessmentForm modules={publishedModules} />
      </div>
    </>
  );
}
