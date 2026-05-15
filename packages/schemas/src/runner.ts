import type { Rubric } from "./question.js";

export interface ProvisionResult {
  embed_url?: string;
  initial_state: unknown;
  session_token?: string;
}

export interface GradeBreakdown {
  criterion_id: string;
  max: number;
  note: string;
  score: number;
}

export interface GradeResult {
  breakdown: GradeBreakdown[];
  max_score: number;
  rationale: string;
  score: number;
}

export interface InteractiveRunner<TConfig, TState, TArtifact> {
  grade(
    artifact: TArtifact,
    config: TConfig,
    rubric: Rubric,
    variables: Record<string, unknown>
  ): Promise<GradeResult>;
  loadState(attemptId: string): Promise<TState>;
  provision(
    attemptId: string,
    config: TConfig,
    variables: Record<string, unknown>
  ): Promise<ProvisionResult>;
  saveState(attemptId: string, state: TState): Promise<void>;
  submit(attemptId: string): Promise<TArtifact>;
  teardown(attemptId: string): Promise<void>;
}
