import { z } from "zod";
import { DifficultyEnum } from "./question.js";

export const GenerationBrief = z.object({
  role_title: z.string(),
  responsibilities: z.string(),
  target_duration_minutes: z.number(),
  difficulty: DifficultyEnum,
  domains: z.array(z.string()),
  question_mix: z.object({
    mcq_pct: z.number(),
    short_pct: z.number(),
    long_pct: z.number(),
    code_pct: z.number(),
    interactive_pct: z.number(),
  }),
  reference_document_ids: z.array(z.string().uuid()).default([]),
  required_competencies: z.array(z.string()),
  notes: z.string().optional(),
});
export type GenerationBrief = z.infer<typeof GenerationBrief>;

export const GeneratedOutlineTopic = z.object({
  name: z.string(),
  competency_tags: z.array(z.string()),
  weight_pct: z.number(),
  question_count: z.number(),
  recommended_types: z.array(z.string()),
  rationale: z.string(),
});
export type GeneratedOutlineTopic = z.infer<typeof GeneratedOutlineTopic>;

export const GeneratedOutline = z.object({
  title: z.string(),
  description: z.string(),
  topics: z.array(GeneratedOutlineTopic),
  total_points: z.number(),
  estimated_duration_minutes: z.number(),
});
export type GeneratedOutline = z.infer<typeof GeneratedOutline>;

export const GenerationStage = z.enum([
  "outline",
  "full",
  "single_question",
  "revision",
]);
export type GenerationStage = z.infer<typeof GenerationStage>;
