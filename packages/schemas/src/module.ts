import { z } from "zod";
import { DifficultyEnum, QuestionTemplate } from "./question.js";

export const ModuleStatus = z.enum(["draft", "published", "archived"]);
export type ModuleStatus = z.infer<typeof ModuleStatus>;

export const Module = z.object({
  id: z.string().uuid().optional(),
  slug: z.string(),
  title: z.string(),
  description: z.string(),
  domain: z.string(),
  target_duration_minutes: z.number(),
  difficulty: DifficultyEnum,
  status: ModuleStatus.optional(),
  version: z.number().int().optional(),
  questions: z.array(QuestionTemplate).min(1),
});
export type Module = z.infer<typeof Module>;

export const AssessmentStatus = z.enum(["draft", "published", "archived"]);
export type AssessmentStatus = z.infer<typeof AssessmentStatus>;

export const AssessmentModuleEntry = z.object({
  module_id: z.string().uuid(),
  position: z.number().int(),
});
export type AssessmentModuleEntry = z.infer<typeof AssessmentModuleEntry>;

export const Assessment = z.object({
  id: z.string().uuid().optional(),
  slug: z.string(),
  title: z.string(),
  description: z.string().optional(),
  domain: z.string().optional(),
  status: AssessmentStatus.optional(),
  target_duration_minutes: z.number().optional(),
  difficulty: DifficultyEnum.optional(),
  modules: z.array(AssessmentModuleEntry).default([]),
});
export type Assessment = z.infer<typeof Assessment>;
