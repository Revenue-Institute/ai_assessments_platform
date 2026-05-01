import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import {
  ApiError,
  type AssessmentDetail,
  createAssessmentPreviewMagicLink,
  getAssessment,
  type ModulePreviewResponse,
  previewModule,
} from "@/lib/api";
import { Header } from "../../../components/header";
import { QuestionPreviewRenderer } from "../../../components/question-preview-renderer";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

type ModulePreviewBlock = {
  moduleId: string;
  moduleTitle: string;
  preview: ModulePreviewResponse | null;
  error: string | null;
};

export default async function AssessmentPreviewPage({
  params,
}: {
  params: Params;
}) {
  const { id } = await params;

  let detail: AssessmentDetail;
  try {
    detail = await getAssessment(id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  async function openAsCandidate(): Promise<void> {
    "use server";
    const link = await createAssessmentPreviewMagicLink(id);
    redirect(link.magic_link_url);
  }

  const blocks: ModulePreviewBlock[] = await Promise.all(
    detail.modules.map(async (m) => {
      try {
        const preview = await previewModule(m.module_id);
        return {
          moduleId: m.module_id,
          moduleTitle: m.title,
          preview,
          error: null,
        };
      } catch (e) {
        return {
          moduleId: m.module_id,
          moduleTitle: m.title,
          preview: null,
          error:
            e instanceof ApiError
              ? e.message
              : "Failed to load module preview.",
        };
      }
    })
  );

  let questionOffset = 0;
  const totalQuestions = blocks.reduce(
    (acc, b) => acc + (b.preview?.questions.length ?? 0),
    0
  );

  return (
    <>
      <Header
        page={`Preview: ${detail.title}`}
        pages={["Assessments", detail.title]}
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
            href={`/assessments/${id}`}
          >
            {"← Back to assessment"}
          </Link>
        </div>

        {detail.modules.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            This assessment has no modules yet.
          </p>
        ) : (
          <div className="space-y-6">
            {blocks.map((block, blockIndex) => {
              const startOffset = questionOffset;
              const count = block.preview?.questions.length ?? 0;
              questionOffset += count;
              return (
                <section
                  className="rounded-xl border border-border/50 bg-muted/20 p-4"
                  key={block.moduleId}
                >
                  <header className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="eyebrow-label">
                        Module {blockIndex + 1} of {blocks.length}
                      </p>
                      <h2 className="mt-0.5 font-semibold text-base">
                        {block.moduleTitle}
                      </h2>
                    </div>
                    <p className="text-muted-foreground text-xs">
                      {count} {count === 1 ? "question" : "questions"}
                    </p>
                  </header>

                  {block.error && (
                    <p
                      className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
                      role="alert"
                    >
                      {block.error}
                    </p>
                  )}

                  {block.preview && block.preview.questions.length === 0 && (
                    <p className="text-muted-foreground text-sm">
                      This module has no questions yet.
                    </p>
                  )}

                  {block.preview && block.preview.questions.length > 0 && (
                    <ol className="space-y-3">
                      {block.preview.questions.map((q, i) => (
                        <li
                          className="rounded-lg border border-border/40 bg-background/40 p-4"
                          key={q.question_template_id}
                        >
                          <header className="mb-2 flex items-center justify-between">
                            <p className="eyebrow-label">
                              Question {startOffset + i + 1} of {totalQuestions}{" "}
                              {"·"} {q.type}
                            </p>
                            <p className="text-muted-foreground text-xs">
                              {q.max_points} pts
                              {q.time_limit_seconds != null
                                ? ` · ${q.time_limit_seconds}s`
                                : ""}
                            </p>
                          </header>

                          <h3 className="mb-2 whitespace-pre-wrap font-medium text-base">
                            {q.rendered_prompt}
                          </h3>

                          {q.competency_tags.length > 0 && (
                            <p className="mb-3 text-muted-foreground text-xs">
                              {q.competency_tags
                                .map((t) => `#${t}`)
                                .join("  ")}
                            </p>
                          )}

                          <QuestionPreviewRenderer question={q} />
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
