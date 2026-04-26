import type { Rubric } from "./question.js";

export type ProvisionResult = {
  embed_url?: string;
  session_token?: string;
  initial_state: unknown;
};

export type GradeBreakdown = {
  criterion_id: string;
  score: number;
  max: number;
  note: string;
};

export type GradeResult = {
  score: number;
  max_score: number;
  rationale: string;
  breakdown: GradeBreakdown[];
};

export interface InteractiveRunner<TConfig, TState, TArtifact> {
  provision(
    attemptId: string,
    config: TConfig,
    variables: Record<string, unknown>
  ): Promise<ProvisionResult>;
  loadState(attemptId: string): Promise<TState>;
  saveState(attemptId: string, state: TState): Promise<void>;
  submit(attemptId: string): Promise<TArtifact>;
  grade(
    artifact: TArtifact,
    config: TConfig,
    rubric: Rubric,
    variables: Record<string, unknown>
  ): Promise<GradeResult>;
  teardown(attemptId: string): Promise<void>;
}
