import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { AlertBanner } from "@/components/alert-banner";
import {
  ApiError,
  fetchGenerationRun,
  type GeneratedOutline,
  type GenerationBriefIn,
  generateQuestions,
  type OutlineTopic,
} from "@/lib/api";

import { Header } from "../../../components/header";
import { OutlineReviewForm } from "./outline-review-form";

export const dynamic = "force-dynamic";

type Params = Promise<{ run_id: string }>;
type SearchParams = Promise<{ error?: string }>;

export async function generateMetadata({
  params,
}: {
  params: Params;
}): Promise<Metadata> {
  const { run_id } = await params;
  try {
    const run = await fetchGenerationRun(run_id);
    const brief = run.input_brief as { role_title?: string };
    return {
      title: brief.role_title
        ? `Generate - ${brief.role_title}`
        : "Generate Module",
    };
  } catch {
    return { title: "Generate Module" };
  }
}

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseTopicFromForm(formData: FormData, i: number): OutlineTopic {
  return {
    name: String(formData.get(`topics[${i}].name`) ?? "").trim(),
    competency_tags: splitCsv(
      String(formData.get(`topics[${i}].competency_tags`) ?? "")
    ),
    weight_pct: Number.parseFloat(
      String(formData.get(`topics[${i}].weight_pct`) ?? "0")
    ),
    question_count: Number.parseInt(
      String(formData.get(`topics[${i}].question_count`) ?? "0"),
      10
    ),
    recommended_types: splitCsv(
      String(formData.get(`topics[${i}].recommended_types`) ?? "")
    ),
    rationale: String(formData.get(`topics[${i}].rationale`) ?? "").trim(),
  };
}

function parseOutlineFromForm(formData: FormData): GeneratedOutline {
  const title = String(formData.get("title") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  const total_points = Number.parseFloat(
    String(formData.get("total_points") ?? "100")
  );
  const estimated_duration_minutes = Number.parseInt(
    String(formData.get("estimated_duration_minutes") ?? "45"),
    10
  );

  // Indices reflect the client's reordered list, not the original generation order.
  const topics: OutlineTopic[] = [];
  let i = 0;
  while (formData.has(`topics[${i}].name`)) {
    topics.push(parseTopicFromForm(formData, i));
    i += 1;
  }

  return {
    title,
    description,
    topics,
    total_points,
    estimated_duration_minutes,
  };
}

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
    if (e instanceof ApiError && e.status === 404) {
      notFound();
    }
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
    const editedOutline = parseOutlineFromForm(formData);

    if (!(slug && domain)) {
      redirect(
        `/modules/new/${run_id}?error=${encodeURIComponent("Slug and domain are required.")}`
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
        redirect(
          `/modules/new/${run_id}?error=${encodeURIComponent(e.message)}`
        );
      }
      throw e;
    }
  }

  let totalQuestions = 0;
  let totalWeight = 0;
  for (const t of outline.topics) {
    totalQuestions += t.question_count || 0;
    totalWeight += t.weight_pct || 0;
  }

  return (
    <>
      <Header page="Review outline" pages={["Modules", "New module"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <p className="eyebrow-label">Step 2 of 2 · Outline review</p>
          <h2 className="mt-1 font-semibold text-2xl">{outline.title}</h2>
          <p className="mt-1 max-w-prose text-muted-foreground text-sm">
            {outline.description}
          </p>
          <p className="mt-2 text-muted-foreground text-xs">
            {outline.topics.length} topics, {totalQuestions} questions, est.{" "}
            {outline.estimated_duration_minutes} min, weight sum{" "}
            <span
              className={
                Math.abs(totalWeight - 100) > 1 ? "text-warning" : undefined
              }
            >
              {totalWeight}%
            </span>
          </p>
          <details className="mt-2 text-muted-foreground text-xs">
            <summary className="cursor-pointer">Generation stats</summary>
            <p className="mt-1">
              Model {run.model}, {run.tokens_in} to {run.tokens_out} tokens,{" "}
              {run.latency_ms} ms
            </p>
          </details>
        </section>

        <AlertBanner>{error}</AlertBanner>

        <OutlineReviewForm
          formAction={action}
          outline={outline}
          runId={run_id}
        />
      </div>
    </>
  );
}
