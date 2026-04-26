import { z } from "zod";

export const QuestionTypeEnum = z.enum([
  "mcq",
  "multi_select",
  "short_answer",
  "long_answer",
  "code",
  "notebook",
  "sql",
  "n8n",
  "diagram",
  "scenario",
]);
export type QuestionType = z.infer<typeof QuestionTypeEnum>;

export const DifficultyEnum = z.enum(["junior", "mid", "senior", "expert"]);
export type Difficulty = z.infer<typeof DifficultyEnum>;

export const VariableSpec = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("int"),
    min: z.number(),
    max: z.number(),
    step: z.number().default(1),
  }),
  z.object({
    kind: z.literal("float"),
    min: z.number(),
    max: z.number(),
    decimals: z.number().default(2),
  }),
  z.object({
    kind: z.literal("choice"),
    options: z.array(z.string()).min(2),
  }),
  z.object({
    kind: z.literal("dataset"),
    pool: z.array(z.string()).min(1),
  }),
  z.object({
    kind: z.literal("string_template"),
    pattern: z.string(),
  }),
]);
export type VariableSpec = z.infer<typeof VariableSpec>;

export const VariableSchema = z.record(z.string(), VariableSpec);
export type VariableSchema = z.infer<typeof VariableSchema>;

export const ScoringMode = z.enum([
  "exact_match",
  "numeric_tolerance",
  "structural_match",
  "rubric_ai",
  "test_cases",
]);
export type ScoringMode = z.infer<typeof ScoringMode>;

export const RubricCriterion = z.object({
  id: z.string(),
  label: z.string(),
  weight: z.number().min(0).max(1),
  description: z.string(),
  scoring_guidance: z.string(),
});
export type RubricCriterion = z.infer<typeof RubricCriterion>;

export const Rubric = z.object({
  version: z.string().default("1"),
  criteria: z.array(RubricCriterion),
  scoring_mode: ScoringMode,
  tolerance: z.number().optional(),
  test_cases: z.array(z.any()).optional(),
});
export type Rubric = z.infer<typeof Rubric>;

export const QuestionTemplate = z.object({
  id: z.string().uuid().optional(),
  type: QuestionTypeEnum,
  prompt_template: z.string(),
  variable_schema: VariableSchema,
  solver_code: z.string().optional(),
  solver_language: z.literal("python").default("python"),
  interactive_config: z.any().optional(),
  rubric: Rubric,
  competency_tags: z.array(z.string()),
  time_limit_seconds: z.number().optional(),
  max_points: z.number().default(10),
  difficulty: DifficultyEnum,
  metadata: z.record(z.string(), z.any()).default({}),
});
export type QuestionTemplate = z.infer<typeof QuestionTemplate>;
