import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ApiError,
  type Difficulty,
  type GenerationBriefIn,
  generateOutline,
} from "@/lib/api";
import { Header } from "../../components/header";

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
    const responsibilities = String(formData.get("responsibilities") ?? "").trim();
    const target_duration_minutes = Number.parseInt(
      String(formData.get("target_duration_minutes") ?? "45"),
      10
    );
    const difficulty = String(formData.get("difficulty") ?? "mid") as Difficulty;
    const domains = String(formData.get("domains") ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const required_competencies = String(formData.get("required_competencies") ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const notes = String(formData.get("notes") ?? "").trim() || undefined;

    const brief: GenerationBriefIn = {
      role_title,
      responsibilities,
      target_duration_minutes,
      difficulty,
      domains,
      question_mix: {
        mcq_pct: pctField(formData, "mcq_pct", 30),
        short_pct: pctField(formData, "short_pct", 20),
        long_pct: pctField(formData, "long_pct", 20),
        code_pct: pctField(formData, "code_pct", 15),
        interactive_pct: pctField(formData, "interactive_pct", 15),
      },
      reference_document_ids: [],
      required_competencies,
      notes,
    };

    if (!role_title || !responsibilities) {
      redirect(
        "/modules/new?error=" +
          encodeURIComponent("Role title and responsibilities are required.")
      );
    }

    try {
      const result = await generateOutline(brief);
      redirect(`/modules/new/${result.run_id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/modules/new?error=" + encodeURIComponent(e.message));
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
            <p className="text-emerald-300/70 text-xs uppercase tracking-widest">
              Step 1 of 2 · Brief
            </p>
            <h1 className="mt-1 font-semibold text-2xl">Describe the role</h1>
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

        {error && (
          <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
            {error}
          </p>
        )}

        <form action={action} className="grid max-w-3xl gap-4 rounded-xl border border-border/50 bg-muted/20 p-4">
          <Field label="Role title" name="role_title" placeholder="HubSpot Workflows Architect" required />
          <Field
            label="Responsibilities"
            name="responsibilities"
            placeholder="Paste from JD or write 4-8 bullet points"
            defaultValue={DEFAULT_RESPONSIBILITIES}
            textarea
          />
          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Target duration (minutes)"
              name="target_duration_minutes"
              type="number"
              defaultValue="45"
            />
            <label className="space-y-1">
              <span className="text-sm">Difficulty</span>
              <select
                className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
                defaultValue="mid"
                name="difficulty"
              >
                <option value="junior">junior</option>
                <option value="mid">mid</option>
                <option value="senior">senior</option>
                <option value="expert">expert</option>
              </select>
            </label>
          </div>
          <Field
            label="Domains (comma-separated)"
            name="domains"
            placeholder="hubspot, marketing, ops"
          />
          <Field
            label="Required competencies (taxonomy ids, comma-separated)"
            name="required_competencies"
            placeholder="hubspot.workflows, marketing.analytics"
          />

          <fieldset className="grid grid-cols-5 gap-3 rounded border border-border/40 bg-background/30 p-3">
            <legend className="px-1 text-emerald-300/70 text-xs uppercase tracking-wide">
              Question mix (%)
            </legend>
            <NumField label="mcq" name="mcq_pct" defaultValue="30" />
            <NumField label="short" name="short_pct" defaultValue="20" />
            <NumField label="long" name="long_pct" defaultValue="20" />
            <NumField label="code" name="code_pct" defaultValue="15" />
            <NumField label="interactive" name="interactive_pct" defaultValue="15" />
          </fieldset>

          <Field label="Notes for the generator (optional)" name="notes" textarea />

          <button
            className="rounded bg-emerald-500 px-3 py-2 text-emerald-950 text-sm hover:bg-emerald-400"
            type="submit"
          >
            Generate outline
          </button>
          <p className="text-muted-foreground text-xs">
            The first call typically takes 10-25 seconds. You'll review the outline before any questions are written.
          </p>
        </form>
      </div>
    </>
  );
}

function pctField(form: FormData, name: string, fallback: number): number {
  const v = Number.parseFloat(String(form.get(name) ?? ""));
  return Number.isFinite(v) ? v : fallback;
}

function Field({
  label,
  name,
  placeholder,
  defaultValue,
  required,
  type = "text",
  textarea = false,
}: {
  label: string;
  name: string;
  placeholder?: string;
  defaultValue?: string;
  required?: boolean;
  type?: string;
  textarea?: boolean;
}) {
  const className =
    "block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none";
  return (
    <label className="space-y-1">
      <span className="text-sm">{label}</span>
      {textarea ? (
        <textarea
          className={`${className} h-32`}
          defaultValue={defaultValue}
          name={name}
          placeholder={placeholder}
        />
      ) : (
        <input
          className={className}
          defaultValue={defaultValue}
          name={name}
          placeholder={placeholder}
          required={required}
          type={type}
        />
      )}
    </label>
  );
}

function NumField({
  label,
  name,
  defaultValue,
}: {
  label: string;
  name: string;
  defaultValue: string;
}) {
  return (
    <label className="space-y-1">
      <span className="text-muted-foreground text-xs">{label}</span>
      <input
        className="block w-full rounded border border-border/60 bg-background px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none"
        defaultValue={defaultValue}
        max="100"
        min="0"
        name={name}
        step="5"
        type="number"
      />
    </label>
  );
}
