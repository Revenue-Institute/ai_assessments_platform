/** Read-only preview renderers for every question type (spec §5.1).
 *
 * The candidate app has interactive renderers (Monaco, React Flow, n8n
 * iframe). The admin preview uses these inert mirrors so reviewers see
 * what a candidate would see without spinning up sandboxes or hitting
 * external services. Inputs are deliberately disabled so a stray click
 * cannot mutate state.
 *
 * Spec §6.6 (preview-variants) renders 5 sampled variants side-by-side;
 * this component handles a single sampled instance. The parent decides
 * how many to render. */

import type { ModulePreviewQuestion } from "@/lib/api";

type PreviewConfig = Record<string, unknown>;

export function QuestionPreviewRenderer({
  question,
}: {
  question: ModulePreviewQuestion;
}) {
  const config = (question.interactive_config ?? {}) as PreviewConfig;

  switch (question.type) {
    case "mcq":
      return <McqPreview config={config} />;
    case "multi_select":
      return <MultiSelectPreview config={config} />;
    case "short_answer":
      return <ShortAnswerPreview />;
    case "long_answer":
      return <LongAnswerPreview />;
    case "scenario":
      return <ScenarioPreview config={config} />;
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

function McqPreview({ config }: { config: PreviewConfig }) {
  const options = (config.options as string[] | undefined) ?? [];
  if (options.length === 0) return <EmptyOptions />;
  return (
    <fieldset
      className="space-y-2 rounded border border-border/60 bg-card/50 p-3"
      disabled
    >
      <legend className="px-1 text-muted-foreground text-xs">Choose one</legend>
      {options.map((opt, i) => (
        <label
          className="flex items-start gap-3 rounded px-2 py-1.5 text-sm"
          key={`${i}-${opt}`}
        >
          <input className="mt-1" disabled name="preview" type="radio" />
          <span className="leading-6">{opt}</span>
        </label>
      ))}
    </fieldset>
  );
}

function MultiSelectPreview({ config }: { config: PreviewConfig }) {
  const options = (config.options as string[] | undefined) ?? [];
  if (options.length === 0) return <EmptyOptions />;
  return (
    <fieldset
      className="space-y-2 rounded border border-border/60 bg-card/50 p-3"
      disabled
    >
      <legend className="px-1 text-muted-foreground text-xs">
        Choose all that apply
      </legend>
      {options.map((opt, i) => (
        <label
          className="flex items-start gap-3 rounded px-2 py-1.5 text-sm"
          key={`${i}-${opt}`}
        >
          <input className="mt-1" disabled name="preview" type="checkbox" />
          <span className="leading-6">{opt}</span>
        </label>
      ))}
    </fieldset>
  );
}

function ShortAnswerPreview() {
  return (
    <input
      aria-label="Candidate would type a short answer here"
      className="w-full rounded border border-border/60 bg-card/40 px-3 py-2 text-sm"
      disabled
      placeholder="Candidate types a short answer"
      type="text"
    />
  );
}

function LongAnswerPreview() {
  return (
    <textarea
      aria-label="Candidate would type a long answer here"
      className="h-32 w-full rounded border border-border/60 bg-card/40 px-3 py-2 text-sm leading-6"
      disabled
      placeholder="Candidate types a paragraph response"
    />
  );
}

function ScenarioPreview({ config }: { config: PreviewConfig }) {
  const parts = config.parts as
    | Array<{ id?: string; label?: string; placeholder?: string }>
    | undefined;
  if (Array.isArray(parts) && parts.length > 0) {
    return (
      <div className="space-y-3">
        {parts.map((part, i) => (
          <label className="block space-y-1" key={part.id ?? i}>
            <span className="block font-medium text-foreground text-sm">
              {part.label ?? `Part ${i + 1}`}
            </span>
            <textarea
              className="h-24 w-full rounded border border-border/60 bg-card/40 px-3 py-2 text-sm leading-6"
              disabled
              placeholder={part.placeholder ?? "Candidate response"}
            />
          </label>
        ))}
      </div>
    );
  }
  return (
    <textarea
      aria-label="Candidate would write a scenario response here"
      className="h-40 w-full rounded border border-border/60 bg-card/40 px-3 py-2 text-sm leading-6"
      disabled
      placeholder="Candidate walks through each part of the scenario"
    />
  );
}

function CodePreview({ config }: { config: PreviewConfig }) {
  const language = (config.language as string | undefined) ?? "python";
  const starter = (config.starter_code as string | undefined) ?? "";
  const visible = config.visible_tests as string | undefined;
  const packages = (config.packages as string[] | undefined) ?? [];
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-muted-foreground text-xs">
        <span className="font-mono uppercase">{language}</span>
        {packages.length > 0 && (
          <span>{`packages: ${packages.join(", ")}`}</span>
        )}
      </div>
      <CodeBlock
        ariaLabel={`Starter code (${language})`}
        body={starter || "(empty starter)"}
      />
      {visible && (
        <details className="rounded border border-border/40 bg-background/30 text-xs">
          <summary className="cursor-pointer px-2 py-1 text-muted-foreground">
            Visible tests (candidate can run these)
          </summary>
          <CodeBlock ariaLabel="Visible tests" body={visible} muted />
        </details>
      )}
    </div>
  );
}

function SqlPreview({ config }: { config: PreviewConfig }) {
  const schema = config.schema_sql as string | undefined;
  const seed = config.seed_sql as string | undefined;
  const starter = (config.starter_sql as string | undefined) ?? "-- Candidate writes their SQL here";
  return (
    <div className="space-y-2">
      <p className="font-mono text-muted-foreground text-xs uppercase">sql</p>
      <CodeBlock ariaLabel="Starter SQL" body={starter} />
      {(schema || seed) && (
        <details className="rounded border border-border/40 bg-background/30 text-xs">
          <summary className="cursor-pointer px-2 py-1 text-muted-foreground">
            Sandbox schema + seed (candidate sees the resulting tables)
          </summary>
          {schema && <CodeBlock ariaLabel="Schema SQL" body={schema} muted />}
          {seed && <CodeBlock ariaLabel="Seed SQL" body={seed} muted />}
        </details>
      )}
    </div>
  );
}

type StarterCell = { type: "code" | "markdown"; source?: string };

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
            key={`${cell.type}-${i}`}
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
  const palette = (config.palette as
    | Array<{ type: string; label: string }>
    | undefined) ?? [];
  const starterNodes = (config.starter_nodes as Array<unknown> | undefined) ?? [];
  return (
    <div className="space-y-2 rounded border border-border/60 bg-card/40 p-4">
      <p className="font-mono text-muted-foreground text-xs uppercase">
        diagram
      </p>
      <p className="text-muted-foreground text-sm">
        Candidates build a process diagram on a React Flow canvas. The
        full editor is only available in the candidate app; preview
        shows the palette and starter shape.
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
        Candidates build an n8n workflow in an embedded n8n workspace
        (full editor, drag-and-drop nodes, run executions). The workspace
        provisions only when a candidate opens the question; preview is
        not available here.
      </p>
    </div>
  );
}

function UnsupportedPreview({ type }: { type: string }) {
  return (
    <p
      className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-warning text-sm"
      role="alert"
    >
      {`No preview for question type "${type}".`}
    </p>
  );
}

function EmptyOptions() {
  return (
    <p
      className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-warning text-xs"
      role="alert"
    >
      No options configured for this choice question.
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
    <pre
      aria-label={ariaLabel}
      className={`max-h-72 overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-xs leading-6 ${
        muted ? "bg-muted/20" : "bg-muted/40"
      }`}
    >
      {body || "(empty)"}
    </pre>
  );
}
