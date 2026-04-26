"use client";

import Editor from "@monaco-editor/react";
import { useState } from "react";
import { env } from "@/env";

type CodeConfig = {
  language?: string;
  starter_code?: string;
  visible_tests?: string;
  packages?: string[];
};

type RunResult = {
  stdout: string;
  stderr: string;
  exit_code: number;
  runtime_ms: number;
  timed_out: boolean;
};

type TestResult = {
  passed: number;
  failed: number;
  errors: number;
  total: number;
  output: string;
  runtime_ms: number;
  timed_out: boolean;
};

const SUPPORTED_MONACO_LANGS = new Set([
  "python",
  "javascript",
  "typescript",
  "sql",
  "shell",
]);

const monacoLanguage = (lang: string | undefined): string => {
  if (!lang) return "python";
  if (lang === "bash") return "shell";
  if (SUPPORTED_MONACO_LANGS.has(lang)) return lang;
  return "plaintext";
};

export function CodeRenderer({
  token,
  questionIndex,
  config,
  initialCode,
  hasVisibleTests,
}: {
  token: string;
  questionIndex: number;
  config: CodeConfig;
  initialCode: string;
  hasVisibleTests: boolean;
}) {
  const [code, setCode] = useState(initialCode);
  const [running, setRunning] = useState<"none" | "run" | "test">("none");
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apiBase = env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");

  async function runCode() {
    setRunning("run");
    setError(null);
    setTestResult(null);
    try {
      const res = await fetch(`${apiBase}/a/${encodeURIComponent(token)}/code/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, question_index: questionIndex }),
      });
      if (!res.ok) {
        const body = await safeJson(res);
        setError(body?.detail ?? `Run failed (${res.status})`);
        return;
      }
      setRunResult((await res.json()) as RunResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error.");
    } finally {
      setRunning("none");
    }
  }

  async function runTests() {
    setRunning("test");
    setError(null);
    setRunResult(null);
    try {
      const res = await fetch(`${apiBase}/a/${encodeURIComponent(token)}/code/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, question_index: questionIndex }),
      });
      if (!res.ok) {
        const body = await safeJson(res);
        setError(body?.detail ?? `Test run failed (${res.status})`);
        return;
      }
      setTestResult((await res.json()) as TestResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error.");
    } finally {
      setRunning("none");
    }
  }

  return (
    <div className="space-y-3">
      <input
        name="answer"
        type="hidden"
        value={JSON.stringify({ code })}
      />

      {/* Monaco lives inside the allow-paste zone so the integrity monitor
          tolerates copy/paste/keyboard shortcuts there. */}
      <div
        className="overflow-hidden rounded-lg border border-border"
        data-allow-paste="true"
      >
        <Editor
          defaultLanguage={monacoLanguage(config.language)}
          height="320px"
          onChange={(value) => setCode(value ?? "")}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            scrollBeyondLastLine: false,
            tabSize: 4,
          }}
          theme="vs-dark"
          value={code}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          className="rounded border border-border bg-card px-3 py-2 text-sm hover:bg-primary/10 disabled:opacity-50"
          disabled={running !== "none"}
          onClick={runCode}
          type="button"
        >
          {running === "run" ? "Running…" : "Run"}
        </button>
        {hasVisibleTests && (
          <button
            className="rounded border border-border bg-card px-3 py-2 text-sm hover:bg-primary/10 disabled:opacity-50"
            disabled={running !== "none"}
            onClick={runTests}
            type="button"
          >
            {running === "test" ? "Running tests…" : "Run visible tests"}
          </button>
        )}
      </div>

      {error && (
        <p className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm">
          {error}
        </p>
      )}

      {runResult && (
        <ResultPane
          title={`Run output (${runResult.runtime_ms} ms${
            runResult.timed_out ? " · timed out" : ""
          })`}
          stdout={runResult.stdout}
          stderr={runResult.stderr}
          exitCode={runResult.exit_code}
        />
      )}

      {testResult && (
        <TestResultPane result={testResult} />
      )}
    </div>
  );
}

function ResultPane({
  title,
  stdout,
  stderr,
  exitCode,
}: {
  title: string;
  stdout: string;
  stderr: string;
  exitCode: number;
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-3 text-xs">
      <header className="mb-2 flex items-center justify-between">
        <p className="font-medium text-primary">{title}</p>
        <p className="text-muted-foreground">exit {exitCode}</p>
      </header>
      {stdout && (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-secondary p-2 text-foreground">
          {stdout}
        </pre>
      )}
      {stderr && (
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-destructive/15 p-2 text-destructive">
          {stderr}
        </pre>
      )}
      {!stdout && !stderr && (
        <p className="text-muted-foreground">No output.</p>
      )}
    </section>
  );
}

function TestResultPane({ result }: { result: TestResult }) {
  const passed = result.passed === result.total && result.total > 0;
  return (
    <section className="rounded-lg border border-border bg-card p-3 text-xs">
      <header className="mb-2 flex items-center justify-between">
        <p className="font-medium text-primary">Visible tests</p>
        <p
          className={
            passed
              ? "font-medium text-primary"
              : "font-medium text-amber-300"
          }
        >
          {result.passed}/{result.total} passed ({result.runtime_ms} ms)
        </p>
      </header>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-secondary p-2 text-foreground">
        {result.output || "(no output)"}
      </pre>
    </section>
  );
}

async function safeJson(res: Response): Promise<{ detail?: string } | null> {
  try {
    return (await res.json()) as { detail?: string };
  } catch {
    return null;
  }
}
