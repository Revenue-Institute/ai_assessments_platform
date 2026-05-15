"use client";

import { emitIntegrityEvent } from "@repo/integrity/browser";
import { useCallback, useEffect, useState } from "react";
import { env } from "@/env";

interface Props {
  initialWorkflowId: string | null;
  questionIndex: number;
  token: string;
}

interface EmbedResponse {
  embed_url: string;
  workflow_id: string;
}

interface ExportResponse {
  workflow: Record<string, unknown>;
  workflow_id: string;
}

const TRAILING_SLASH_RE = /\/$/;

export function N8nRenderer({
  token,
  questionIndex,
  initialWorkflowId,
}: Props) {
  const [workflowId, setWorkflowId] = useState<string | null>(
    initialWorkflowId
  );
  const [embedUrl, setEmbedUrl] = useState<string | null>(null);
  const [exportedWorkflow, setExportedWorkflow] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"none" | "embed" | "export">("none");

  const apiBase = env.NEXT_PUBLIC_API_URL.replace(TRAILING_SLASH_RE, "");

  const provision = useCallback(async () => {
    setBusy("embed");
    setError(null);
    try {
      const res = await fetch(
        `${apiBase}/a/${encodeURIComponent(token)}/n8n/embed`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question_index: questionIndex }),
        }
      );
      if (!res.ok) {
        // Backend logs the raw httpx / n8n error; the candidate just sees a
        // calm fallback. 502/503 mean the n8n service or its provisioning
        // endpoint is unreachable, which is operational, not the
        // candidate's problem.
        if (res.status === 502 || res.status === 503) {
          setError(
            "n8n workspace is currently unavailable. Your progress is saved; an admin can rescore this attempt once the workspace is back up."
          );
        } else {
          const body = await safeJson(res);
          setError(body?.detail ?? `Provision failed (${res.status})`);
        }
        return;
      }
      const data = (await res.json()) as EmbedResponse;
      setWorkflowId(data.workflow_id);
      setEmbedUrl(data.embed_url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error.");
    } finally {
      setBusy("none");
    }
  }, [apiBase, questionIndex, token]);

  useEffect(() => {
    if (workflowId || busy !== "none") {
      return;
    }
    provision();
  }, [busy, provision, workflowId]);

  async function exportWorkflow() {
    if (!workflowId) {
      return;
    }
    setBusy("export");
    setError(null);
    emitIntegrityEvent("n8n_workflow_saved", {
      question_index: questionIndex,
      workflow_id: workflowId,
    });
    try {
      const res = await fetch(
        `${apiBase}/a/${encodeURIComponent(token)}/n8n/export`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question_index: questionIndex,
            workflow_id: workflowId,
          }),
        }
      );
      if (!res.ok) {
        const body = await safeJson(res);
        setError(body?.detail ?? `Export failed (${res.status})`);
        return;
      }
      const data = (await res.json()) as ExportResponse;
      setExportedWorkflow(data.workflow);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error.");
    } finally {
      setBusy("none");
    }
  }

  return (
    <div className="space-y-3">
      <input
        name="answer"
        type="hidden"
        value={JSON.stringify({
          workflow_id: workflowId,
          workflow: exportedWorkflow,
        })}
      />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground">
          {workflowId
            ? `Workflow ${workflowId.slice(0, 10)}…`
            : "Provisioning n8n workspace…"}
        </span>
        <button
          aria-describedby="n8n-export-help"
          className={
            exportedWorkflow
              ? "rounded border border-primary/40 bg-primary/10 px-2 py-1 text-primary hover:bg-primary/20 disabled:opacity-50"
              : "btn-primary text-xs disabled:opacity-50"
          }
          disabled={!workflowId || busy !== "none"}
          onClick={exportWorkflow}
          type="button"
        >
          {exportButtonLabel(busy, exportedWorkflow)}
        </button>
        <button
          className="rounded border border-border bg-card px-2 py-1 hover:bg-primary/10 disabled:opacity-50"
          disabled={busy !== "none"}
          onClick={provision}
          type="button"
        >
          {busy === "embed" ? "Provisioning…" : "Reset workspace"}
        </button>
      </div>

      {!exportedWorkflow && workflowId && busy !== "embed" && (
        <output
          aria-live="polite"
          className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-warning text-xs"
        >
          You haven&apos;t saved this workflow yet. Click{" "}
          <strong>Save workflow to answer</strong> after each set of edits, and
          again right before you submit. Without a save, the grader won&apos;t
          see your latest changes.
        </output>
      )}

      {exportedWorkflow && (
        <output
          aria-live="polite"
          className="rounded border border-primary/40 bg-primary/10 px-3 py-2 text-primary text-xs"
        >
          Workflow saved. Re-save if you keep editing.
        </output>
      )}

      {error && (
        <p className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm">
          {error}
        </p>
      )}

      {embedUrl ? (
        // The cross-origin iframe blocks the parent's clipboard listeners
        // from reaching its contents, but marking the wrapper with
        // data-allow-paste keeps the integrity contract uniform with the
        // other interactive editors.
        <div data-allow-paste="true">
          <iframe
            className="h-[640px] w-full overflow-hidden rounded-lg border border-border bg-card/60"
            referrerPolicy="origin"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            src={embedUrl}
            title="n8n workflow editor"
          />
        </div>
      ) : (
        <output
          aria-busy={!error}
          className="flex h-[300px] flex-col items-center justify-center gap-2 rounded-lg border border-border bg-card/60 text-muted-foreground text-sm"
        >
          {error ? (
            "n8n workspace unavailable. The admin can rescore this attempt later."
          ) : (
            <>
              <span
                aria-hidden="true"
                className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent"
              />
              <span>Setting up your workspace (10-15 seconds)...</span>
            </>
          )}
        </output>
      )}

      {exportedWorkflow && (
        <details className="rounded-lg border border-border bg-card p-3 text-xs">
          <summary className="cursor-pointer text-primary">
            Captured workflow JSON ({Object.keys(exportedWorkflow).length} keys)
          </summary>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-secondary p-2 text-foreground">
            {JSON.stringify(exportedWorkflow, null, 2)}
          </pre>
        </details>
      )}

      <p className="text-muted-foreground text-xs" id="n8n-export-help">
        Build the workflow in the iframe above, then click{" "}
        <em>Save workflow to answer</em> whenever you reach a checkpoint. The
        grader scores the most recent saved version, so re-save right before you
        submit.
      </p>
    </div>
  );
}

function exportButtonLabel(
  busy: "none" | "embed" | "export",
  exportedWorkflow: Record<string, unknown> | null
) {
  if (busy === "export") {
    return "Saving workflow…";
  }
  if (exportedWorkflow) {
    return "Re-save workflow";
  }
  return "Save workflow to answer";
}

async function safeJson(res: Response): Promise<{ detail?: string } | null> {
  try {
    return (await res.json()) as { detail?: string };
  } catch {
    return null;
  }
}
