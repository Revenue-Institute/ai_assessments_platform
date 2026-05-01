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

export type AssessmentStatus = ModuleStatus;

export type AssessmentSummary = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  status: AssessmentStatus;
  version: number;
  module_count: number;
  question_count: number;
  total_duration_minutes: number;
  created_at: string;
  published_at: string | null;
};

export type AssessmentModuleEntry = {
  module_id: string;
  position: number;
  title: string;
  domain: string;
  difficulty: Difficulty;
  target_duration_minutes: number;
  question_count: number;
};

export type AssessmentDetail = AssessmentSummary & {
  modules: AssessmentModuleEntry[];
};

export type AssignmentSummary = {
  id: string;
  subject_id: string;
  subject_full_name: string | null;
  subject_email: string | null;
  assessment_id: string | null;
  assessment_title: string | null;
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
  assessment_id: string | null;
  module_id: string | null;
  expires_at: string;
  magic_link_url: string;
  token: string;
};

export type AdminRole = "admin" | "reviewer" | "viewer";

export type AdminMe = {
  user_id: string;
  email: string;
  full_name: string | null;
  role: AdminRole;
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

export type QuestionPayload = {
  id?: string;
  position?: number;
  type: string;
  prompt_template: string;
  variable_schema?: Record<string, unknown>;
  solver_code?: string | null;
  solver_language?: string;
  interactive_config?: Record<string, unknown> | null;
  rubric: Record<string, unknown>;
  competency_tags?: string[];
  time_limit_seconds?: number | null;
  max_points?: number;
  metadata?: Record<string, unknown>;
};

export type QuestionRow = {
  id: string;
  module_id: string;
  position: number;
  type: string;
  prompt_template: string;
  competency_tags: string[];
  max_points: number;
  time_limit_seconds: number | null;
};

export const createModuleQuestion = (
  moduleId: string,
  payload: QuestionPayload,
) =>
  callApi<QuestionRow>(
    `/api/modules/${encodeURIComponent(moduleId)}/questions`,
    { method: "POST", body: JSON.stringify(payload) }
  );

export const patchModuleQuestion = (
  moduleId: string,
  questionId: string,
  payload: Partial<QuestionPayload>,
) =>
  callApi<QuestionRow>(
    `/api/modules/${encodeURIComponent(moduleId)}/questions/${encodeURIComponent(questionId)}`,
    { method: "PATCH", body: JSON.stringify(payload) }
  );

export const deleteModuleQuestion = (moduleId: string, questionId: string) =>
  callApi<void>(
    `/api/modules/${encodeURIComponent(moduleId)}/questions/${encodeURIComponent(questionId)}`,
    { method: "DELETE" }
  );

export type AttemptEvent = {
  id: string;
  attempt_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  client_timestamp: string | null;
  server_timestamp: string;
  user_agent: string | null;
};

export const listAssignmentEvents = (assignmentId: string) =>
  callApi<AttemptEvent[]>(
    `/api/assignments/${encodeURIComponent(assignmentId)}/events`
  );

export type ModulePreviewQuestion = {
  question_template_id: string;
  position: number;
  type: string;
  rendered_prompt: string;
  max_points: number;
  time_limit_seconds: number | null;
  competency_tags: string[];
  interactive_config: Record<string, unknown> | null;
};

export type ModulePreviewResponse = {
  module_id: string;
  questions: ModulePreviewQuestion[];
};

export const previewModule = (id: string) =>
  callApi<ModulePreviewResponse>(
    `/api/modules/${encodeURIComponent(id)}/preview`
  );

// Assessments
export const listAssessments = () =>
  callApi<AssessmentSummary[]>("/api/assessments");
export const getAssessment = (id: string) =>
  callApi<AssessmentDetail>(`/api/assessments/${encodeURIComponent(id)}`);
export const createAssessment = (body: {
  slug: string;
  title: string;
  description?: string | null;
  module_ids?: string[];
}) =>
  callApi<AssessmentSummary>("/api/assessments", {
    method: "POST",
    body: JSON.stringify(body),
  });
export const patchAssessment = (
  id: string,
  body: { title?: string; description?: string | null }
) =>
  callApi<AssessmentSummary>(`/api/assessments/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
export const addAssessmentModule = (
  id: string,
  body: { module_id: string; position?: number | null }
) =>
  callApi<AssessmentDetail>(
    `/api/assessments/${encodeURIComponent(id)}/modules`,
    { method: "POST", body: JSON.stringify(body) }
  );
export const removeAssessmentModule = (id: string, moduleId: string) =>
  callApi<AssessmentDetail>(
    `/api/assessments/${encodeURIComponent(id)}/modules/${encodeURIComponent(moduleId)}`,
    { method: "DELETE" }
  );
export const reorderAssessment = (id: string, moduleIds: string[]) =>
  callApi<AssessmentDetail>(
    `/api/assessments/${encodeURIComponent(id)}/reorder`,
    { method: "POST", body: JSON.stringify({ module_ids: moduleIds }) }
  );
export const publishAssessment = (id: string) =>
  callApi<AssessmentSummary>(
    `/api/assessments/${encodeURIComponent(id)}/publish`,
    { method: "POST", body: JSON.stringify({}) }
  );
export const archiveAssessment = (id: string) =>
  callApi<AssessmentSummary>(
    `/api/assessments/${encodeURIComponent(id)}/archive`,
    { method: "POST", body: JSON.stringify({}) }
  );

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
  assessment_id?: string;
  module_id?: string;
  subject_id: string;
  expires_in_days: number;
  send_email?: boolean;
}) =>
  callApi<AssignmentMagicLink>("/api/assignments", {
    method: "POST",
    body: JSON.stringify({ send_email: true, ...body }),
  });

export type AssignmentBulkResult = {
  created: AssignmentMagicLink[];
  failed: Array<{ subject_id: string; detail: string }>;
};

export const bulkCreateAssignments = (body: {
  assessment_id?: string;
  module_id?: string;
  subject_ids: string[];
  expires_in_days: number;
  send_email?: boolean;
}) =>
  callApi<AssignmentBulkResult>("/api/assignments/bulk", {
    method: "POST",
    body: JSON.stringify({ send_email: true, ...body }),
  });
export const cancelAssignment = (id: string) =>
  callApi<AssignmentDetail>(`/api/assignments/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
export const resendAssignmentEmail = (
  id: string,
  options?: { expires_in_days?: number },
) => {
  const qs = new URLSearchParams();
  if (options?.expires_in_days != null)
    qs.set("expires_in_days", String(options.expires_in_days));
  const q = qs.toString();
  return callApi<AssignmentMagicLink>(
    `/api/assignments/${id}/resend-email${q ? `?${q}` : ""}`,
    { method: "POST", body: JSON.stringify({}) }
  );
};
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
export type QuestionMix = {
  mcq_pct?: number | null;
  short_pct?: number | null;
  long_pct?: number | null;
  code_pct?: number | null;
  interactive_pct?: number | null;
};

export type GenerationBriefIn = {
  role_title: string;
  responsibilities: string;
  target_duration_minutes: number;
  difficulty: Difficulty;
  domains: string[];
  /** Optional. Omit entirely (or set fields to null) to let the AI choose. */
  question_mix?: QuestionMix | null;
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

// Benchmarks ---------------------------------------------------------------

export type CompetencyScorePoint = {
  competency_id: string;
  score_pct: number;
  point_total: number;
  point_possible: number;
  assignment_id: string;
  computed_at: string;
};

export type SubjectCompetencyTrend = {
  competency_id: string;
  points: CompetencyScorePoint[];
  latest_score_pct: number;
  delta_vs_previous: number | null;
};

export type SubjectCompetencyResponse = {
  subject_id: string;
  trends: SubjectCompetencyTrend[];
};

export type CohortHeatmapCell = {
  subject_id: string;
  competency_id: string;
  score_pct: number;
  assignment_id: string;
  computed_at: string;
};

export type CohortSubject = {
  id: string;
  full_name: string;
  email: string;
  type: SubjectType;
};

export type CohortHeatmapResponse = {
  subjects: CohortSubject[];
  competencies: string[];
  cells: CohortHeatmapCell[];
  team_average_pct: Record<string, number>;
};

export type WeakSpot = {
  competency_id: string;
  median_pct: number;
  sample_size: number;
};

export type WeakSpotsResponse = {
  threshold_pct: number;
  weak_spots: WeakSpot[];
};

export const subjectCompetencyScores = (subjectId: string) =>
  callApi<SubjectCompetencyResponse>(
    `/api/subjects/${encodeURIComponent(subjectId)}/competency-scores`
  );

export const cohortHeatmap = (params: {
  type?: SubjectType;
  domain?: string;
  days?: number;
}) => {
  const qs = new URLSearchParams();
  if (params.type) qs.set("type", params.type);
  if (params.domain) qs.set("domain", params.domain);
  if (params.days) qs.set("days", String(params.days));
  const q = qs.toString();
  return callApi<CohortHeatmapResponse>(
    `/api/cohorts/heatmap${q ? `?${q}` : ""}`
  );
};

export const weakSpots = (params: {
  type?: SubjectType;
  threshold_pct?: number;
}) => {
  const qs = new URLSearchParams();
  if (params.type) qs.set("type", params.type);
  if (params.threshold_pct != null)
    qs.set("threshold_pct", String(params.threshold_pct));
  const q = qs.toString();
  return callApi<WeakSpotsResponse>(
    `/api/cohorts/weak-spots${q ? `?${q}` : ""}`
  );
};

// Series -------------------------------------------------------------------

export type SeriesAssignmentSummary = {
  assignment_id: string;
  sequence_number: number;
  status: string;
  final_score: number | null;
  max_possible_score: number | null;
  completed_at: string | null;
};

export type SeriesSummary = {
  id: string;
  subject_id: string;
  subject_full_name: string | null;
  subject_email: string | null;
  name: string;
  competency_focus: string[];
  cadence_days: number | null;
  next_due_at: string | null;
  created_at: string;
  assignment_count: number;
};

export type SeriesDetail = SeriesSummary & {
  assignments: SeriesAssignmentSummary[];
};

export const listSeries = () => callApi<SeriesSummary[]>("/api/series");

export const createSeries = (body: {
  subject_id: string;
  name: string;
  competency_focus: string[];
  cadence_days?: number | null;
}) =>
  callApi<SeriesSummary>("/api/series", {
    method: "POST",
    body: JSON.stringify({ cadence_days: null, ...body }),
  });

export const getSeriesDetail = (id: string) =>
  callApi<SeriesDetail>(`/api/series/${encodeURIComponent(id)}`);

export const attachAssignmentToSeries = (
  seriesId: string,
  assignmentId: string,
) =>
  callApi<SeriesDetail>(
    `/api/series/${encodeURIComponent(seriesId)}/assignments/${encodeURIComponent(assignmentId)}`,
    { method: "POST", body: JSON.stringify({}) }
  );

export type SeriesIssueNextResponse = {
  series_id: string;
  assignment_id: string;
  module_id: string;
  magic_link_url: string;
  expires_at: string;
  sequence_number: number;
  next_due_at: string | null;
};

export const issueNextForSeries = (
  seriesId: string,
  options?: { expires_in_days?: number; send_email?: boolean },
) => {
  const qs = new URLSearchParams();
  if (options?.expires_in_days != null)
    qs.set("expires_in_days", String(options.expires_in_days));
  if (options?.send_email != null)
    qs.set("send_email", String(options.send_email));
  const q = qs.toString();
  return callApi<SeriesIssueNextResponse>(
    `/api/series/${encodeURIComponent(seriesId)}/issue-next${q ? `?${q}` : ""}`,
    { method: "POST", body: JSON.stringify({}) }
  );
};

export type CompetencyDistributionResponse = {
  competency_id: string;
  sample_size: number;
  min_pct: number;
  p25_pct: number;
  median_pct: number;
  p75_pct: number;
  max_pct: number;
  values: number[];
};

export const competencyDistribution = (params: {
  competency_id: string;
  type?: SubjectType;
  exclude_subject_id?: string;
}) => {
  const qs = new URLSearchParams({ competency_id: params.competency_id });
  if (params.type) qs.set("type", params.type);
  if (params.exclude_subject_id)
    qs.set("exclude_subject_id", params.exclude_subject_id);
  return callApi<CompetencyDistributionResponse>(
    `/api/cohorts/distribution?${qs.toString()}`
  );
};
