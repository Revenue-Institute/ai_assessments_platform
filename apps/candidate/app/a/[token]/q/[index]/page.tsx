import { PromptMarkdown } from "@repo/design-system/components/prompt-markdown";
import { notFound, redirect } from "next/navigation";
import {
  ApiError,
  type CandidateQuestionView,
  completeAssignment,
  fetchQuestion,
  submitQuestion,
} from "@/lib/api";
import { CandidateMonitor } from "./candidate-monitor";
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
        <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
          <h1 className="font-semibold text-2xl">
            {error.status === 404
              ? "Question not found"
              : "Something went wrong"}
          </h1>
          <p className="text-muted-foreground text-sm">{error.message}</p>
        </main>
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
  const promptClass = isInteractive
    ? "text-base leading-relaxed"
    : "text-base leading-relaxed";
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

function parseSubmittedAnswer(formData: FormData, token: string, idx: number) {
  return (
    parseMultiSelectAnswer(formData, token, idx) ??
    parseScenarioAnswer(formData, token, idx) ??
    parseScalarAnswer(formData, token, idx)
  );
}

function parseMultiSelectAnswer(
  formData: FormData,
  token: string,
  idx: number
) {
  const checkedIndices = formData.getAll("answer_indices");
  if (checkedIndices.length === 0) {
    return null;
  }
  const ints = checkedIndices
    .map((v) => Number.parseInt(String(v), 10))
    .filter((n) => !Number.isNaN(n))
    .sort((a, b) => a - b);
  if (ints.length === 0) {
    redirectWithSubmitError(token, idx, "Please select at least one answer.");
  }
  return { selected_indices: ints };
}

function parseScenarioAnswer(formData: FormData, token: string, idx: number) {
  const responses: Record<string, string> = {};
  for (const [key, value] of formData.entries()) {
    if (key.startsWith("scenario_part:") && typeof value === "string") {
      responses[key.slice("scenario_part:".length)] = value.trim();
    }
  }
  if (Object.keys(responses).length === 0) {
    return null;
  }
  if (Object.values(responses).every((value) => value.length === 0)) {
    redirectWithSubmitError(token, idx, "Please provide an answer.");
  }
  return { responses };
}

function parseScalarAnswer(formData: FormData, token: string, idx: number) {
  const raw = formData.get("answer");
  if (typeof raw !== "string") {
    return raw;
  }
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    redirectWithSubmitError(token, idx, "Please provide an answer.");
  }
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      return JSON.parse(trimmed) as unknown;
    } catch {
      return { text: trimmed };
    }
  }
  return parseLegacySelectedAnswer(formData, trimmed);
}

function parseLegacySelectedAnswer(formData: FormData, selected: string) {
  const selectedIndex = formData.get("answer_index");
  if (typeof selectedIndex !== "string" || selectedIndex.length === 0) {
    return { text: selected };
  }
  const parsedIndex = Number.parseInt(selectedIndex, 10);
  return Number.isNaN(parsedIndex)
    ? { selected }
    : { selected_index: parsedIndex, selected };
}

function redirectWithSubmitError(token: string, idx: number, message: string) {
  redirect(`/a/${token}/q/${idx}?error=${encodeURIComponent(message)}`);
}
