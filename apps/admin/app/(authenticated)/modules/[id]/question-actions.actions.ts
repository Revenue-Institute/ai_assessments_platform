"use server";

import {
  type PreviewVariantsResponse,
  previewVariants,
  type ReviseQuestionResponse,
  reviseQuestion,
} from "@/lib/api";

// biome-ignore lint/suspicious/useAwait: Server Action -- Next.js requires async
export async function previewVariantsAction(body: {
  variable_schema: Record<string, unknown>;
  prompt_template: string;
  seed_count?: number;
}): Promise<PreviewVariantsResponse> {
  return previewVariants(body);
}

type RevisePreserve = Parameters<typeof reviseQuestion>[1]["preserve"];

// biome-ignore lint/suspicious/useAwait: Server Action -- Next.js requires async
export async function reviseQuestionAction(
  questionId: string,
  body: { instruction: string; preserve?: RevisePreserve }
): Promise<ReviseQuestionResponse> {
  return reviseQuestion(questionId, body);
}
