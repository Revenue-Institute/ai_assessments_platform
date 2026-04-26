import { redirect } from "next/navigation";
import {
  ApiError,
  createAssignment,
  listModules,
  listSubjects,
  type ModuleSummary,
  type SubjectSummary,
} from "@/lib/api";
import { Header } from "../../components/header";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ error?: string; link?: string; expires?: string }>;

export default async function NewAssignmentPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error, link, expires } = await searchParams;

  let modules: ModuleSummary[] = [];
  let subjects: SubjectSummary[] = [];
  let loadError: string | null = null;
  try {
    [modules, subjects] = await Promise.all([listModules(), listSubjects()]);
  } catch (e) {
    if (e instanceof ApiError) loadError = e.message;
    else throw e;
  }

  const publishable = modules.filter((m) => m.status === "published");

  async function action(formData: FormData): Promise<void> {
    "use server";
    const module_id = String(formData.get("module_id") ?? "");
    const subject_id = String(formData.get("subject_id") ?? "");
    const expires_in_days = Number.parseInt(
      String(formData.get("expires_in_days") ?? "7"),
      10
    );
    if (!module_id || !subject_id) {
      redirect(
        "/assignments/new?error=" +
          encodeURIComponent("Pick a module and a subject.")
      );
    }
    try {
      const result = await createAssignment({
        module_id,
        subject_id,
        expires_in_days,
      });
      redirect(
        `/assignments/new?link=${encodeURIComponent(result.magic_link_url)}` +
          `&expires=${encodeURIComponent(result.expires_at)}`
      );
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/assignments/new?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  return (
    <>
      <Header page="New assignment" pages={["Assignments"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h1 className="font-semibold text-xl">Issue a magic-link assignment</h1>
          <p className="text-muted-foreground text-sm">
            The token is signed once and shown below. Copy and email it to the
            subject; it cannot be retrieved later.
          </p>
        </section>

        {(error || loadError) && (
          <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
            {error || loadError}
          </p>
        )}

        {link && (
          <section className="rounded-xl border border-emerald-900/60 bg-emerald-950/30 p-4 text-sm">
            <p className="font-medium text-emerald-200">Magic link issued</p>
            <p className="mt-1 text-emerald-100/70 text-xs">
              Expires {expires ? new Date(expires).toLocaleString() : ""}
            </p>
            <code className="mt-2 block break-all rounded bg-emerald-950/60 p-2 text-emerald-100 text-xs">
              {link}
            </code>
          </section>
        )}

        <form
          action={action}
          className="grid max-w-2xl gap-3 rounded-xl border border-border/50 bg-muted/20 p-4"
        >
          <label className="space-y-1">
            <span className="text-sm">Module (published only)</span>
            <select
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              defaultValue=""
              name="module_id"
              required
            >
              <option disabled value="">
                {publishable.length === 0
                  ? "No published modules — publish one first"
                  : "Pick a module"}
              </option>
              {publishable.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title} ({m.question_count} q · {m.target_duration_minutes} min)
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-sm">Subject</span>
            <select
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              defaultValue=""
              name="subject_id"
              required
            >
              <option disabled value="">
                {subjects.length === 0
                  ? "No subjects — add one in Subjects"
                  : "Pick a subject"}
              </option>
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.full_name} · {s.email} ({s.type})
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-sm">Expires in (days)</span>
            <input
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              defaultValue="7"
              max="90"
              min="1"
              name="expires_in_days"
              required
              type="number"
            />
          </label>
          <button
            className="mt-1 rounded bg-emerald-500 px-3 py-2 text-emerald-950 text-sm hover:bg-emerald-400 disabled:opacity-50"
            disabled={publishable.length === 0 || subjects.length === 0}
            type="submit"
          >
            Issue magic link
          </button>
        </form>
      </div>
    </>
  );
}
