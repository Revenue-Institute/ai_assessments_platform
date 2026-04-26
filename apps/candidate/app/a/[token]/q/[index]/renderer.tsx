import type { CandidateQuestionView } from "@/lib/api";
import { CodeRenderer } from "./code-editor";
import { DiagramRenderer } from "./diagram-editor";
import { SqlRenderer } from "./sql-editor";

export function QuestionRenderer({
  question,
  token,
}: {
  question: CandidateQuestionView;
  token: string;
}) {
  switch (question.type) {
    case "mcq":
      return <McqRenderer question={question} />;
    case "short_answer":
      return <ShortAnswerRenderer question={question} />;
    case "long_answer":
      return <LongAnswerRenderer question={question} />;
    case "code": {
      const config = (question.interactive_config ?? {}) as {
        language?: string;
        starter_code?: string;
        visible_tests?: string;
        packages?: string[];
      };
      const previousCode = (question.raw_answer?.value as { code?: string } | undefined)
        ?.code;
      const initial = previousCode ?? config.starter_code ?? "";
      return (
        <CodeRenderer
          config={config}
          hasVisibleTests={!!config.visible_tests}
          initialCode={initial}
          questionIndex={question.index}
          token={token}
        />
      );
    }
    case "sql": {
      const config = (question.interactive_config ?? {}) as {
        schema_sql?: string;
        seed_sql?: string;
        starter_sql?: string;
      };
      const previousSql = (question.raw_answer?.value as { sql?: string } | undefined)
        ?.sql;
      const initial =
        previousSql ?? config.starter_sql ?? "-- Write your SQL here\nSELECT 1;";
      return (
        <SqlRenderer
          config={config}
          initialSql={initial}
          questionIndex={question.index}
          token={token}
        />
      );
    }
    case "diagram": {
      const config = (question.interactive_config ?? {}) as {
        starter_nodes?: Array<{
          id?: string;
          label?: string;
          type?: string;
          position?: { x: number; y: number };
        }>;
        starter_edges?: Array<{
          id?: string;
          source: string;
          target: string;
          label?: string;
        }>;
        palette?: Array<{ type: string; label: string }>;
      };
      const previous = (question.raw_answer?.value as
        | { diagram?: Parameters<typeof DiagramRenderer>[0]["initialAnswer"] }
        | undefined)?.diagram;
      return <DiagramRenderer config={config} initialAnswer={previous} />;
    }
    default:
      return <UnsupportedRenderer question={question} />;
  }
}

function McqRenderer({ question }: { question: CandidateQuestionView }) {
  const config = question.interactive_config ?? {};
  const options = (config.options as string[] | undefined) ?? [];
  const previous = (question.raw_answer?.value as { selected?: string } | undefined)
    ?.selected;

  return (
    <fieldset className="space-y-2 rounded-lg border border-emerald-900/60 bg-emerald-950/40 p-4">
      <legend className="px-1 text-emerald-300/70 text-xs uppercase tracking-wide">
        Choose one
      </legend>
      {options.map((opt, i) => (
        <label
          className="flex cursor-pointer items-start gap-3 rounded border border-transparent px-2 py-2 hover:border-emerald-800/60 hover:bg-emerald-900/30"
          key={`${i}-${opt}`}
        >
          <input
            className="mt-1"
            defaultChecked={previous === opt}
            name="answer"
            required
            type="radio"
            value={opt}
            onChange={undefined}
          />
          <input name="answer_index" type="hidden" value={String(i)} />
          <span className="text-sm leading-6">{opt}</span>
        </label>
      ))}
    </fieldset>
  );
}

function ShortAnswerRenderer({
  question,
}: {
  question: CandidateQuestionView;
}) {
  const previous = (question.raw_answer?.value as { text?: string } | undefined)
    ?.text;
  return (
    <input
      autoComplete="off"
      className="w-full rounded border border-emerald-900/60 bg-emerald-950/40 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
      defaultValue={previous ?? ""}
      maxLength={300}
      name="answer"
      placeholder="Your answer"
      required
      type="text"
    />
  );
}

function LongAnswerRenderer({
  question,
}: {
  question: CandidateQuestionView;
}) {
  const previous = (question.raw_answer?.value as { text?: string } | undefined)
    ?.text;
  return (
    <textarea
      className="h-48 w-full rounded border border-emerald-900/60 bg-emerald-950/40 px-3 py-2 text-sm leading-6 focus:border-emerald-500 focus:outline-none"
      defaultValue={previous ?? ""}
      maxLength={4000}
      name="answer"
      placeholder="Write your answer"
      required
    />
  );
}

function UnsupportedRenderer({
  question,
}: {
  question: CandidateQuestionView;
}) {
  return (
    <div className="rounded-lg border border-amber-900/60 bg-amber-950/30 p-4 text-amber-100 text-sm">
      <p className="font-medium">Renderer not yet wired</p>
      <p className="mt-1 text-amber-100/80">
        Question type <code>{question.type}</code> renders in a later phase.
        Submit a placeholder to advance.
      </p>
      <input name="answer" type="hidden" value="(not yet supported)" />
    </div>
  );
}
