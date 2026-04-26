import { redirect } from "next/navigation";
import { ApiError, createModule, type Difficulty } from "@/lib/api";
import { Header } from "../../components/header";

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
    const description = String(formData.get("description") ?? "").trim() || null;
    const domain = String(formData.get("domain") ?? "").trim();
    const target_duration_minutes = Number.parseInt(
      String(formData.get("target_duration_minutes") ?? "30"),
      10
    );
    const difficulty = String(formData.get("difficulty") ?? "junior") as Difficulty;

    if (!slug || !title || !domain) {
      redirect("/modules/new?error=" + encodeURIComponent("Slug, title, and domain are required."));
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
        redirect("/modules/new?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  return (
    <>
      <Header page="New module" pages={["Modules"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <h1 className="font-semibold text-xl">Create draft module</h1>
          <p className="mt-1 text-muted-foreground text-sm">
            Modules start as drafts. Add questions via the seed script (or AI generation in Phase 2),
            then publish before issuing assignments.
          </p>
        </section>

        {error && (
          <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
            {error}
          </p>
        )}

        <form action={action} className="grid max-w-xl gap-3 rounded-xl border border-border/50 bg-muted/20 p-4">
          <Field label="Slug" name="slug" placeholder="hubspot-workflows-v1" required />
          <Field label="Title" name="title" placeholder="HubSpot Workflows" required />
          <Field
            label="Description"
            name="description"
            placeholder="Optional"
            textarea
          />
          <Field label="Domain" name="domain" placeholder="hubspot, data, sales..." required />
          <Field
            label="Target duration (minutes)"
            name="target_duration_minutes"
            type="number"
            defaultValue="30"
          />
          <label className="space-y-1">
            <span className="text-sm">Difficulty</span>
            <select
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              defaultValue="junior"
              name="difficulty"
            >
              <option value="junior">junior</option>
              <option value="mid">mid</option>
              <option value="senior">senior</option>
              <option value="expert">expert</option>
            </select>
          </label>
          <button
            className="mt-2 rounded bg-emerald-500 px-3 py-2 text-emerald-950 text-sm hover:bg-emerald-400"
            type="submit"
          >
            Create draft
          </button>
        </form>
      </div>
    </>
  );
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
          className={`${className} h-24`}
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
