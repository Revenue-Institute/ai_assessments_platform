import { z } from "zod";
import { DifficultyEnum, QuestionTemplate } from "./question.js";

export const ModuleStatus = z.enum(["draft", "published", "archived"]);
export type ModuleStatus = z.infer<typeof ModuleStatus>;

export const Module = z.object({
  slug: z.string(),
  title: z.string(),
  description: z.string(),
  domain: z.string(),
  target_duration_minutes: z.number(),
  difficulty: DifficultyEnum,
  questions: z.array(QuestionTemplate),
});
export type Module = z.infer<typeof Module>;
