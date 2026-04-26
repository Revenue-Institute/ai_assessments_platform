import { notFound, redirect } from "next/navigation";
import {
  ApiError,
  type CandidateQuestionView,
  completeAssignment,
  fetchQuestion,
  submitQuestion,
} from "@/lib/api";
import { CandidateMonitor } from "./candidate-monitor";
import { QuestionRenderer } from "./renderer";

type Params = { token: string; index: string };
type SearchParams = Promise<{ error?: string }>;

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
            {error.status === 404 ? "Question not found" : "Something went wrong"}
          </h1>
          <p className="text-emerald-100/70 text-sm">{error.message}</p>
        </main>
      );
    }
    throw error;
  }

  async function handleSubmit(formData: FormData): Promise<void> {
    "use server";
    const raw = formData.get("answer");
    let parsed: unknown = raw;
    if (typeof raw === "string") {
      const trimmed = raw.trim();
      if (trimmed.length === 0) {
        redirect(
          `/a/${token}/q/${idx}?error=${encodeURIComponent("Please provide an answer.")}`
        );
      }
      // Renderers that own a structured shape (code, multi-part) emit the
      // answer as JSON. Plain string values mean a legacy renderer (mcq,
      // short, long) — wrap accordingly.
      if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
        try {
          parsed = JSON.parse(trimmed);
        } catch {
          parsed = { text: trimmed };
        }
      } else {
        const selectedIndex = formData.get("answer_index");
        if (typeof selectedIndex === "string" && selectedIndex.length > 0) {
          const parsedIndex = Number.parseInt(selectedIndex, 10);
          parsed = Number.isNaN(parsedIndex)
            ? { selected: trimmed }
            : { selected_index: parsedIndex, selected: trimmed };
        } else {
          parsed = { text: trimmed };
        }
      }
    }
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

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <CandidateMonitor token={token} />

      <header className="flex items-center justify-between">
        <p className="text-emerald-300/70 text-xs uppercase tracking-widest">
          Question {idx + 1} of {question.total}
        </p>
        <Deadline expiresAt={question.expires_at} />
      </header>

      <article className="space-y-2">
        <h1 className="whitespace-pre-wrap font-medium text-xl leading-relaxed">
          {question.rendered_prompt}
        </h1>
        {question.competency_tags.length > 0 && (
          <p className="text-emerald-300/60 text-xs">
            {question.competency_tags.map((t) => `#${t}`).join("  ")}
          </p>
        )}
      </article>

      {submitError && (
        <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
          {submitError}
        </p>
      )}

      <form action={handleSubmit} className="space-y-3">
        <QuestionRenderer question={question} token={token} />
        <SubmitButton last={idx === question.total - 1} />
      </form>
    </main>
  );
}

function Deadline({ expiresAt }: { expiresAt: string }) {
  // Server-rendered fixed timestamp; the live ticking countdown lands when
  // we wire a client-side timer on top of the server-authoritative deadline.
  const date = new Date(expiresAt);
  return (
    <p className="text-emerald-100/60 text-xs">
      Expires {date.toLocaleString()}
    </p>
  );
}

function SubmitButton({ last }: { last: boolean }) {
  return (
    <button
      className="w-full rounded bg-emerald-500 px-3 py-3 font-medium text-emerald-950 hover:bg-emerald-400"
      type="submit"
    >
      {last ? "Submit and finish" : "Save and continue"}
    </button>
  );
}
