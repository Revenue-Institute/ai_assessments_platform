"use server";

import { redirect } from "next/navigation";

import {
  ApiError,
  addAssessmentModule,
  archiveAssessment,
  createAssessment,
  patchAssessment,
  publishAssessment,
  removeAssessmentModule,
  reorderAssessment,
} from "@/lib/api";
import { type ActionResult, redirectOnApi, runApiAction } from "@/lib/api-helpers";

export type { ActionResult } from "@/lib/api-helpers";

export async function createAssessmentAction(input: {
  slug: string;
  title: string;
  description: string | null;
  module_ids: string[];
}): Promise<void> {
  const slug = input.slug.trim();
  const title = input.title.trim();
  const description = input.description?.trim() || null;

  if (!(slug && title)) {
    redirect(
      `/assessments/new?error=${encodeURIComponent("Slug and title are required.")}`
    );
  }

  try {
    const created = await createAssessment({
      slug,
      title,
      description,
      module_ids: input.module_ids,
    });
    redirect(`/assessments/${created.id}`);
  } catch (e) {
    if (e instanceof ApiError) {
      redirect(`/assessments/new?error=${encodeURIComponent(e.message)}`);
    }
    throw e;
  }
}

export async function patchAssessmentAction(
  id: string,
  input: { title: string; description: string | null }
): Promise<ActionResult> {
  const title = input.title.trim();
  if (!title) {
    return { ok: false, error: "Title is required." };
  }
  return runApiAction(() =>
    patchAssessment(id, {
      title,
      description: input.description?.trim() || null,
    })
  );
}

export async function addAssessmentModuleAction(
  id: string,
  moduleId: string
): Promise<ActionResult> {
  return runApiAction(() =>
    addAssessmentModule(id, { module_id: moduleId })
  );
}

export async function removeAssessmentModuleAction(
  id: string,
  moduleId: string
): Promise<ActionResult> {
  return runApiAction(() => removeAssessmentModule(id, moduleId));
}

export async function reorderAssessmentAction(
  id: string,
  moduleIds: string[]
): Promise<ActionResult> {
  return runApiAction(() => reorderAssessment(id, moduleIds));
}

export async function publishAssessmentAction(id: string): Promise<void> {
  await redirectOnApi(
    () => publishAssessment(id),
    `/assessments/${id}`,
    "Published."
  );
}

export async function archiveAssessmentAction(id: string): Promise<void> {
  await redirectOnApi(
    () => archiveAssessment(id),
    `/assessments/${id}`,
    "Archived."
  );
}
