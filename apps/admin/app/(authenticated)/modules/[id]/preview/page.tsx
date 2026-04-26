import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getModule, previewModule } from "@/lib/api";
import { Header } from "../../../components/header";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

export default async function ModulePreviewPage({
  params,
}: {
  params: Params;
}) {
  const { id } = await params;

  let detail: Awaited<ReturnType<typeof getModule>>;
  let preview: Awaited<ReturnType<typeof previewModule>>;
  try {
    [detail, preview] = await Promise.all([getModule(id), previewModule(id)]);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <>
      <Header
        page={`Preview: ${detail.title}`}
        pages={["Modules", detail.title]}
      />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <p className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-amber-200 text-xs">
          Admin preview. Variables are sampled deterministically and
          answer-revealing fields are stripped, matching the candidate view.
          Answers are not graded here.
        </p>

        <div>
          <Link
            className="text-emerald-300 text-sm hover:underline"
            href={`/modules/${id}`}
          >
            &larr; Back to module
          </Link>
        </div>

        {preview.questions.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            This module has no questions yet.
          </p>
        ) : (
          <ol className="space-y-4">
            {preview.questions.map((q, i) => (
              <li
                className="rounded-xl border border-border/50 bg-muted/20 p-4"
                key={q.question_template_id}
              >
                <header className="mb-2 flex items-center justify-between">
                  <p className="text-emerald-300/70 text-xs uppercase tracking-widest">
                    Question {i + 1} of {preview.questions.length} &middot;{" "}
                    {q.type}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {q.max_points} pts
                    {q.time_limit_seconds != null
                      ? ` · ${q.time_limit_seconds}s`
                      : ""}
                  </p>
                </header>

                <h2 className="mb-2 whitespace-pre-wrap font-medium text-base">
                  {q.rendered_prompt}
                </h2>

                {q.competency_tags.length > 0 && (
                  <p className="mb-2 text-emerald-300/60 text-xs">
                    {q.competency_tags.map((t) => `#${t}`).join("  ")}
                  </p>
                )}

                {q.interactive_config && (
                  <details className="rounded border border-border/40 bg-background/40 p-2 text-xs">
                    <summary className="cursor-pointer text-muted-foreground">
                      Interactive config (sanitized)
                    </summary>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap">
                      {JSON.stringify(q.interactive_config, null, 2)}
                    </pre>
                  </details>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </>
  );
}
