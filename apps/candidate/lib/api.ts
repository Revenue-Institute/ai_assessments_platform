import { ApiError, createCallApi } from "@repo/api-client";
import { env } from "@/env";

export { ApiError } from "@repo/api-client";

const TRAILING_SLASH_RE = /\/$/;

export interface CandidateAssignmentView {
  assignment_id: string;
  consent_at: string | null;
  expires_at: string;
  module: {
    title: string;
    description: string;
    target_duration_minutes: number;
    question_count: number;
  };
  started_at: string | null;
  status: "pending" | "in_progress" | "completed" | "expired" | "cancelled";
  subject: {
    full_name: string;
    type: "candidate" | "employee";
  };
}

export interface ConsentResponse {
  assignment_id: string;
  server_deadline: string;
  started_at: string;
  status: "in_progress";
}

export interface CandidateQuestionView {
  assignment_id: string;
  competency_tags: string[];
  expires_at: string;
  index: number;
  interactive_config: Record<string, unknown> | null;
  max_points: number;
  question_template_id: string;
  raw_answer: { value: unknown } | null;
  rendered_prompt: string;
  submitted_at: string | null;
  time_limit_seconds: number | null;
  total: number;
  type: string;
}

export interface SubmitAnswerResponse {
  next_index: number | null;
  ok: true;
  total: number;
}

export interface CompleteResponse {
  assignment_id: string;
  completed_at: string;
  status: "completed";
}

const callApi = createCallApi({ baseUrl: env.INTERNAL_API_URL });

export function fetchAssignment(token: string) {
  return callApi<CandidateAssignmentView>(
    `/a/${encodeURIComponent(token)}/resolve`
  );
}

export function postConsent(token: string, forwardedIp?: string) {
  return callApi<ConsentResponse>(`/a/${encodeURIComponent(token)}/consent`, {
    method: "POST",
    body: JSON.stringify({}),
    headers: forwardedIp ? { "x-forwarded-for": forwardedIp } : undefined,
  });
}

export function fetchQuestion(token: string, index: number) {
  return callApi<CandidateQuestionView>(
    `/a/${encodeURIComponent(token)}/questions/${index}`
  );
}

export function submitQuestion(token: string, index: number, answer: unknown) {
  return callApi<SubmitAnswerResponse>(
    `/a/${encodeURIComponent(token)}/questions/${index}/submit`,
    {
      method: "POST",
      body: JSON.stringify({ answer }),
    }
  );
}

export function completeAssignment(token: string) {
  return callApi<CompleteResponse>(`/a/${encodeURIComponent(token)}/complete`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

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

/** Pull `data:` lines out of one raw SSE frame, ignoring `:` keepalive
 * comments. Returns the joined payload or `null` when the frame has no
 * data lines (e.g. a lone keepalive). */
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

/** Parse one SSE data payload and forward it to `onEvent`. Returns
 * `true` if the payload was a terminal `exit` frame. Malformed JSON is
 * surfaced as a synthetic stderr chunk so the candidate sees something
 * rather than a silent stall. */
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

/** Drain every complete `\n\n`-delimited frame from `buffer`, dispatching
 * each via `dispatchSseFrame`. Returns the leftover buffer (incomplete
 * trailing frame) and whether any frame signalled `exit`. */
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

/** Best-effort extraction of an API error detail message from a non-OK
 * response. Falls back to the HTTP status text. */
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
 * `EventSource` doesn't support POST, so we use a streaming `fetch` plus
 * a manual SSE parser. The parser only handles `data:` lines and the
 * `\n\n` frame separator that the backend emits; non-JSON `:` comments
 * (used for keepalives) are silently skipped. */
export async function runCodeStream(
  token: string,
  questionIndex: number,
  code: string,
  onEvent: (frame: CodeRunFrame) => void,
  options?: RunCodeStreamOptions
): Promise<void> {
  // Streaming fetch runs in the browser (code editor is a client
  // component), so use the public API URL. INTERNAL_API_URL is only
  // reachable from server components / server actions.
  const base = env.NEXT_PUBLIC_API_URL.replace(TRAILING_SLASH_RE, "");
  const url = `${base}/a/${encodeURIComponent(token)}/code/run?stream=true`;
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
