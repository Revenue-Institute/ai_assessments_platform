import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import {
  ApiError,
  createModulePreviewMagicLink,
  getModule,
  previewModule,
} from "@/lib/api";
import { Header } from "../../../components/header";
import { QuestionPreviewRenderer } from "../../../components/question-preview-renderer";

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

  async function openAsCandidate(): Promise<void> {
    "use server";
    const link = await createModulePreviewMagicLink(id);
    redirect(link.magic_link_url);
  }

  return (
    <>
      <Header
        page={`Preview: ${detail.title}`}
        pages={["Modules", detail.title]}
      />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border/50 bg-muted/20 p-4">
          <div className="space-y-1">
            <p className="eyebrow-label">Read-only review</p>
            <p className="text-muted-foreground text-sm">
              Variables are sampled deterministically and answer-revealing
              fields are stripped. To drive the live experience (Monaco
              run / test, server timer, integrity monitor), open as a
              candidate.
            </p>
          </div>
          <form action={openAsCandidate}>
            <button className="btn-primary text-sm" type="submit">
              Open as candidate
            </button>
          </form>
        </section>

        <div>
          <Link
            className="text-primary text-sm hover:underline"
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
                  <p className="eyebrow-label">
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
                  <p className="mb-3 text-muted-foreground text-xs">
                    {q.competency_tags.map((t) => `#${t}`).join("  ")}
                  </p>
                )}

                <QuestionPreviewRenderer question={q} />
              </li>
            ))}
          </ol>
        )}
      </div>
    </>
  );
}
