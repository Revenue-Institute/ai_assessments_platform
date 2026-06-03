import { PromptMarkdown } from "@repo/design-system/components/prompt-markdown";
import { notFound, redirect } from "next/navigation";

import {
  ApiError,
  type CandidateQuestionView,
  completeAssignment,
  fetchQuestion,
  submitQuestion,
} from "@/lib/api";
import { ErrorView } from "@/app/components/error-view";

import { CandidateMonitor } from "./candidate-monitor";
import { parseSubmittedAnswer } from "./parse-answer";
import { QuestionNavigator } from "./question-navigator";
import { QuestionRenderer } from "./renderer";
import { SubmitButton } from "./submit-button";
import { CountdownTimer } from "./timer";

interface Params {
  index: string;
  token: string;
}

type SearchParams = Promise<{ error?: string }>;

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}) {
  const { index } = await params;
  const idx = Number.parseInt(index, 10);
  return {
    title: Number.isNaN(idx)
      ? "Question · RI Assessment"
      : `Question ${idx + 1} · RI Assessment`,
  };
}

export default async function QuestionPage({
  params,
  searchParams,
}: {
  params: Promise<Params>;
  searchParams: SearchParams;
}) {
  const { token, index } = await params;
  const { error: submitError } = await searchParams;

  const idx = Number.parseInt(index, 10);
  if (!token || token.length < 16 || Number.isNaN(idx) || idx < 0) {
    notFound();
  }

  let question: CandidateQuestionView;
  try {
    question = await fetchQuestion(token, idx);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 409 || error.status === 410) {
        redirect(`/a/${token}`);
      }
      return (
        <ErrorView
          headline={error.status === 404 ? "Question not found" : undefined}
          message={error.message}
          status={error.status}
        />
      );
    }
    throw error;
  }

  async function handleSubmit(formData: FormData): Promise<void> {
    "use server";
    const parsed = parseSubmittedAnswer(formData, token, idx);
    try {
      const result = await submitQuestion(token, idx, parsed);
      if (result.next_index === null) {
        await completeAssignment(token);
        redirect(`/a/${token}/done`);
      }
      redirect(`/a/${token}/q/${result.next_index}`);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 410) {
          redirect(`/a/${token}`);
        }
        redirect(
          `/a/${token}/q/${idx}?error=${encodeURIComponent(error.message)}`
        );
      }
      throw error;
    }
  }

  const isInteractive = ["code", "sql", "diagram", "notebook", "n8n"].includes(
    question.type
  );
  const shellClass = isInteractive
    ? "mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8"
    : "mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10";
  const promptClass = "text-base leading-relaxed";
  const formClass = isInteractive
    ? "grid gap-4 xl:grid-cols-[minmax(0,1fr)_220px]"
    : "space-y-3";

  return (
    <main className={shellClass} id="main">
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-primary focus:px-3 focus:py-2 focus:font-medium focus:text-primary-foreground"
        href="#answer-form"
      >
        Skip to answer form
      </a>
      <CandidateMonitor
        assignmentId={question.assignment_id}
        questionIndex={idx}
        token={token}
      />
      <QuestionNavigator current={idx} total={question.total} />

      <header className="flex flex-wrap items-center justify-between gap-3">
        <p className="eyebrow-label">
          Question {idx + 1} of {question.total}
        </p>
        <CountdownTimer deadlineIso={question.expires_at} />
      </header>

      <article className="space-y-2" id="question-prompt">
        <PromptMarkdown
          className={promptClass}
          source={question.rendered_prompt}
        />
        {question.competency_tags.length > 0 && (
          <p className="text-muted-foreground text-xs">
            {question.competency_tags.map((t) => `#${t}`).join("  ")}
          </p>
        )}
      </article>

      {submitError && (
        <p
          aria-live="assertive"
          className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
          role="alert"
        >
          {submitError}
        </p>
      )}

      <form
        action={handleSubmit}
        aria-label={`Question ${idx + 1} answer form`}
        className={formClass}
        id="answer-form"
      >
        <div className="min-w-0">
          <QuestionRenderer question={question} token={token} />
        </div>
        <aside
          className={
            isInteractive ? "space-y-3 xl:sticky xl:top-6 xl:self-start" : ""
          }
        >
          <SubmitButton
            assignmentId={question.assignment_id}
            last={idx === question.total - 1}
            questionIndex={idx}
          />
          {isInteractive && (
            <p className="rounded border border-border/50 bg-muted/20 px-3 py-2 text-muted-foreground text-xs">
              Use the tool area to build and test your answer. Save and continue
              submits the current state for this question.
            </p>
          )}
        </aside>
      </form>
    </main>
  );
}

