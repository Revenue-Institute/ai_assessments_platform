import { notFound, redirect } from "next/navigation";
import {
  ApiError,
  fetchGenerationRun,
  type GenerationBriefIn,
  type GeneratedOutline,
  generateQuestions,
  type OutlineTopic,
} from "@/lib/api";
import { Header } from "../../../components/header";

export const dynamic = "force-dynamic";

type Params = Promise<{ run_id: string }>;
type SearchParams = Promise<{ error?: string }>;

export default async function OutlineReviewPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const { run_id } = await params;
  const { error } = await searchParams;

  let run: Awaited<ReturnType<typeof fetchGenerationRun>>;
  try {
    run = await fetchGenerationRun(run_id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  if (run.stage !== "outline" || run.status !== "success" || !run.outline) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
        <h1 className="font-semibold text-2xl">Outline unavailable</h1>
        <p className="text-muted-foreground text-sm">
          {run.error ?? "This generation run did not produce a usable outline."}
        </p>
      </main>
    );
  }

  const brief = run.input_brief as GenerationBriefIn;
  const outline = run.outline;

  async function action(formData: FormData): Promise<void> {
    "use server";
    const slug = String(formData.get("slug") ?? "").trim();
    const domain = String(formData.get("domain") ?? "").trim();
    const title = String(formData.get("title") ?? "").trim();
    const description = String(formData.get("description") ?? "").trim();
    const total_points = Number.parseFloat(
      String(formData.get("total_points") ?? "100")
    );
    const estimated_duration_minutes = Number.parseInt(
      String(formData.get("estimated_duration_minutes") ?? "45"),
      10
    );

    const topics: OutlineTopic[] = outline.topics.map((t, i) => ({
      name: String(formData.get(`topics[${i}].name`) ?? t.name).trim(),
      competency_tags: String(
        formData.get(`topics[${i}].competency_tags`) ?? t.competency_tags.join(",")
      )
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      weight_pct: Number.parseFloat(
        String(formData.get(`topics[${i}].weight_pct`) ?? t.weight_pct)
      ),
      question_count: Number.parseInt(
        String(formData.get(`topics[${i}].question_count`) ?? t.question_count),
        10
      ),
      recommended_types: String(
        formData.get(`topics[${i}].recommended_types`) ?? t.recommended_types.join(",")
      )
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      rationale: String(
        formData.get(`topics[${i}].rationale`) ?? t.rationale
      ).trim(),
    }));

    const editedOutline: GeneratedOutline = {
      title,
      description,
      topics,
      total_points,
      estimated_duration_minutes,
    };

    if (!slug || !domain) {
      redirect(
        `/modules/new/${run_id}?error=` +
          encodeURIComponent("Slug and domain are required.")
      );
    }

    try {
      const result = await generateQuestions({
        outline_run_id: run_id,
        brief,
        outline: editedOutline,
        slug,
        domain,
      });
      redirect(`/modules/${result.module_id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/modules/new/${run_id}?error=` + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  const totalQuestions = outline.topics.reduce(
    (sum, t) => sum + (t.question_count || 0),
    0
  );
  const totalWeight = outline.topics.reduce(
    (sum, t) => sum + (t.weight_pct || 0),
    0
  );

  return (
    <>
      <Header page="Review outline" pages={["Modules", "New module"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <p className="text-emerald-300/70 text-xs uppercase tracking-widest">
            Step 2 of 2 · Outline review
          </p>
          <h1 className="mt-1 font-semibold text-2xl">{outline.title}</h1>
          <p className="mt-1 max-w-prose text-muted-foreground text-sm">
            {outline.description}
          </p>
          <p className="mt-2 text-muted-foreground text-xs">
            {outline.topics.length} topics · {totalQuestions} questions · est.{" "}
            {outline.estimated_duration_minutes} min · weight sum {totalWeight}%
            · model {run.model} · {run.tokens_in} → {run.tokens_out} tokens ·{" "}
            {run.latency_ms} ms
          </p>
        </section>

        {error && (
          <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
            {error}
          </p>
        )}

        <form action={action} className="space-y-4">
          <div className="grid gap-3 rounded-xl border border-border/50 bg-muted/20 p-4 md:grid-cols-2">
            <Field label="Slug" name="slug" required />
            <Field label="Domain" name="domain" required />
            <Field label="Title" name="title" defaultValue={outline.title} />
            <Field
              label="Estimated duration (min)"
              name="estimated_duration_minutes"
              type="number"
              defaultValue={String(outline.estimated_duration_minutes)}
            />
            <Field
              label="Total points"
              name="total_points"
              type="number"
              defaultValue={String(outline.total_points)}
            />
            <Field
              label="Description"
              name="description"
              defaultValue={outline.description}
              textarea
            />
          </div>

          <ol className="space-y-3">
            {outline.topics.map((t, i) => (
              <li
                className="grid gap-2 rounded-xl border border-border/50 bg-muted/20 p-4 text-sm md:grid-cols-12"
                key={i}
              >
                <Field
                  label={`Topic ${i + 1} name`}
                  name={`topics[${i}].name`}
                  defaultValue={t.name}
                  className="md:col-span-6"
                />
                <Field
                  label="Weight %"
                  name={`topics[${i}].weight_pct`}
                  type="number"
                  defaultValue={String(t.weight_pct)}
                  className="md:col-span-3"
                />
                <Field
                  label="Question count"
                  name={`topics[${i}].question_count`}
                  type="number"
                  defaultValue={String(t.question_count)}
                  className="md:col-span-3"
                />
                <Field
                  label="Competency tags (comma-separated)"
                  name={`topics[${i}].competency_tags`}
                  defaultValue={t.competency_tags.join(", ")}
                  className="md:col-span-6"
                />
                <Field
                  label="Recommended types"
                  name={`topics[${i}].recommended_types`}
                  defaultValue={t.recommended_types.join(", ")}
                  className="md:col-span-6"
                />
                <Field
                  label="Rationale"
                  name={`topics[${i}].rationale`}
                  defaultValue={t.rationale}
                  textarea
                  className="md:col-span-12"
                />
              </li>
            ))}
          </ol>

          <button
            className="rounded bg-emerald-500 px-3 py-3 font-medium text-emerald-950 text-sm hover:bg-emerald-400"
            type="submit"
          >
            Generate questions for {outline.topics.length} topics
          </button>
          <p className="text-muted-foreground text-xs">
            One Claude call per topic, in series. Expect ~15-40 seconds per
            topic. The module is created as a draft; review and publish from
            the module detail page.
          </p>
        </form>
      </div>
    </>
  );
}

function Field({
  label,
  name,
  defaultValue,
  required,
  type = "text",
  textarea = false,
  className = "",
}: {
  label: string;
  name: string;
  defaultValue?: string;
  required?: boolean;
  type?: string;
  textarea?: boolean;
  className?: string;
}) {
  const inputClass =
    "block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none";
  return (
    <label className={`space-y-1 ${className}`}>
      <span className="text-muted-foreground text-xs">{label}</span>
      {textarea ? (
        <textarea
          className={`${inputClass} h-20`}
          defaultValue={defaultValue}
          name={name}
        />
      ) : (
        <input
          className={inputClass}
          defaultValue={defaultValue}
          name={name}
          required={required}
          type={type}
        />
      )}
    </label>
  );
}
