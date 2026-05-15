"use client";

import Editor, { type OnMount } from "@monaco-editor/react";
import { emitIntegrityEvent } from "@repo/integrity/browser";
import type { MutableRefObject } from "react";
import { useEffect, useRef, useState } from "react";
import { env } from "@/env";
import { type CodeRunFrame, runCodeStream } from "@/lib/api";
import { useUnsavedChangesWarning } from "@/lib/use-unsaved-changes";

interface CodeConfig {
  language?: string;
  packages?: string[];
  starter_code?: string;
  visible_tests?: string;
}

interface RunResult {
  exit_code: number;
  runtime_ms: number;
  stderr: string;
  stdout: string;
  timed_out: boolean;
}

interface TestResult {
  errors: number;
  failed: number;
  output: string;
  passed: number;
  runtime_ms: number;
  timed_out: boolean;
  total: number;
}

const SUPPORTED_MONACO_LANGS = new Set([
  "python",
  "javascript",
  "typescript",
  "sql",
  "shell",
]);
const TRAILING_SLASH_RE = /\/$/;

const monacoLanguage = (lang: string | undefined): string => {
  if (!lang) {
    return "python";
  }
  if (lang === "bash") {
    return "shell";
  }
  if (SUPPORTED_MONACO_LANGS.has(lang)) {
    return lang;
  }
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
  const [streamingStdout, setStreamingStdout] = useState<string>("");
  const [streamingStderr, setStreamingStderr] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const outputPaneRef = useRef<HTMLElement | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

  useUnsavedChangesWarning(code !== initialCode);

  const apiBase = env.NEXT_PUBLIC_API_URL.replace(TRAILING_SLASH_RE, "");

  // Auto-scroll the output pane to the bottom as new chunks arrive so the
  // candidate watches output flow without manually scrolling. We scroll on
  // every stream tick (cheap, and only the visible pane is touched). The
  // effect body only reads the DOM ref, but it must re-fire whenever
  // stdout/stderr grow, so the buffer lengths are pinned into the dep array
  // explicitly and Biome's exhaustive-deps heuristic is overridden below.
  const stdoutTickLen = streamingStdout.length;
  const stderrTickLen = streamingStderr.length;
  // biome-ignore lint/correctness/useExhaustiveDependencies: stdout/stderr tick lengths drive the re-fire on every stream chunk; the effect body only reads the DOM ref.
  useEffect(() => {
    if (!(isStreaming || runResult)) {
      return;
    }
    const el = outputPaneRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [stdoutTickLen, stderrTickLen, isStreaming, runResult]);

  // Abort any in-flight stream on unmount so we don't leak fetches when
  // the candidate navigates away mid-run.
  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
    };
  }, []);

  const onMount: OnMount = (editor) => {
    // Monaco's default aria-label is generic. Override so screen readers
    // announce the editor's purpose on focus (spec §18 WCAG 2.1 AA).
    editor.updateOptions({ ariaLabel: "Code answer editor" });
  };

  async function runCodeBuffered(): Promise<void> {
    // Legacy buffered fallback. Used when the streaming endpoint fails
    // (older API, proxy strips SSE, network blip mid-stream). Keeps the
    // candidate experience resilient to backend regressions.
    const res = await fetch(
      `${apiBase}/a/${encodeURIComponent(token)}/code/run`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, question_index: questionIndex }),
      }
    );
    if (!res.ok) {
      const body = await safeJson(res);
      setError(body?.detail ?? `Run failed (${res.status})`);
      return;
    }
    setRunResult((await res.json()) as RunResult);
  }

  async function runCode() {
    setRunning("run");
    setError(null);
    setTestResult(null);
    setRunResult(null);
    setStreamingStdout("");
    setStreamingStderr("");
    setIsStreaming(true);
    emitIntegrityEvent("code_executed", { question_index: questionIndex });

    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;

    let stdoutBuf = "";
    let stderrBuf = "";
    // Pre-build the final RunResult inside the frame handler. Using a
    // mutable object (rather than capturing the exit frame and reading
    // its fields later) sidesteps a TS narrowing quirk where values
    // assigned inside a closure stay typed as `never` at the call site.
    let finalResult: RunResult | null = null;
    let receivedAnyFrame = false;

    try {
      await runCodeStream(
        token,
        questionIndex,
        code,
        (frame) => {
          receivedAnyFrame = true;
          if (frame.type === "stdout" && typeof frame.chunk === "string") {
            stdoutBuf += frame.chunk;
            setStreamingStdout(stdoutBuf);
          } else if (
            frame.type === "stderr" &&
            typeof frame.chunk === "string"
          ) {
            stderrBuf += frame.chunk;
            setStreamingStderr(stderrBuf);
          } else if (frame.type === "exit") {
            const exit = frame as Extract<CodeRunFrame, { type: "exit" }>;
            finalResult = {
              stdout: stdoutBuf,
              stderr: stderrBuf,
              exit_code: exit.exit_code,
              runtime_ms: exit.runtime_ms,
              timed_out: exit.timed_out,
            };
          }
        },
        { signal: controller.signal }
      );

      if (finalResult) {
        setRunResult(finalResult);
      } else if (receivedAnyFrame) {
        // Stream ended mid-flight without an exit frame. Surface what we
        // have but flag that the run was truncated.
        setRunResult({
          stdout: stdoutBuf,
          stderr: stderrBuf,
          exit_code: -1,
          runtime_ms: 0,
          timed_out: false,
        });
        setError("Run stream ended before completion.");
      } else {
        // Stream closed without delivering anything. Fall back to the
        // buffered endpoint so the candidate still gets a result.
        await runCodeBuffered();
      }
    } catch (streamErr) {
      if (controller.signal.aborted) {
        return;
      }
      // Streaming failed (network/proxy/cors). Retry once via the buffered
      // endpoint so the candidate doesn't lose their run.
      try {
        await runCodeBuffered();
      } catch (bufferedErr) {
        let message = "Network error.";
        if (bufferedErr instanceof Error) {
          message = bufferedErr.message;
        } else if (streamErr instanceof Error) {
          message = streamErr.message;
        }
        setError(message);
      }
    } finally {
      setIsStreaming(false);
      setRunning("none");
      streamAbortRef.current = null;
    }
  }

  async function runTests() {
    setRunning("test");
    setError(null);
    setRunResult(null);
    emitIntegrityEvent("test_run", { question_index: questionIndex });
    try {
      const res = await fetch(
        `${apiBase}/a/${encodeURIComponent(token)}/code/test`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, question_index: questionIndex }),
        }
      );
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
      <input name="answer" type="hidden" value={JSON.stringify({ code })} />

      {/* Monaco lives inside the allow-paste zone so the integrity monitor
          tolerates copy/paste/keyboard shortcuts there. The wrapping group
          gives assistive tech a stable name for the editor region. */}
      <fieldset
        aria-label="Code answer editor"
        className="overflow-hidden rounded-lg border border-border p-0"
        data-allow-paste="true"
      >
        <Editor
          defaultLanguage={monacoLanguage(config.language)}
          height="320px"
          onChange={(value) => setCode(value ?? "")}
          onMount={onMount}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            scrollBeyondLastLine: false,
            tabSize: 4,
            ariaLabel: "Code answer editor",
          }}
          theme="vs-dark"
          value={code}
        />
      </fieldset>

      <div className="flex flex-wrap gap-2">
        <button
          className="rounded border border-border bg-card px-3 py-2 text-sm hover:bg-primary/10 disabled:opacity-50"
          disabled={running !== "none" || isStreaming}
          onClick={runCode}
          type="button"
        >
          {running === "run" || isStreaming ? "Running..." : "Run"}
        </button>
        {hasVisibleTests && (
          <button
            className="rounded border border-border bg-card px-3 py-2 text-sm hover:bg-primary/10 disabled:opacity-50"
            disabled={running !== "none" || isStreaming}
            onClick={runTests}
            type="button"
          >
            {running === "test" ? "Running tests..." : "Run visible tests"}
          </button>
        )}
      </div>

      {error && (
        <p className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm">
          {error}
        </p>
      )}

      {(isStreaming || runResult) && (
        <StreamingResultPane
          done={!!runResult}
          exitCode={runResult?.exit_code ?? null}
          paneRef={outputPaneRef}
          runtimeMs={runResult?.runtime_ms ?? null}
          stderr={runResult ? runResult.stderr : streamingStderr}
          stdout={runResult ? runResult.stdout : streamingStdout}
          timedOut={runResult?.timed_out ?? false}
        />
      )}

      {testResult && <TestResultPane result={testResult} />}
    </div>
  );
}

function StreamingResultPane({
  stdout,
  stderr,
  exitCode,
  runtimeMs,
  timedOut,
  done,
  paneRef,
}: {
  stdout: string;
  stderr: string;
  exitCode: number | null;
  runtimeMs: number | null;
  timedOut: boolean;
  done: boolean;
  paneRef: MutableRefObject<HTMLElement | null>;
}) {
  // Single output pane that shows stdout and stderr as they stream from
  // the sandbox. Stderr is rendered in the destructive color tokens so
  // exceptions and trace output read at a glance. After the exit frame
  // arrives we render a final summary row with the exit code + runtime.
  return (
    <section
      aria-live="polite"
      className="rounded-lg border border-border bg-card p-3 text-xs"
      ref={(el) => {
        paneRef.current = el;
      }}
    >
      <header className="mb-2 flex items-center justify-between">
        <p className="font-medium text-primary">Run output</p>
        {done ? (
          <p className="text-muted-foreground">
            exit {exitCode}
            {runtimeMs !== null ? ` · ${runtimeMs} ms` : ""}
            {timedOut ? " · timed out" : ""}
          </p>
        ) : (
          <p className="flex items-center gap-1 font-medium text-primary/80">
            <span className="sr-only">Streaming output from sandbox</span>
            <span
              aria-hidden="true"
              className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary"
            />
            Streaming...
          </p>
        )}
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
      {!(stdout || stderr) && (
        <p className="text-muted-foreground">
          {done ? "No output." : "Waiting for output..."}
        </p>
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
            passed ? "font-medium text-primary" : "font-medium text-warning"
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
