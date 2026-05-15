import { createCallApi } from "@repo/api-client";
import { env } from "@/env";

export { ApiError } from "@repo/api-client";

import { ApiError } from "@repo/api-client";

export type ModuleStatus = "draft" | "published" | "archived";
export type Difficulty = "junior" | "mid" | "senior" | "expert";
export type SubjectType = "candidate" | "employee";
export type AssignmentStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "expired"
  | "cancelled";

export interface ModuleSummary {
  created_at: string;
  description: string | null;
  difficulty: Difficulty;
  domain: string;
  id: string;
  published_at: string | null;
  question_count: number;
  slug: string;
  status: ModuleStatus;
  target_duration_minutes: number;
  title: string;
  version: number;
}

export type ModuleDetail = ModuleSummary & {
  questions: Array<{
    id: string;
    position: number;
    type: string;
    prompt_template: string;
    competency_tags: string[];
    max_points: number;
    time_limit_seconds: number | null;
    variable_schema?: Record<string, unknown>;
    rubric?: Record<string, unknown>;
  }>;
};

export interface SubjectSummary {
  created_at: string;
  email: string;
  full_name: string;
  id: string;
  metadata: Record<string, unknown>;
  type: SubjectType;
}

export type AssessmentStatus = ModuleStatus;

export interface AssessmentSummary {
  created_at: string;
  description: string | null;
  id: string;
  module_count: number;
  published_at: string | null;
  question_count: number;
  slug: string;
  status: AssessmentStatus;
  title: string;
  total_duration_minutes: number;
  version: number;
}

export interface AssessmentModuleEntry {
  difficulty: Difficulty;
  domain: string;
  module_id: string;
  position: number;
  question_count: number;
  target_duration_minutes: number;
  title: string;
}

export type AssessmentDetail = AssessmentSummary & {
  modules: AssessmentModuleEntry[];
};

export interface AssignmentSummary {
  assessment_id: string | null;
  assessment_title: string | null;
  completed_at: string | null;
  created_at: string;
  expires_at: string;
  final_score: number | null;
  id: string;
  integrity_score: number | null;
  max_possible_score: number | null;
  module_id: string | null;
  module_title: string | null;
  needs_review: boolean;
  started_at: string | null;
  status: AssignmentStatus;
  subject_email: string | null;
  subject_full_name: string | null;
  subject_id: string;
}

export interface AttemptSummary {
  active_time_seconds: number | null;
  id: string;
  max_score: number;
  needs_review?: boolean;
  question_template_id: string;
  raw_answer: { value: unknown } | null;
  rendered_prompt: string;
  score: number | null;
  score_rationale: string | null;
  scorer_confidence?: number | null;
  scorer_model?: string | null;
  submitted_at: string | null;
}

export type AssignmentDetail = AssignmentSummary & {
  consent_at: string | null;
  total_time_seconds: number | null;
  attempts: AttemptSummary[];
};

export interface AssignmentMagicLink {
  assessment_id: string | null;
  assignment_id: string;
  expires_at: string;
  magic_link_url: string;
  module_id: string | null;
  subject_id: string;
  token: string;
}

export type AdminRole = "admin" | "reviewer" | "viewer";

export interface AdminMe {
  email: string;
  full_name: string | null;
  role: AdminRole;
  user_id: string;
}

async function authHeader(): Promise<Record<string, string>> {
  // Dynamic import so client bundles that pull a function from this file
  // for type inference (Turbopack can't fully tree-shake the module graph)
  // do not also drag `next/headers` into the client. The runtime here is
  // server-only by design; if a client component ever reaches this code
  // path the dynamic import would fail loudly at runtime.
  const { createSupabaseServerClient } = await import(
    "@/lib/supabase/server"
  );
  const supabase = await createSupabaseServerClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    throw new ApiError("Not signed in.", 401);
  }
  return { Authorization: `Bearer ${session.access_token}` };
}

const callApi = createCallApi({
  baseUrl: env.INTERNAL_API_URL,
  getAuthHeader: authHeader,
});

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
export const createModulePreviewMagicLink = (id: string) =>
  callApi<AssignmentMagicLink>(`/api/modules/${id}/preview-magic-link`, {
    method: "POST",
    body: JSON.stringify({}),
  });
export const archiveModule = (id: string) =>
  callApi<ModuleSummary>(`/api/modules/${id}/archive`, {
    method: "POST",
    body: JSON.stringify({}),
  });

export interface QuestionPayload {
  competency_tags?: string[];
  id?: string;
  interactive_config?: Record<string, unknown> | null;
  max_points?: number;
  metadata?: Record<string, unknown>;
  position?: number;
  prompt_template: string;
  rubric: Record<string, unknown>;
  solver_code?: string | null;
  solver_language?: string;
  time_limit_seconds?: number | null;
  type: string;
  variable_schema?: Record<string, unknown>;
}

export interface QuestionRow {
  competency_tags: string[];
  id: string;
  max_points: number;
  module_id: string;
  position: number;
  prompt_template: string;
  time_limit_seconds: number | null;
  type: string;
}

export const createModuleQuestion = (
  moduleId: string,
  payload: QuestionPayload
) =>
  callApi<QuestionRow>(
    `/api/modules/${encodeURIComponent(moduleId)}/questions`,
    { method: "POST", body: JSON.stringify(payload) }
  );

export const patchModuleQuestion = (
  moduleId: string,
  questionId: string,
  payload: Partial<QuestionPayload>
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

export interface AttemptEvent {
  attempt_id: string | null;
  client_timestamp: string | null;
  event_type: string;
  id: string;
  payload: Record<string, unknown>;
  server_timestamp: string;
  user_agent: string | null;
}

export const listAssignmentEvents = (assignmentId: string) =>
  callApi<AttemptEvent[]>(
    `/api/assignments/${encodeURIComponent(assignmentId)}/events`
  );

export interface ModulePreviewQuestion {
  competency_tags: string[];
  interactive_config: Record<string, unknown> | null;
  max_points: number;
  position: number;
  question_template_id: string;
  rendered_prompt: string;
  time_limit_seconds: number | null;
  type: string;
}

export interface ModulePreviewResponse {
  module_id: string;
  questions: ModulePreviewQuestion[];
}

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
export const createAssessmentPreviewMagicLink = (id: string) =>
  callApi<AssignmentMagicLink>(
    `/api/assessments/${encodeURIComponent(id)}/preview-magic-link`,
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
export const listAssignments = (opts?: { needsReview?: boolean }) => {
  let qs = "";
  if (opts?.needsReview === true) {
    qs = "?needs_review=true";
  } else if (opts?.needsReview === false) {
    qs = "?needs_review=false";
  }
  return callApi<AssignmentSummary[]>(`/api/assignments${qs}`);
};
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

export interface AssignmentBulkResult {
  created: AssignmentMagicLink[];
  failed: Array<{ subject_id: string; detail: string }>;
}

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
  options?: { expires_in_days?: number }
) => {
  const qs = new URLSearchParams();
  if (options?.expires_in_days != null) {
    qs.set("expires_in_days", String(options.expires_in_days));
  }
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
export interface QuestionMix {
  code_pct?: number | null;
  interactive_pct?: number | null;
  long_pct?: number | null;
  mcq_pct?: number | null;
  short_pct?: number | null;
}

export interface GenerationBriefIn {
  difficulty: Difficulty;
  domains: string[];
  notes?: string;
  /** Optional. Omit entirely (or set fields to null) to let the AI choose. */
  question_mix?: QuestionMix | null;
  reference_document_ids: string[];
  required_competencies: string[];
  responsibilities: string;
  role_title: string;
  target_duration_minutes: number;
}

export interface OutlineTopic {
  competency_tags: string[];
  name: string;
  question_count: number;
  rationale: string;
  recommended_types: string[];
  weight_pct: number;
}

export interface GeneratedOutline {
  description: string;
  estimated_duration_minutes: number;
  title: string;
  topics: OutlineTopic[];
  total_points: number;
}

export interface OutlineRunResponse {
  latency_ms: number;
  model: string;
  outline: GeneratedOutline;
  run_id: string;
  tokens_in: number;
  tokens_out: number;
}

export interface GenerationRunRow {
  created_at: string;
  error: string | null;
  id: string;
  input_brief: GenerationBriefIn | Record<string, unknown>;
  latency_ms: number | null;
  model: string;
  outline?: GeneratedOutline;
  output: Record<string, unknown>;
  parent_run_id: string | null;
  stage: "outline" | "full" | "single_question" | "revision";
  status: "pending" | "success" | "failed";
  tokens_in: number | null;
  tokens_out: number | null;
}

export interface QuestionGenerationResponse {
  model: string;
  module_id: string;
  module_run_ids: string[];
  questions_generated: number;
  total_tokens_in: number;
  total_tokens_out: number;
}

export const generateOutline = (body: GenerationBriefIn) =>
  callApi<OutlineRunResponse>("/api/generator/outline", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const fetchGenerationRun = (runId: string) =>
  callApi<GenerationRunRow>(`/api/generator/runs/${encodeURIComponent(runId)}`);

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
export interface ReferenceDocumentSummary {
  chunk_count: number;
  created_at: string;
  domain: string | null;
  id: string;
  source_url: string | null;
  title: string;
}

export interface ReferenceUploadResponse {
  chunks_inserted: number;
  document: ReferenceDocumentSummary;
}

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
export interface ReviseQuestionResponse {
  latency_ms: number;
  model: string;
  question_id: string;
  revised: Record<string, unknown>;
  run_id: string;
  tokens_in: number;
  tokens_out: number;
}

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
  }
) =>
  callApi<ReviseQuestionResponse>(
    `/api/generator/question/${encodeURIComponent(questionId)}/revise`,
    {
      method: "POST",
      body: JSON.stringify({ ...body, preserve: body.preserve ?? [] }),
    }
  );

// Preview variants (spec §6.6). Backend renders sampled prompts for each seed.
export interface PreviewVariantRow {
  expected_answer?: unknown;
  rendered_prompt: string;
  seed: string;
  variables: Record<string, unknown>;
}

export interface PreviewVariantsResponse {
  variants: PreviewVariantRow[];
}

export const previewVariants = (body: {
  variable_schema: Record<string, unknown>;
  prompt_template: string;
  seed_count?: number;
}) =>
  callApi<PreviewVariantsResponse>("/api/generator/preview-variants", {
    method: "POST",
    body: JSON.stringify({ seed_count: 5, ...body }),
  });

// Benchmarks ---------------------------------------------------------------

export interface CompetencyScorePoint {
  assignment_id: string;
  competency_id: string;
  computed_at: string;
  point_possible: number;
  point_total: number;
  score_pct: number;
}

export interface SubjectCompetencyTrend {
  competency_id: string;
  delta_vs_previous: number | null;
  latest_score_pct: number;
  points: CompetencyScorePoint[];
}

export interface SubjectCompetencyResponse {
  subject_id: string;
  trends: SubjectCompetencyTrend[];
}

export interface CohortHeatmapCell {
  assignment_id: string;
  competency_id: string;
  computed_at: string;
  score_pct: number;
  subject_id: string;
}

export interface CohortSubject {
  email: string;
  full_name: string;
  id: string;
  type: SubjectType;
}

export interface CohortHeatmapResponse {
  cells: CohortHeatmapCell[];
  competencies: string[];
  subjects: CohortSubject[];
  team_average_pct: Record<string, number>;
}

export interface WeakSpot {
  competency_id: string;
  median_pct: number;
  sample_size: number;
}

export interface WeakSpotsResponse {
  threshold_pct: number;
  weak_spots: WeakSpot[];
}

export const subjectCompetencyScores = (subjectId: string) =>
  callApi<SubjectCompetencyResponse>(
    `/api/subjects/${encodeURIComponent(subjectId)}/competency-scores`
  );

export const cohortHeatmap = (params: {
  type?: SubjectType;
  domain?: string;
  days?: number;
  role?: string;
  start_date?: string;
  end_date?: string;
}) => {
  const qs = new URLSearchParams();
  if (params.type) {
    qs.set("type", params.type);
  }
  if (params.domain) {
    qs.set("domain", params.domain);
  }
  if (params.days) {
    qs.set("days", String(params.days));
  }
  if (params.role) {
    qs.set("role", params.role);
  }
  if (params.start_date) {
    qs.set("start_date", params.start_date);
  }
  if (params.end_date) {
    qs.set("end_date", params.end_date);
  }
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
  if (params.type) {
    qs.set("type", params.type);
  }
  if (params.threshold_pct != null) {
    qs.set("threshold_pct", String(params.threshold_pct));
  }
  const q = qs.toString();
  return callApi<WeakSpotsResponse>(
    `/api/cohorts/weak-spots${q ? `?${q}` : ""}`
  );
};

// Series -------------------------------------------------------------------

export interface SeriesAssignmentSummary {
  assignment_id: string;
  completed_at: string | null;
  final_score: number | null;
  max_possible_score: number | null;
  sequence_number: number;
  status: string;
}

export interface SeriesSummary {
  assignment_count: number;
  cadence_days: number | null;
  competency_focus: string[];
  created_at: string;
  id: string;
  name: string;
  next_due_at: string | null;
  subject_email: string | null;
  subject_full_name: string | null;
  subject_id: string;
}

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
  assignmentId: string
) =>
  callApi<SeriesDetail>(
    `/api/series/${encodeURIComponent(seriesId)}/assignments/${encodeURIComponent(assignmentId)}`,
    { method: "POST", body: JSON.stringify({}) }
  );

export interface SeriesIssueNextResponse {
  assignment_id: string;
  expires_at: string;
  magic_link_url: string;
  module_id: string;
  next_due_at: string | null;
  sequence_number: number;
  series_id: string;
}

export const issueNextForSeries = (
  seriesId: string,
  options?: { expires_in_days?: number; send_email?: boolean }
) => {
  const qs = new URLSearchParams();
  if (options?.expires_in_days != null) {
    qs.set("expires_in_days", String(options.expires_in_days));
  }
  if (options?.send_email != null) {
    qs.set("send_email", String(options.send_email));
  }
  const q = qs.toString();
  return callApi<SeriesIssueNextResponse>(
    `/api/series/${encodeURIComponent(seriesId)}/issue-next${q ? `?${q}` : ""}`,
    { method: "POST", body: JSON.stringify({}) }
  );
};

// Series trend: longitudinal score per competency across sequence numbers.
// Backend endpoint added in parallel; see specs/requirements.md §11.4.
export interface SeriesTrendPoint {
  assignment_id: string;
  completed_at: string | null;
  score_pct: number | null;
  sequence_number: number;
}

export interface SeriesTrendLine {
  competency_id: string;
  points: SeriesTrendPoint[];
}

export interface SeriesTrendResponse {
  series_id: string;
  trends: SeriesTrendLine[];
}

export const getSeriesTrend = (id: string) =>
  callApi<SeriesTrendResponse>(`/api/series/${encodeURIComponent(id)}/trend`);

export interface CompetencyDistributionResponse {
  competency_id: string;
  max_pct: number;
  median_pct: number;
  min_pct: number;
  p25_pct: number;
  p75_pct: number;
  sample_size: number;
  values: number[];
}

export const competencyDistribution = (params: {
  competency_id: string;
  type?: SubjectType;
  exclude_subject_id?: string;
  subject_id?: string;
  assignment_id?: string;
}) => {
  const qs = new URLSearchParams({ competency_id: params.competency_id });
  if (params.type) {
    qs.set("type", params.type);
  }
  if (params.exclude_subject_id) {
    qs.set("exclude_subject_id", params.exclude_subject_id);
  }
  if (params.subject_id) {
    qs.set("subject_id", params.subject_id);
  }
  if (params.assignment_id) {
    qs.set("assignment_id", params.assignment_id);
  }
  return callApi<CompetencyDistributionResponse>(
    `/api/cohorts/distribution?${qs.toString()}`
  );
};

// Users management (spec §12.1 /settings/users). Internal-user CRUD over
// /api/users. Self-demotion is server-rejected; the frontend mirrors that
// check to keep the UI honest before the round-trip.
export interface AdminUserRow {
  created_at: string;
  email: string;
  full_name: string | null;
  id: string;
  role: AdminRole;
}

export const listAdminUsers = () => callApi<AdminUserRow[]>("/api/users");

export const patchAdminUser = (id: string, body: { role: AdminRole }) =>
  callApi<AdminUserRow>(`/api/users/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

// Generation run SSE URL. EventSource cannot send Authorization headers, so
// the admin app proxies the upstream FastAPI stream at /api/generation-events
// and attaches the Supabase Bearer token server-side. Mirrors the
// scoring-events proxy. Events: topic_completed, finished, failed.
export function generationRunEventsUrl(runId: string): string {
  return `/api/generation-events?run_id=${encodeURIComponent(runId)}`;
}
