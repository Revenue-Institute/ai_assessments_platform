"use server";

import { redirect } from "next/navigation";
import {
  addAssessmentModule,
  ApiError,
  archiveAssessment,
  createAssessment,
  patchAssessment,
  publishAssessment,
  removeAssessmentModule,
  reorderAssessment,
} from "@/lib/api";

export type ActionResult = { ok: true } | { ok: false; error: string };

export async function createAssessmentAction(input: {
  slug: string;
  title: string;
  description: string | null;
  module_ids: string[];
}): Promise<void> {
  const slug = input.slug.trim();
  const title = input.title.trim();
  const description = input.description?.trim() || null;

  if (!slug || !title) {
    redirect(
      `/assessments/new?error=${encodeURIComponent("Slug and title are required.")}`
    );
  }

  let createdId: string | null = null;
  try {
    const created = await createAssessment({
      slug,
      title,
      description,
      module_ids: input.module_ids,
    });
    createdId = created.id;
  } catch (e) {
    if (e instanceof ApiError) {
      redirect(`/assessments/new?error=${encodeURIComponent(e.message)}`);
    }
    throw e;
  }

  redirect(`/assessments/${createdId}`);
}

export async function patchAssessmentAction(
  id: string,
  input: { title: string; description: string | null }
): Promise<ActionResult> {
  const title = input.title.trim();
  if (!title) {
    return { ok: false, error: "Title is required." };
  }
  try {
    await patchAssessment(id, {
      title,
      description: input.description?.trim() || null,
    });
    return { ok: true };
  } catch (e) {
    if (e instanceof ApiError) return { ok: false, error: e.message };
    throw e;
  }
}

export async function addAssessmentModuleAction(
  id: string,
  moduleId: string
): Promise<ActionResult> {
  try {
    await addAssessmentModule(id, { module_id: moduleId });
    return { ok: true };
  } catch (e) {
    if (e instanceof ApiError) return { ok: false, error: e.message };
    throw e;
  }
}

export async function removeAssessmentModuleAction(
  id: string,
  moduleId: string
): Promise<ActionResult> {
  try {
    await removeAssessmentModule(id, moduleId);
    return { ok: true };
  } catch (e) {
    if (e instanceof ApiError) return { ok: false, error: e.message };
    throw e;
  }
}

export async function reorderAssessmentAction(
  id: string,
  moduleIds: string[]
): Promise<ActionResult> {
  try {
    await reorderAssessment(id, moduleIds);
    return { ok: true };
  } catch (e) {
    if (e instanceof ApiError) return { ok: false, error: e.message };
    throw e;
  }
}

export async function publishAssessmentAction(id: string): Promise<void> {
  try {
    await publishAssessment(id);
    redirect(`/assessments/${id}?ok=${encodeURIComponent("Published.")}`);
  } catch (e) {
    if (e instanceof ApiError) {
      redirect(`/assessments/${id}?error=${encodeURIComponent(e.message)}`);
    }
    throw e;
  }
}

export async function archiveAssessmentAction(id: string): Promise<void> {
  try {
    await archiveAssessment(id);
    redirect(`/assessments/${id}?ok=${encodeURIComponent("Archived.")}`);
  } catch (e) {
    if (e instanceof ApiError) {
      redirect(`/assessments/${id}?error=${encodeURIComponent(e.message)}`);
    }
    throw e;
  }
}
