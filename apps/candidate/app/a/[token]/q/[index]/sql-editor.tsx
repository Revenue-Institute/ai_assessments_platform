"use client";

import Editor from "@monaco-editor/react";
import { useState } from "react";
import { env } from "@/env";
import { useUnsavedChangesWarning } from "@/lib/use-unsaved-changes";

type SqlConfig = {
  schema_sql?: string;
  seed_sql?: string;
};

type SqlRunResult = {
  columns: string[];
  rows: unknown[][];
  runtime_ms: number;
  error: string | null;
  timed_out: boolean;
};

export function SqlRenderer({
  token,
  questionIndex,
  config,
  initialSql,
}: {
  token: string;
  questionIndex: number;
  config: SqlConfig;
  initialSql: string;
}) {
  const [sql, setSql] = useState(initialSql);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SqlRunResult | null>(null);
  const [networkError, setNetworkError] = useState<string | null>(null);

  useUnsavedChangesWarning(sql !== initialSql);

  const apiBase = env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");

  async function runQuery() {
    setRunning(true);
    setNetworkError(null);
    try {
      const res = await fetch(
        `${apiBase}/a/${encodeURIComponent(token)}/sql/query`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sql, question_index: questionIndex }),
        }
      );
      if (!res.ok) {
        const body = await safeJson(res);
        setNetworkError(body?.detail ?? `Run failed (${res.status})`);
        return;
      }
      setResult((await res.json()) as SqlRunResult);
    } catch (e) {
      setNetworkError(e instanceof Error ? e.message : "Network error.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <input name="answer" type="hidden" value={JSON.stringify({ sql })} />

      {(config.schema_sql || config.seed_sql) && (
        <details className="rounded-lg border border-border bg-card p-3 text-xs">
          <summary className="cursor-pointer text-primary">
            Schema and seed
          </summary>
          {config.schema_sql && (
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-secondary p-2 text-foreground">
              {config.schema_sql}
            </pre>
          )}
          {config.seed_sql && (
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-secondary p-2 text-foreground">
              {config.seed_sql}
            </pre>
          )}
        </details>
      )}

      <div
        className="overflow-hidden rounded-lg border border-border"
        data-allow-paste="true"
      >
        <Editor
          defaultLanguage="sql"
          height="240px"
          onChange={(value) => setSql(value ?? "")}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            scrollBeyondLastLine: false,
            wordWrap: "on",
          }}
          theme="vs-dark"
          value={sql}
        />
      </div>

      <button
        className="rounded border border-border bg-card px-3 py-2 text-sm hover:bg-primary/10 disabled:opacity-50"
        disabled={running}
        onClick={runQuery}
        type="button"
      >
        {running ? "Running…" : "Run query"}
      </button>

      {networkError && (
        <p className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm">
          {networkError}
        </p>
      )}

      {result && (
        <ResultPane result={result} />
      )}
    </div>
  );
}

function ResultPane({ result }: { result: SqlRunResult }) {
  if (result.error) {
    return (
      <section className="rounded border border-destructive/50 bg-destructive/15 p-3 text-xs">
        <p className="font-medium text-destructive">Query error</p>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-destructive/15 p-2 text-destructive">
          {result.error}
        </pre>
        <p className="mt-2 text-destructive/80">
          {result.timed_out ? "Timed out" : `${result.runtime_ms} ms`}
        </p>
      </section>
    );
  }
  return (
    <section className="rounded-lg border border-border bg-card p-3 text-xs">
      <header className="mb-2 flex items-center justify-between">
        <p className="font-medium text-primary">
          {result.rows.length} row{result.rows.length === 1 ? "" : "s"}
        </p>
        <p className="text-muted-foreground">{result.runtime_ms} ms</p>
      </header>
      <div className="max-h-72 overflow-auto rounded border border-border">
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 bg-secondary text-foreground">
            <tr>
              {result.columns.map((c) => (
                <th
                  className="border-border border-b px-2 py-1 font-medium"
                  key={c}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, i) => (
              <tr className="odd:bg-secondary/30" key={i}>
                {row.map((cell, j) => (
                  <td
                    className="border-border/60 border-b px-2 py-1"
                    key={j}
                  >
                    {formatCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {result.rows.length === 0 && (
          <p className="px-2 py-3 text-muted-foreground">No rows.</p>
        )}
      </div>
    </section>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

async function safeJson(res: Response): Promise<{ detail?: string } | null> {
  try {
    return (await res.json()) as { detail?: string };
  } catch {
    return null;
  }
}
