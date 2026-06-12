import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import {
  ApiError,
  type Difficulty,
  type GenerationBriefIn,
  generateOutline,
} from "@/lib/api";
import { AlertBanner } from "@/components/alert-banner";
import { FormField, FormInput, FormSelect, FormTextarea } from "@/components/form-fields";
import { SubmitButton } from "@/components/submit-button";

import { Header } from "../../components/header";

export const metadata: Metadata = { title: "New Module" };

type SearchParams = Promise<{ error?: string }>;

const DEFAULT_RESPONSIBILITIES = `Designs and builds HubSpot Workflows for lifecycle marketing.
Owns lead routing, scoring, and ICP-based segmentation.
Integrates HubSpot with Salesforce, Slack, and the data warehouse.
Builds dashboards in HubSpot Reporting and runs weekly attribution reviews.`;

export default async function NewModuleWizardPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error } = await searchParams;

  async function action(formData: FormData): Promise<void> {
    "use server";
    const role_title = String(formData.get("role_title") ?? "").trim();
    const responsibilities = String(
      formData.get("responsibilities") ?? ""
    ).trim();

    if (!(role_title && responsibilities)) {
      redirect(
        "/modules/new?error=" +
          encodeURIComponent("Role title and responsibilities are required.")
      );
    }

    const target_duration_minutes = Number.parseInt(
      String(formData.get("target_duration_minutes") ?? "45"),
      10
    );
    const difficulty = String(
      formData.get("difficulty") ?? "mid"
    ) as Difficulty;
    const domains = String(formData.get("domains") ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const required_competencies = String(
      formData.get("required_competencies") ?? ""
    )
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const notes = String(formData.get("notes") ?? "").trim() || undefined;

    const mix = {
      mcq_pct: optionalPct(formData, "mcq_pct"),
      short_pct: optionalPct(formData, "short_pct"),
      long_pct: optionalPct(formData, "long_pct"),
      code_pct: optionalPct(formData, "code_pct"),
      interactive_pct: optionalPct(formData, "interactive_pct"),
    };
    const allEmpty = Object.values(mix).every((v) => v === null);
    const constrainedTotal = Object.values(mix).reduce<number>(
      (acc, v) => acc + (v ?? 0),
      0
    );
    if (constrainedTotal > 100.5) {
      redirect(
        "/modules/new?error=" +
          encodeURIComponent(
            `Question-mix percentages sum to ${constrainedTotal.toFixed(0)}%. Reduce values so they total at most 100, or clear them so the AI can choose.`
          )
      );
    }

    const brief: GenerationBriefIn = {
      role_title,
      responsibilities,
      target_duration_minutes,
      difficulty,
      domains,
      ...(allEmpty ? {} : { question_mix: mix }),
      reference_document_ids: [],
      required_competencies,
      notes,
    };

    try {
      const result = await generateOutline(brief);
      redirect(`/modules/new/${result.run_id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/modules/new?error=${encodeURIComponent(e.message)}`);
      }
      throw e;
    }
  }

  return (
    <>
      <Header page="New module (AI generation)" pages={["Modules"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="flex items-start justify-between rounded-xl border border-border/50 bg-muted/30 p-6">
          <div>
            <p className="eyebrow-label">Step 1 of 2 · Brief</p>
            <h2 className="mt-1 font-semibold text-2xl">Describe the role</h2>
            <p className="mt-1 max-w-prose text-muted-foreground text-sm">
              The AI generator turns a role description into a balanced outline
              you can edit before questions are written.
            </p>
          </div>
          <Link
            className="rounded border border-border/50 bg-background px-3 py-2 text-sm hover:bg-muted"
            href="/modules/new/manual"
          >
            Skip AI · create manually
          </Link>
        </section>

        <AlertBanner>{error}</AlertBanner>

        <form
          action={action}
          className="grid max-w-3xl gap-4 rounded-xl border border-border/50 bg-muted/20 p-4"
        >
          <FormField label="Role title">
            <FormInput
              className="focus:border-primary focus:outline-none"
              name="role_title"
              placeholder="HubSpot Workflows Architect"
              required
            />
          </FormField>
          <FormField label="Responsibilities">
            <FormTextarea
              className="h-32 focus:border-primary focus:outline-none"
              defaultValue={DEFAULT_RESPONSIBILITIES}
              name="responsibilities"
              placeholder="Paste from JD or write 4-8 bullet points"
            />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Target duration (minutes)">
              <FormInput
                className="focus:border-primary focus:outline-none"
                defaultValue="45"
                name="target_duration_minutes"
                type="number"
              />
            </FormField>
            <FormField label="Difficulty">
              <FormSelect defaultValue="mid" name="difficulty">
                <option value="junior">junior</option>
                <option value="mid">mid</option>
                <option value="senior">senior</option>
                <option value="expert">expert</option>
              </FormSelect>
            </FormField>
          </div>
          <FormField label="Domains (comma-separated)">
            <FormInput
              className="focus:border-primary focus:outline-none"
              name="domains"
              placeholder="hubspot, marketing, ops"
            />
          </FormField>
          <FormField label="Required competencies">
            <FormInput
              className="focus:border-primary focus:outline-none"
              name="required_competencies"
              placeholder="e.g. hubspot.workflows, marketing.analytics"
            />
          </FormField>

          <fieldset className="space-y-3 rounded border border-border/40 bg-background/30 p-3">
            <legend className="eyebrow-label px-1">
              Question mix (%) (optional)
            </legend>
            <p className="text-muted-foreground text-xs">
              Leave every box blank to let the AI choose the mix from the role
              and responsibilities. Set one or more to constrain the AI;
              remaining blanks are filled to total 100%. Filled values must sum
              to at most 100.
            </p>
            <div className="grid grid-cols-5 gap-3">
              <NumField label="mcq" name="mcq_pct" />
              <NumField label="short" name="short_pct" />
              <NumField label="long" name="long_pct" />
              <NumField label="code" name="code_pct" />
              <NumField label="interactive" name="interactive_pct" />
            </div>
          </fieldset>

          <FormField label="Notes for the generator (optional)">
            <FormTextarea
              className="h-32 focus:border-primary focus:outline-none"
              name="notes"
            />
          </FormField>

          <SubmitButton className="btn-primary text-sm" pendingLabel="Generating outline...">
            Generate outline
          </SubmitButton>
          <p className="text-muted-foreground text-xs">
            The first call typically takes 10-25 seconds. You'll review the
            outline before any questions are written.
          </p>
        </form>
      </div>
    </>
  );
}

function optionalPct(form: FormData, name: string): number | null {
  const raw = String(form.get(name) ?? "").trim();
  if (raw === "") {
    return null;
  }
  const v = Number.parseFloat(raw);
  if (!Number.isFinite(v) || v < 0 || v > 100) {
    return null;
  }
  return v;
}


function NumField({ label, name }: { label: string; name: string }) {
  return (
    <label className="space-y-1">
      <span className="text-muted-foreground text-xs">{label}</span>
      <input
        className="block w-full rounded border border-border/60 bg-background px-2 py-1 text-sm focus:border-primary focus:outline-none"
        max="100"
        min="0"
        name={name}
        placeholder="AI"
        step="5"
        type="number"
      />
    </label>
  );
}
