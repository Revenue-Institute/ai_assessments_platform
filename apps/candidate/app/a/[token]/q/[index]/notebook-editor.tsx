"use client";

import Editor from "@monaco-editor/react";
import { useState } from "react";
import { env } from "@/env";

type Cell = { type: "code" | "markdown"; source: string };

type CellOutput = {
  index: number;
  type: string;
  stdout: string;
  stderr: string;
  error: string | null;
  runtime_ms: number;
};

type RunResponse = {
  cells: CellOutput[];
  runtime_ms: number;
  timed_out: boolean;
};

const STARTER_CELL: Cell = {
  type: "code",
  source: "# Use the cells below to load and analyze the data.\n",
};

function bootstrapCells(initial: Cell[] | undefined, starter?: Cell[]): Cell[] {
  if (initial && initial.length > 0) return initial;
  if (starter && starter.length > 0) return starter;
  return [STARTER_CELL];
}

export function NotebookRenderer({
  token,
  questionIndex,
  config,
  initialCells,
}: {
  token: string;
  questionIndex: number;
  config: { dataset_urls?: string[]; starter_cells?: Cell[] };
  initialCells: Cell[] | undefined;
}) {
  const [cells, setCells] = useState<Cell[]>(
    bootstrapCells(initialCells, config.starter_cells)
  );
  const [outputs, setOutputs] = useState<Record<number, CellOutput>>({});
  const [running, setRunning] = useState(false);
  const [networkError, setNetworkError] = useState<string | null>(null);

  const apiBase = env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");

  function updateCell(i: number, source: string) {
    setCells((current) =>
      current.map((c, idx) => (idx === i ? { ...c, source } : c))
    );
  }

  function setCellType(i: number, type: Cell["type"]) {
    setCells((current) =>
      current.map((c, idx) => (idx === i ? { ...c, type } : c))
    );
  }

  function addCell(after: number, type: Cell["type"]) {
    setCells((current) => [
      ...current.slice(0, after + 1),
      { type, source: "" },
      ...current.slice(after + 1),
    ]);
  }

  function deleteCell(i: number) {
    setCells((current) =>
      current.length === 1 ? current : current.filter((_, idx) => idx !== i)
    );
    setOutputs((current) => {
      const next = { ...current };
      delete next[i];
      return next;
    });
  }

  async function runAll() {
    setRunning(true);
    setNetworkError(null);
    setOutputs({});
    try {
      const res = await fetch(
        `${apiBase}/a/${encodeURIComponent(token)}/notebook/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cells, question_index: questionIndex }),
        }
      );
      if (!res.ok) {
        const body = await safeJson(res);
        setNetworkError(body?.detail ?? `Run failed (${res.status})`);
        return;
      }
      const data = (await res.json()) as RunResponse;
      const map: Record<number, CellOutput> = {};
      for (const out of data.cells) map[out.index] = out;
      setOutputs(map);
    } catch (e) {
      setNetworkError(e instanceof Error ? e.message : "Network error.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <input name="answer" type="hidden" value={JSON.stringify({ cells })} />

      {(config.dataset_urls?.length ?? 0) > 0 && (
        <details className="rounded-lg border border-border bg-card p-3 text-xs">
          <summary className="cursor-pointer text-primary">
            Datasets in /data/
          </summary>
          <ul className="mt-2 space-y-1 text-muted-foreground">
            {config.dataset_urls?.map((u) => (
              <li className="break-all" key={u}>
                <code>{u}</code>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="flex items-center gap-2 text-xs">
        <button
          className="rounded bg-primary px-3 py-2 text-primary-foreground font-medium hover:bg-neon hover:text-deep-navy disabled:opacity-50"
          disabled={running}
          onClick={runAll}
          type="button"
        >
          {running ? "Running…" : "Run all"}
        </button>
        <span className="text-muted-foreground">
          Cells run in order in a stateful Python kernel.
        </span>
      </div>

      {networkError && (
        <p className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm">
          {networkError}
        </p>
      )}

      <ol className="space-y-3">
        {cells.map((cell, i) => (
          <li
            className="space-y-2 rounded-lg border border-border bg-card p-3"
            key={i}
          >
            <div className="flex items-center gap-2 text-xs">
              <span className="font-medium text-muted-foreground">
                Cell {i + 1}
              </span>
              <select
                className="rounded border border-border bg-card px-2 py-1"
                onChange={(e) => setCellType(i, e.target.value as Cell["type"])}
                value={cell.type}
              >
                <option value="code">code</option>
                <option value="markdown">markdown</option>
              </select>
              <div className="ml-auto flex items-center gap-1">
                <button
                  className="rounded border border-border px-2 py-0.5 text-[11px] hover:bg-primary/10"
                  onClick={() => addCell(i, "code")}
                  type="button"
                >
                  + code
                </button>
                <button
                  className="rounded border border-border px-2 py-0.5 text-[11px] hover:bg-primary/10"
                  onClick={() => addCell(i, "markdown")}
                  type="button"
                >
                  + markdown
                </button>
                <button
                  className="rounded border border-destructive/40 bg-destructive/10 px-2 py-0.5 text-[11px] text-destructive hover:bg-destructive/20 disabled:opacity-50"
                  disabled={cells.length === 1}
                  onClick={() => deleteCell(i)}
                  type="button"
                >
                  delete
                </button>
              </div>
            </div>

            {cell.type === "code" ? (
              <div
                className="overflow-hidden rounded border border-border"
                data-allow-paste="true"
              >
                <Editor
                  defaultLanguage="python"
                  height="180px"
                  onChange={(value) => updateCell(i, value ?? "")}
                  options={{
                    minimap: { enabled: false },
                    fontSize: 13,
                    scrollBeyondLastLine: false,
                  }}
                  theme="vs-dark"
                  value={cell.source}
                />
              </div>
            ) : (
              <textarea
                className="h-32 w-full rounded border border-border bg-card p-2 text-sm leading-6"
                onChange={(e) => updateCell(i, e.target.value)}
                placeholder="# Markdown notes..."
                value={cell.source}
              />
            )}

            {outputs[i] && cell.type === "code" && (
              <CellOutputView output={outputs[i]} />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function CellOutputView({ output }: { output: CellOutput }) {
  if (!output.stdout && !output.stderr && !output.error) {
    return (
      <p className="text-muted-foreground text-xs">
        No output. ({output.runtime_ms} ms)
      </p>
    );
  }
  return (
    <div className="space-y-2 text-xs">
      {output.stdout && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-secondary p-2 text-foreground">
          {output.stdout}
        </pre>
      )}
      {output.stderr && (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-amber-500/10 p-2 text-amber-300">
          {output.stderr}
        </pre>
      )}
      {output.error && (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-destructive/15 p-2 text-destructive">
          {output.error}
        </pre>
      )}
      <p className="text-muted-foreground/70">{output.runtime_ms} ms</p>
    </div>
  );
}

async function safeJson(res: Response): Promise<{ detail?: string } | null> {
  try {
    return (await res.json()) as { detail?: string };
  } catch {
    return null;
  }
}
