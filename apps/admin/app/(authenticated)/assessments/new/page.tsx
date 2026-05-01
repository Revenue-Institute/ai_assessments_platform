import { ApiError, listModules, type ModuleSummary } from "@/lib/api";
import { Header } from "../../components/header";
import { NewAssessmentForm } from "./new-assessment-form";

export const dynamic = "force-dynamic";

export default async function NewAssessmentPage() {
  let modules: ModuleSummary[] = [];
  let error: string | null = null;
  try {
    modules = await listModules();
  } catch (e) {
    if (e instanceof ApiError) error = e.message;
    else throw e;
  }

  const publishedModules = modules.filter((m) => m.status === "published");

  return (
    <>
      <Header page="New assessment" pages={["Assessments"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <h1 className="font-semibold text-xl">Create draft assessment</h1>
          <p className="mt-1 text-muted-foreground text-sm">
            Bundle published modules into an ordered assessment. Drafts can be
            edited; publish before issuing assignments.
          </p>
        </section>

        {error && (
          <p
            className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
            role="alert"
          >
            {error}
          </p>
        )}

        <NewAssessmentForm modules={publishedModules} />
      </div>
    </>
  );
}
