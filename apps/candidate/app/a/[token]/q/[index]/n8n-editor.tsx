"use client";

import { useEffect, useState } from "react";
import { env } from "@/env";

type Props = {
  token: string;
  questionIndex: number;
  initialWorkflowId: string | null;
};

type EmbedResponse = {
  workflow_id: string;
  embed_url: string;
};

type ExportResponse = {
  workflow_id: string;
  workflow: Record<string, unknown>;
};

export function N8nRenderer({
  token,
  questionIndex,
  initialWorkflowId,
}: Props) {
  const [workflowId, setWorkflowId] = useState<string | null>(initialWorkflowId);
  const [embedUrl, setEmbedUrl] = useState<string | null>(null);
  const [exportedWorkflow, setExportedWorkflow] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"none" | "embed" | "export">("none");

  const apiBase = env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");

  useEffect(() => {
    if (workflowId || busy !== "none") return;
    void provision();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function provision() {
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
        const body = await safeJson(res);
        setError(body?.detail ?? `Provision failed (${res.status})`);
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
  }

  async function exportWorkflow() {
    if (!workflowId) return;
    setBusy("export");
    setError(null);
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
        <span className="text-emerald-300/70">
          {workflowId
            ? `Workflow ${workflowId.slice(0, 10)}…`
            : "Provisioning n8n workspace…"}
        </span>
        <button
          className="rounded border border-emerald-900/60 bg-emerald-950/40 px-2 py-1 hover:bg-emerald-900/40 disabled:opacity-50"
          disabled={!workflowId || busy !== "none"}
          onClick={exportWorkflow}
          type="button"
        >
          {busy === "export" ? "Exporting…" : "Export current state"}
        </button>
        <button
          className="rounded border border-emerald-900/60 bg-emerald-950/40 px-2 py-1 hover:bg-emerald-900/40 disabled:opacity-50"
          disabled={busy !== "none"}
          onClick={provision}
          type="button"
        >
          {busy === "embed" ? "Provisioning…" : "Reset workspace"}
        </button>
      </div>

      {error && (
        <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
          {error}
        </p>
      )}

      {embedUrl ? (
        <iframe
          className="h-[640px] w-full overflow-hidden rounded-lg border border-emerald-900/60 bg-emerald-950/20"
          referrerPolicy="origin"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          src={embedUrl}
          title="n8n workflow editor"
        />
      ) : (
        <div className="flex h-[300px] items-center justify-center rounded-lg border border-emerald-900/60 bg-emerald-950/20 text-emerald-300/70 text-sm">
          {error
            ? "n8n workspace unavailable. The admin can rescore this attempt later."
            : "Loading n8n workspace…"}
        </div>
      )}

      {exportedWorkflow && (
        <details className="rounded-lg border border-emerald-900/60 bg-emerald-950/30 p-3 text-xs">
          <summary className="cursor-pointer text-emerald-200">
            Captured workflow JSON ({Object.keys(exportedWorkflow).length} keys)
          </summary>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-emerald-950/60 p-2 text-emerald-100">
            {JSON.stringify(exportedWorkflow, null, 2)}
          </pre>
        </details>
      )}

      <p className="text-emerald-300/60 text-xs">
        Build the workflow in the iframe. Click <em>Export current state</em>
        before submitting; it captures the workflow JSON the grader sees.
      </p>
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
