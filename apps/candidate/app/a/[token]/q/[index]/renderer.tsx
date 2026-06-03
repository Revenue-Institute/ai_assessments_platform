import {
  LongAnswerRenderer,
  McqRenderer,
  MultiSelectRenderer,
  ScenarioRenderer,
  ShortAnswerRenderer,
} from "@repo/design-system/components/question-renderer";
import { parseCodeConfig, parseSqlConfig } from "@repo/schemas";

import type { CandidateQuestionView } from "@/lib/api";

import { CodeRenderer } from "./code-editor";
import { DiagramRenderer } from "./diagram-editor";
import { N8nRenderer } from "./n8n-editor";
import { NotebookRenderer } from "./notebook-editor";
import { SqlRenderer } from "./sql-editor";

/**
 * Top-level dispatch for candidate question rendering. Static types
 * (mcq, multi_select, short_answer, long_answer, scenario) come from
 * the shared @repo/design-system/components/question-renderer package
 * so the admin preview and the candidate runtime stay in lockstep.
 *
 * Interactive sandbox types (code, sql, notebook, diagram, n8n) stay
 * local because they wire Monaco / React Flow / n8n iframe / E2B fetch
 * calls that we deliberately keep out of the design-system surface.
 * Their `interactive_config` is parsed via the shared parseXxxConfig
 * helpers where the Zod schema covers the editor's shape; the diagram
 * and notebook configs carry UI-only fields (palette, starter_cells,
 * starter_edges) that the Zod schemas do not yet model, so those
 * editors keep their local cast.
 */
export function QuestionRenderer({
  question,
  token,
}: {
  question: CandidateQuestionView;
  token: string;
}) {
  switch (question.type) {
    case "mcq":
      return <McqRenderer mode="interactive" question={question} />;
    case "multi_select":
      return <MultiSelectRenderer mode="interactive" question={question} />;
    case "short_answer":
      return <ShortAnswerRenderer mode="interactive" question={question} />;
    case "long_answer":
      return <LongAnswerRenderer mode="interactive" question={question} />;
    case "scenario":
      return <ScenarioRenderer mode="interactive" question={question} />;
    case "code": {
      const config = parseCodeConfig(question.interactive_config);
      const previousCode = (
        question.raw_answer?.value as { code?: string } | undefined
      )?.code;
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
      const parsed = parseSqlConfig(question.interactive_config);
      // starter_sql is a UI-only field not in the Zod SqlConfig; pull
      // it directly from the raw config so the editor still gets a
      // sensible default.
      const raw = (question.interactive_config ?? {}) as {
        starter_sql?: string;
      };
      const previousSql = (
        question.raw_answer?.value as { sql?: string } | undefined
      )?.sql;
      const initial =
        previousSql ?? raw.starter_sql ?? "-- Write your SQL here\nSELECT 1;";
      return (
        <SqlRenderer
          config={parsed}
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
      const previous = (
        question.raw_answer?.value as
          | { diagram?: Parameters<typeof DiagramRenderer>[0]["initialAnswer"] }
          | undefined
      )?.diagram;
      return <DiagramRenderer config={config} initialAnswer={previous} />;
    }
    case "notebook": {
      const config = (question.interactive_config ?? {}) as {
        dataset_urls?: string[];
        starter_cells?: Array<{
          id?: string;
          type: "code" | "markdown";
          source: string;
        }>;
      };
      const previous = (
        question.raw_answer?.value as
          | {
              cells?: Array<{
                id?: string;
                type: "code" | "markdown";
                source: string;
              }>;
            }
          | undefined
      )?.cells;
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
      const previous = (
        question.raw_answer?.value as { workflow_id?: string } | undefined
      )?.workflow_id;
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

function UnsupportedRenderer({
  question,
}: {
  question: CandidateQuestionView;
}) {
  return (
    <div
      className="rounded border border-warning/40 bg-warning/10 p-4 text-sm text-warning"
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
