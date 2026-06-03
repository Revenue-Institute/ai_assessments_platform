import { ApiError } from "@repo/api-client";

import { env } from "@/env";

const TRAILING_SLASH_RE = /\/$/;
const API_BASE = env.NEXT_PUBLIC_API_URL.replace(TRAILING_SLASH_RE, "");

/** SSE frame shapes emitted by the FastAPI `/a/{token}/code/run?stream=true`
 * endpoint. Source of truth lives in
 * `apps/api/src/ri_assessments_api/services/code_runner.py::run_user_code_streaming`.
 * Kept structural (not branded) so future frame types added on the backend
 * still parse and surface to the caller without a client redeploy. */
export type CodeRunFrame =
  | { type: "started"; language?: string; time_limit_ms?: number }
  | { type: "stdout"; chunk: string }
  | { type: "stderr"; chunk: string }
  | {
      type: "exit";
      exit_code: number;
      runtime_ms: number;
      timed_out: boolean;
      error: string | null;
    }
  | { type: string; [key: string]: unknown };

export interface RunCodeStreamOptions {
  /** AbortSignal so callers can cancel an in-flight stream (e.g. on
   * component unmount). The fetch is wired through this signal directly. */
  signal?: AbortSignal;
}

function extractSseDataPayload(rawFrame: string): string | null {
  const dataLines: string[] = [];
  for (const line of rawFrame.split("\n")) {
    if (line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return dataLines.join("\n");
}

function dispatchSseFrame(
  payload: string,
  onEvent: (frame: CodeRunFrame) => void
): boolean {
  try {
    const parsed = JSON.parse(payload) as CodeRunFrame;
    onEvent(parsed);
    return parsed.type === "exit";
  } catch {
    onEvent({ type: "stderr", chunk: payload });
    return false;
  }
}

function drainSseBuffer(
  buffer: string,
  onEvent: (frame: CodeRunFrame) => void
): { buffer: string; sawExit: boolean } {
  let remaining = buffer;
  let sawExit = false;
  let separatorIndex = remaining.indexOf("\n\n");
  while (separatorIndex !== -1) {
    const rawFrame = remaining.slice(0, separatorIndex);
    remaining = remaining.slice(separatorIndex + 2);
    separatorIndex = remaining.indexOf("\n\n");
    const payload = extractSseDataPayload(rawFrame);
    if (payload === null) {
      continue;
    }
    if (dispatchSseFrame(payload, onEvent)) {
      sawExit = true;
    }
  }
  return { buffer: remaining, sawExit };
}

async function readApiErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    /* fall through to status text */
  }
  return res.statusText;
}

/** POST candidate code to `/a/{token}/code/run?stream=true` and parse the
 * `text/event-stream` body frame-by-frame, invoking `onEvent` for each
 * decoded JSON payload. Resolves once the stream closes (either after an
 * `exit` frame or because the server ended the response) and rejects if
 * the request fails or the response body isn't streamable.
 *
 * Uses NEXT_PUBLIC_API_URL (not INTERNAL_API_URL) because this runs in
 * the browser inside the code-editor client component. */
export async function runCodeStream(
  token: string,
  questionIndex: number,
  code: string,
  onEvent: (frame: CodeRunFrame) => void,
  options?: RunCodeStreamOptions
): Promise<void> {
  const url = `${API_BASE}/a/${encodeURIComponent(token)}/code/run?stream=true`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ code, question_index: questionIndex }),
    signal: options?.signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(await readApiErrorDetail(res), res.status);
  }
  if (!res.body) {
    throw new ApiError("Streaming response had no body.", 500);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const drained = drainSseBuffer(buffer, onEvent);
      buffer = drained.buffer;
      if (drained.sawExit) {
        break;
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* reader may already be released; ignore */
    }
  }
}