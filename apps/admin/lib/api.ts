import { env } from "@/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type ModuleStatus = "draft" | "published" | "archived";
export type Difficulty = "junior" | "mid" | "senior" | "expert";
export type SubjectType = "candidate" | "employee";
export type AssignmentStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "expired"
  | "cancelled";

export type ModuleSummary = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  domain: string;
  target_duration_minutes: number;
  difficulty: Difficulty;
  status: ModuleStatus;
  version: number;
  question_count: number;
  created_at: string;
  published_at: string | null;
};

export type ModuleDetail = ModuleSummary & {
  questions: Array<{
    id: string;
    position: number;
    type: string;
    prompt_template: string;
    competency_tags: string[];
    max_points: number;
    time_limit_seconds: number | null;
  }>;
};

export type SubjectSummary = {
  id: string;
  type: SubjectType;
  full_name: string;
  email: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AssignmentSummary = {
  id: string;
  subject_id: string;
  subject_full_name: string | null;
  subject_email: string | null;
  module_id: string | null;
  module_title: string | null;
  status: AssignmentStatus;
  expires_at: string;
  started_at: string | null;
  completed_at: string | null;
  integrity_score: number | null;
  final_score: number | null;
  max_possible_score: number | null;
  created_at: string;
};

export type AttemptSummary = {
  id: string;
  question_template_id: string;
  rendered_prompt: string;
  raw_answer: { value: unknown } | null;
  submitted_at: string | null;
  score: number | null;
  max_score: number;
  score_rationale: string | null;
  scorer_model?: string | null;
  scorer_confidence?: number | null;
  needs_review?: boolean;
  active_time_seconds: number | null;
};

export type AssignmentDetail = AssignmentSummary & {
  consent_at: string | null;
  total_time_seconds: number | null;
  attempts: AttemptSummary[];
};

export type AssignmentMagicLink = {
  assignment_id: string;
  subject_id: string;
  module_id: string;
  expires_at: string;
  magic_link_url: string;
  token: string;
};

export type AdminMe = {
  user_id: string;
  email: string;
  full_name: string | null;
  role: "admin" | "reviewer" | "viewer";
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const supabase = await createSupabaseServerClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    throw new ApiError("Not signed in.", 401);
  }
  return { Authorization: `Bearer ${session.access_token}` };
}

async function callApi<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${env.INTERNAL_API_URL.replace(/\/$/, "")}${path}`;
  const auth = await authHeader();
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...auth,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* fall through */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// Modules
export const listModules = () => callApi<ModuleSummary[]>("/api/modules");
export const getModule = (id: string) =>
  callApi<ModuleDetail>(`/api/modules/${id}`);
export const createModule = (body: {
  slug: string;
  title: string;
  description?: string | null;
  domain: string;
  target_duration_minutes: number;
  difficulty: Difficulty;
}) =>
  callApi<ModuleSummary>("/api/modules", {
    method: "POST",
    body: JSON.stringify(body),
  });
export const publishModule = (id: string) =>
  callApi<ModuleSummary>(`/api/modules/${id}/publish`, {
    method: "POST",
    body: JSON.stringify({}),
  });
export const archiveModule = (id: string) =>
  callApi<ModuleSummary>(`/api/modules/${id}/archive`, {
    method: "POST",
    body: JSON.stringify({}),
  });

// Subjects
export const listSubjects = () => callApi<SubjectSummary[]>("/api/subjects");
export const createSubject = (body: {
  type: SubjectType;
  full_name: string;
  email: string;
}) =>
  callApi<SubjectSummary>("/api/subjects", {
    method: "POST",
    body: JSON.stringify(body),
  });

// Assignments
export const listAssignments = () =>
  callApi<AssignmentSummary[]>("/api/assignments");
export const getAssignment = (id: string) =>
  callApi<AssignmentDetail>(`/api/assignments/${id}`);
export const createAssignment = (body: {
  module_id: string;
  subject_id: string;
  expires_in_days: number;
}) =>
  callApi<AssignmentMagicLink>("/api/assignments", {
    method: "POST",
    body: JSON.stringify(body),
  });
export const cancelAssignment = (id: string) =>
  callApi<AssignmentDetail>(`/api/assignments/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
export const rescoreAssignment = (id: string) =>
  callApi<AssignmentDetail>(`/api/assignments/${id}/rescore`, {
    method: "POST",
    body: JSON.stringify({}),
  });
export const rescoreAttempt = (attemptId: string) =>
  callApi<AssignmentDetail>(`/api/attempts/${attemptId}/rescore`, {
    method: "POST",
    body: JSON.stringify({}),
  });

export const fetchAdminMe = () => callApi<AdminMe>("/api/me");

// Generator
export type GenerationBriefIn = {
  role_title: string;
  responsibilities: string;
  target_duration_minutes: number;
  difficulty: Difficulty;
  domains: string[];
  question_mix: {
    mcq_pct: number;
    short_pct: number;
    long_pct: number;
    code_pct: number;
    interactive_pct: number;
  };
  reference_document_ids: string[];
  required_competencies: string[];
  notes?: string;
};

export type OutlineTopic = {
  name: string;
  competency_tags: string[];
  weight_pct: number;
  question_count: number;
  recommended_types: string[];
  rationale: string;
};

export type GeneratedOutline = {
  title: string;
  description: string;
  topics: OutlineTopic[];
  total_points: number;
  estimated_duration_minutes: number;
};

export type OutlineRunResponse = {
  run_id: string;
  outline: GeneratedOutline;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
};

export type GenerationRunRow = {
  id: string;
  stage: "outline" | "full" | "single_question" | "revision";
  status: "pending" | "success" | "failed";
  model: string;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  error: string | null;
  parent_run_id: string | null;
  input_brief: GenerationBriefIn | Record<string, unknown>;
  output: Record<string, unknown>;
  outline?: GeneratedOutline;
  created_at: string;
};

export type QuestionGenerationResponse = {
  module_id: string;
  module_run_ids: string[];
  questions_generated: number;
  model: string;
  total_tokens_in: number;
  total_tokens_out: number;
};

export const generateOutline = (body: GenerationBriefIn) =>
  callApi<OutlineRunResponse>("/api/generator/outline", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const fetchGenerationRun = (runId: string) =>
  callApi<GenerationRunRow>(
    `/api/generator/runs/${encodeURIComponent(runId)}`
  );

export const generateQuestions = (body: {
  outline_run_id: string;
  brief: GenerationBriefIn;
  outline: GeneratedOutline;
  slug: string;
  domain: string;
}) =>
  callApi<QuestionGenerationResponse>("/api/generator/questions", {
    method: "POST",
    body: JSON.stringify(body),
  });

// References
export type ReferenceDocumentSummary = {
  id: string;
  title: string;
  source_url: string | null;
  domain: string | null;
  chunk_count: number;
  created_at: string;
};

export type ReferenceUploadResponse = {
  document: ReferenceDocumentSummary;
  chunks_inserted: number;
};

export const listReferences = () =>
  callApi<ReferenceDocumentSummary[]>("/api/references");

export const uploadReferenceText = (body: {
  title: string;
  content: string;
  domain?: string | null;
  source_url?: string | null;
}) =>
  callApi<ReferenceUploadResponse>("/api/references", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const uploadReferenceUrl = (body: {
  url: string;
  title?: string | null;
  domain?: string | null;
}) =>
  callApi<ReferenceUploadResponse>("/api/references/url", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteReference = (id: string) =>
  callApi<void>(`/api/references/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

// Question revision
export type ReviseQuestionResponse = {
  question_id: string;
  run_id: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  revised: Record<string, unknown>;
};

export const reviseQuestion = (
  questionId: string,
  body: {
    instruction: string;
    preserve?: Array<
      | "type"
      | "competency_tags"
      | "max_points"
      | "difficulty"
      | "time_limit_seconds"
      | "rubric"
    >;
  },
) =>
  callApi<ReviseQuestionResponse>(
    `/api/generator/question/${encodeURIComponent(questionId)}/revise`,
    {
      method: "POST",
      body: JSON.stringify({ ...body, preserve: body.preserve ?? [] }),
    }
  );
