import type { CandidateQuestionView } from "@/lib/api";
import { CodeRenderer } from "./code-editor";
import { DiagramRenderer } from "./diagram-editor";
import { N8nRenderer } from "./n8n-editor";
import { NotebookRenderer } from "./notebook-editor";
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
    case "multi_select":
      return <MultiSelectRenderer question={question} />;
    case "short_answer":
      return <ShortAnswerRenderer question={question} />;
    case "long_answer":
      return <LongAnswerRenderer question={question} />;
    case "scenario":
      return <ScenarioRenderer question={question} />;
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
    case "notebook": {
      const config = (question.interactive_config ?? {}) as {
        dataset_urls?: string[];
        starter_cells?: Array<{ type: "code" | "markdown"; source: string }>;
      };
      const previous = (question.raw_answer?.value as
        | { cells?: Array<{ type: "code" | "markdown"; source: string }> }
        | undefined)?.cells;
      return (
        <NotebookRenderer
          config={config}
          initialCells={previous}
          questionIndex={question.index}
          token={token}
        />
      );
    }
    case "n8n": {
      const previous = (question.raw_answer?.value as
        | { workflow_id?: string }
        | undefined)?.workflow_id;
      return (
        <N8nRenderer
          initialWorkflowId={previous ?? null}
          questionIndex={question.index}
          token={token}
        />
      );
    }
    default:
      return <UnsupportedRenderer question={question} />;
  }
}

function MultiSelectRenderer({ question }: { question: CandidateQuestionView }) {
  const config = question.interactive_config ?? {};
  const options = (config.options as string[] | undefined) ?? [];
  const previousIndices =
    (question.raw_answer?.value as { selected_indices?: number[] } | undefined)
      ?.selected_indices ?? [];

  return (
    <fieldset className="space-y-2 rounded border border-border bg-card p-4">
      <legend className="eyebrow-label px-1">Choose all that apply</legend>
      {options.map((opt, i) => (
        <label
          className="flex cursor-pointer items-start gap-3 rounded border border-transparent px-2 py-2 hover:border-primary/40 hover:bg-primary/5"
          key={`${i}-${opt}`}
        >
          <input
            className="mt-1"
            defaultChecked={previousIndices.includes(i)}
            name="answer_indices"
            type="checkbox"
            value={String(i)}
          />
          <span className="text-sm leading-6">{opt}</span>
        </label>
      ))}
    </fieldset>
  );
}

function ScenarioRenderer({ question }: { question: CandidateQuestionView }) {
  // Scenarios are multi-part rubric-graded prompts. When the generator
  // pins explicit parts in interactive_config we render labeled textareas
  // per part; otherwise we fall back to a single long-form input so the
  // candidate can structure their own response inline with the prompt.
  const config = question.interactive_config ?? {};
  const parts = config.parts as
    | Array<{ id?: string; label?: string; placeholder?: string }>
    | undefined;
  const previousResponses = (question.raw_answer?.value as
    | { responses?: Record<string, string>; text?: string }
    | undefined) ?? {};

  if (Array.isArray(parts) && parts.length > 0) {
    return (
      <div className="space-y-3">
        {parts.map((part, i) => {
          const partId = part.id ?? `part_${i + 1}`;
          const previous = previousResponses.responses?.[partId] ?? "";
          return (
            <label className="block space-y-1" key={partId}>
              <span className="block text-sm font-medium text-foreground">
                {part.label ?? `Part ${i + 1}`}
              </span>
              <textarea
                className="h-32 w-full rounded border border-border bg-card px-3 py-2 text-sm leading-6 focus:border-primary focus:outline-none"
                defaultValue={previous}
                maxLength={4000}
                name={`scenario_part:${partId}`}
                placeholder={part.placeholder ?? "Your response"}
                required
              />
            </label>
          );
        })}
      </div>
    );
  }

  return (
    <textarea
      className="h-56 w-full rounded border border-border bg-card px-3 py-2 text-sm leading-6 focus:border-primary focus:outline-none"
      defaultValue={previousResponses.text ?? ""}
      maxLength={6000}
      name="answer"
      placeholder="Walk through each part of the scenario."
      required
    />
  );
}

function McqRenderer({ question }: { question: CandidateQuestionView }) {
  const config = question.interactive_config ?? {};
  const options = (config.options as string[] | undefined) ?? [];
  const previous = (question.raw_answer?.value as { selected?: string } | undefined)
    ?.selected;

  return (
    <fieldset className="space-y-2 rounded border border-border bg-card p-4">
      <legend className="eyebrow-label px-1">Choose one</legend>
      {options.map((opt, i) => (
        <label
          className="flex cursor-pointer items-start gap-3 rounded border border-transparent px-2 py-2 hover:border-primary/40 hover:bg-primary/5"
          key={`${i}-${opt}`}
        >
          <input
            className="mt-1"
            defaultChecked={previous === opt}
            name="answer"
            required
            type="radio"
            value={opt}
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
      className="w-full rounded border border-border bg-card px-3 py-2 text-sm focus:border-primary focus:outline-none"
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
      className="h-48 w-full rounded border border-border bg-card px-3 py-2 text-sm leading-6 focus:border-primary focus:outline-none"
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
    <div
      className="rounded border border-warning/40 bg-warning/10 p-4 text-warning text-sm"
      role="alert"
    >
      <p className="font-medium">Unrecognized question type</p>
      <p className="mt-1 text-warning/80">
        We can&apos;t render <code>{question.type}</code> here. Please flag this
        to the Revenue Institute team. Your time and attempt are still being
        recorded.
      </p>
      <input name="answer" type="hidden" value="" />
    </div>
  );
}
