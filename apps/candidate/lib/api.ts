import { env } from "@/env";

export type CandidateAssignmentView = {
  assignment_id: string;
  status: "pending" | "in_progress" | "completed" | "expired" | "cancelled";
  expires_at: string;
  started_at: string | null;
  consent_at: string | null;
  subject: {
    full_name: string;
    type: "candidate" | "employee";
  };
  module: {
    title: string;
    description: string;
    target_duration_minutes: number;
    question_count: number;
  };
};

export type ConsentResponse = {
  assignment_id: string;
  status: "in_progress";
  started_at: string;
  server_deadline: string;
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function callApi<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${env.INTERNAL_API_URL.replace(/\/$/, "")}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      }
    } catch {
      /* fall through to statusText */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

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
