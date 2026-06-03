import { ApiError, createCallApi } from "@repo/api-client";

import { env } from "@/env";

export { ApiError } from "@repo/api-client";

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

export type { CodeRunFrame, RunCodeStreamOptions } from "./code-stream-api";
export { runCodeStream } from "./code-stream-api";
