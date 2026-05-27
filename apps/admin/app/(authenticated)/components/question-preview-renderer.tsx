"use client";

/** Read-only preview renderers for every question type (spec §5.1).
 *
 * The static types (mcq, multi_select, short_answer, long_answer,
 * scenario) come from the shared @repo/design-system question-renderer
 * package in `mode="preview"`; this keeps admin previews and the
 * candidate runtime in lockstep on form shape + accessibility labeling.
 *
 * The interactive-sandbox previews (code, sql, notebook, diagram, n8n)
 * stay local because they render disabled chrome around starter
 * artifacts and never spin up sandboxes or hit external services. */

import {
  LongAnswerRenderer,
  McqRenderer,
  MultiSelectRenderer,
  ScenarioRenderer,
  ShortAnswerRenderer,
} from "@repo/design-system/components/question-renderer";
import dynamic from "next/dynamic";
import type { ModulePreviewQuestion } from "@/lib/api";

// Lazy-load Monaco so it only ships in the preview routes. The read-only
// editor renders identically to what candidates see (vs-dark theme,
// matching syntax highlighting), without the Run / Test wiring.
const CodePreviewMonaco = dynamic(
  () => import("./code-preview").then((m) => m.CodePreviewMonaco),
  {
    ssr: false,
    loading: () => (
      <div
        aria-hidden="true"
        className="h-[260px] animate-pulse rounded-lg border border-border bg-muted/40"
      />
    ),
  }
);

type PreviewConfig = Record<string, unknown>;

export function QuestionPreviewRenderer({
  question,
}: {
  question: ModulePreviewQuestion;
}) {
  const config = (question.interactive_config ?? {}) as PreviewConfig;

  switch (question.type) {
    case "mcq":
      return <McqRenderer mode="preview" question={question} />;
    case "multi_select":
      return <MultiSelectRenderer mode="preview" question={question} />;
    case "short_answer":
      return <ShortAnswerRenderer mode="preview" question={question} />;
    case "long_answer":
      return <LongAnswerRenderer mode="preview" question={question} />;
    case "scenario":
      return <ScenarioRenderer mode="preview" question={question} />;
    case "code":
      return <CodePreview config={config} />;
    case "sql":
      return <SqlPreview config={config} />;
    case "notebook":
      return <NotebookPreview config={config} />;
    case "diagram":
      return <DiagramPreview config={config} />;
    case "n8n":
      return <N8nPreview />;
    default:
      return <UnsupportedPreview type={question.type} />;
  }
}

function EditorChrome({
  language,
  rightSlot,
  children,
}: {
  language: string;
  rightSlot?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card/40">
      <div className="flex items-center justify-between border-border/60 border-b bg-muted/40 px-3 py-1.5">
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-destructive/60" />
            <span className="h-2.5 w-2.5 rounded-full bg-warning/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-primary/70" />
          </span>
          <span className="font-mono text-[11px] text-muted-foreground uppercase tracking-wide">
            {language}
          </span>
        </div>
        {rightSlot}
      </div>
      {children}
    </div>
  );
}

function CodePreview({ config }: { config: PreviewConfig }) {
  const language = (config.language as string | undefined) ?? "python";
  const starter = (config.starter_code as string | undefined) ?? "";
  const visible = config.visible_tests as string | undefined;
  const packages = (config.packages as string[] | undefined) ?? [];
  return (
    <div className="space-y-3">
      <EditorChrome
        language={language}
        rightSlot={
          packages.length > 0 ? (
            <span className="text-muted-foreground text-xs">
              {`packages: ${packages.join(", ")}`}
            </span>
          ) : (
            <span className="text-muted-foreground text-xs">
              read-only preview
            </span>
          )
        }
      >
        <CodePreviewMonaco code={starter} language={language} />
      </EditorChrome>
      {visible && (
        <details className="rounded-lg border border-border/40 bg-card/40">
          <summary className="cursor-pointer border-border/40 border-b bg-muted/30 px-3 py-1.5 text-muted-foreground text-xs">
            Visible tests (candidate can run these from a Run tests button)
          </summary>
          <CodePreviewMonaco
            code={visible}
            height="180px"
            language={language}
          />
        </details>
      )}
    </div>
  );
}

function SqlPreview({ config }: { config: PreviewConfig }) {
  const schema = config.schema_sql as string | undefined;
  const seed = config.seed_sql as string | undefined;
  const starter =
    (config.starter_sql as string | undefined) ??
    "-- Candidate writes their SQL here";
  return (
    <div className="space-y-3">
      <EditorChrome
        language="sql"
        rightSlot={
          <span className="text-muted-foreground text-xs">DuckDB sandbox</span>
        }
      >
        <CodePreviewMonaco code={starter} language="sql" />
      </EditorChrome>
      {(schema || seed) && (
        <details className="rounded-lg border border-border/40 bg-card/40">
          <summary className="cursor-pointer border-border/40 border-b bg-muted/30 px-3 py-1.5 text-muted-foreground text-xs">
            Sandbox schema + seed (the resulting tables are queryable)
          </summary>
          <div className="space-y-2 p-2">
            {schema && (
              <CodePreviewMonaco code={schema} height="160px" language="sql" />
            )}
            {seed && (
              <CodePreviewMonaco code={seed} height="160px" language="sql" />
            )}
          </div>
        </details>
      )}
    </div>
  );
}

interface StarterCell {
  source?: string;
  type: "code" | "markdown";
}

function NotebookPreview({ config }: { config: PreviewConfig }) {
  const cells = (config.starter_cells as StarterCell[] | undefined) ?? [];
  const datasets = (config.dataset_urls as string[] | undefined) ?? [];
  return (
    <div className="space-y-2">
      <p className="font-mono text-muted-foreground text-xs uppercase">
        notebook
      </p>
      {datasets.length > 0 && (
        <p className="text-muted-foreground text-xs">
          {`Datasets pre-loaded: ${datasets.join(", ")}`}
        </p>
      )}
      {cells.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          Empty starter notebook. Candidate writes from scratch.
        </p>
      ) : (
        cells.map((cell, i) => (
          <div
            className="rounded border border-border/40"
            key={`${cell.type}-${cell.source ?? i}`}
          >
            <p className="border-border/30 border-b bg-muted/30 px-2 py-1 font-mono text-[10px] text-muted-foreground uppercase">
              {cell.type}
            </p>
            <CodeBlock
              ariaLabel={`${cell.type} cell ${i + 1}`}
              body={cell.source ?? ""}
              muted
            />
          </div>
        ))
      )}
    </div>
  );
}

function DiagramPreview({ config }: { config: PreviewConfig }) {
  const palette =
    (config.palette as Array<{ type: string; label: string }> | undefined) ??
    [];
  const starterNodes = (config.starter_nodes as unknown[] | undefined) ?? [];
  return (
    <div className="space-y-2 rounded border border-border/60 bg-card/40 p-4">
      <p className="font-mono text-muted-foreground text-xs uppercase">
        diagram
      </p>
      <p className="text-muted-foreground text-sm">
        Candidates build a process diagram on a React Flow canvas. The full
        editor is only available in the candidate app; preview shows the palette
        and starter shape.
      </p>
      {palette.length > 0 && (
        <div>
          <p className="text-muted-foreground text-xs">Palette</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {palette.map((p) => (
              <li
                className="rounded border border-border/40 bg-background/40 px-2 py-0.5 text-xs"
                key={p.type}
              >
                {p.label}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-muted-foreground text-xs">
        {`${starterNodes.length} starter node${starterNodes.length === 1 ? "" : "s"} provided.`}
      </p>
    </div>
  );
}

function N8nPreview() {
  return (
    <div className="rounded border border-border/60 bg-card/40 p-4 text-sm">
      <p className="font-mono text-muted-foreground text-xs uppercase">n8n</p>
      <p className="mt-1">
        Candidates build an n8n workflow in an embedded n8n workspace (full
        editor, drag-and-drop nodes, run executions). The workspace provisions
        only when a candidate opens the question; preview is not available here.
      </p>
    </div>
  );
}

function UnsupportedPreview({ type }: { type: string }) {
  return (
    <p
      className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning"
      role="alert"
    >
      {`No preview for question type "${type}".`}
    </p>
  );
}

function CodeBlock({
  ariaLabel,
  body,
  muted = false,
}: {
  ariaLabel: string;
  body: string;
  muted?: boolean;
}) {
  return (
    <figure aria-label={ariaLabel}>
      <pre
        className={`max-h-72 overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-xs leading-6 ${
          muted ? "bg-muted/20" : "bg-muted/40"
        }`}
      >
        {body || "(empty)"}
      </pre>
    </figure>
  );
}
