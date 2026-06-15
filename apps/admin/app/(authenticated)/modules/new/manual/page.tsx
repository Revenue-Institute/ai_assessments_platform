import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AlertBanner } from "@/components/alert-banner";
import {
  FormField,
  FormInput,
  FormSelect,
  FormTextarea,
} from "@/components/form-fields";
import { SubmitButton } from "@/components/submit-button";
import { ApiError, createModule, type Difficulty } from "@/lib/api";

import { Header } from "../../../components/header";

export const metadata: Metadata = { title: "New Module" };

type SearchParams = Promise<{ error?: string }>;

export default async function NewModulePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error } = await searchParams;

  async function action(formData: FormData): Promise<void> {
    "use server";
    const slug = String(formData.get("slug") ?? "").trim();
    const title = String(formData.get("title") ?? "").trim();
    const description =
      String(formData.get("description") ?? "").trim() || null;
    const domain = String(formData.get("domain") ?? "").trim();
    const target_duration_minutes = Number.parseInt(
      String(formData.get("target_duration_minutes") ?? "30"),
      10
    );
    const difficulty = String(
      formData.get("difficulty") ?? "junior"
    ) as Difficulty;

    if (!(slug && title && domain)) {
      redirect(
        "/modules/new?error=" +
          encodeURIComponent("Slug, title, and domain are required.")
      );
    }

    try {
      const created = await createModule({
        slug,
        title,
        description,
        domain,
        target_duration_minutes,
        difficulty,
      });
      redirect(`/modules/${created.id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/modules/new/manual?error=${encodeURIComponent(e.message)}`);
      }
      throw e;
    }
  }

  return (
    <>
      <Header page="New module" pages={["Modules"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <h2 className="font-semibold text-xl">Create draft module</h2>
          <p className="mt-1 text-muted-foreground text-sm">
            Modules start as drafts. Add questions via the seed script (or AI
            generation in Phase 2), then publish before issuing assignments.
          </p>
        </section>

        <AlertBanner>{error}</AlertBanner>

        <form
          action={action}
          className="grid max-w-xl gap-3 rounded-xl border border-border/50 bg-muted/20 p-4"
        >
          <FormField label="Slug">
            <FormInput
              className="focus:border-primary focus:outline-none"
              name="slug"
              placeholder="hubspot-workflows-v1"
              required
            />
          </FormField>
          <FormField label="Title">
            <FormInput
              className="focus:border-primary focus:outline-none"
              name="title"
              placeholder="HubSpot Workflows"
              required
            />
          </FormField>
          <FormField label="Description">
            <FormTextarea
              className="h-24 focus:border-primary focus:outline-none"
              name="description"
              placeholder="Optional"
            />
          </FormField>
          <FormField label="Domain">
            <FormInput
              className="focus:border-primary focus:outline-none"
              name="domain"
              placeholder="hubspot, data, sales..."
              required
            />
          </FormField>
          <FormField label="Target duration (minutes)">
            <FormInput
              className="focus:border-primary focus:outline-none"
              defaultValue="30"
              name="target_duration_minutes"
              type="number"
            />
          </FormField>
          <FormField label="Difficulty">
            <FormSelect defaultValue="junior" name="difficulty">
              <option value="junior">junior</option>
              <option value="mid">mid</option>
              <option value="senior">senior</option>
              <option value="expert">expert</option>
            </FormSelect>
          </FormField>
          <SubmitButton
            className="btn-primary mt-2 text-sm"
            pendingLabel="Creating..."
          >
            Create draft
          </SubmitButton>
        </form>
      </div>
    </>
  );
}
