import { redirect } from "next/navigation";
import {
  ApiError,
  createSeries,
  issueNextForSeries,
  listSeries,
  listSubjects,
  type SeriesSummary,
  type SubjectSummary,
} from "@/lib/api";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ error?: string; ok?: string }>;

export default async function SeriesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error, ok } = await searchParams;

  let series: SeriesSummary[] = [];
  let subjects: SubjectSummary[] = [];
  let loadError: string | null = null;
  try {
    [series, subjects] = await Promise.all([listSeries(), listSubjects()]);
  } catch (e) {
    if (e instanceof ApiError) loadError = e.message;
    else throw e;
  }

  async function action(formData: FormData): Promise<void> {
    "use server";
    const subject_id = String(formData.get("subject_id") ?? "");
    const name = String(formData.get("name") ?? "").trim();
    const focusRaw = String(formData.get("competency_focus") ?? "");
    const competency_focus = focusRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const cadenceRaw = String(formData.get("cadence_days") ?? "").trim();
    const cadence_days = cadenceRaw ? Number.parseInt(cadenceRaw, 10) : null;

    if (!subject_id || !name || competency_focus.length === 0) {
      redirect(
        "/series?error=" +
          encodeURIComponent(
            "Subject, name, and at least one competency tag are required."
          )
      );
    }

    try {
      await createSeries({ subject_id, name, competency_focus, cadence_days });
      redirect("/series?ok=" + encodeURIComponent("Series created."));
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/series?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  async function issueNext(formData: FormData): Promise<void> {
    "use server";
    const seriesId = String(formData.get("series_id") ?? "");
    if (!seriesId) return;
    try {
      const result = await issueNextForSeries(seriesId);
      redirect(
        "/series?ok=" +
          encodeURIComponent(
            `Issued sequence ${result.sequence_number}: ${result.magic_link_url}`
          )
      );
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/series?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  return (
    <>
      <Header page="Series" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h1 className="font-semibold text-xl">Assessment series</h1>
          <p className="text-muted-foreground text-sm">
            Track recurring competency check-ins per subject. Auto-scheduling
            of the next assignment lands in a follow-up worker — for v1, link
            assignments to a series via the series detail endpoint.
          </p>
        </section>

        {(error || ok || loadError) && (
          <p
            className={`rounded px-3 py-2 text-sm ${
              error || loadError
                ? "border border-destructive/50 bg-destructive/15 text-destructive"
                : "border border-primary/50 bg-primary/15 text-primary"
            }`}
            role={error || loadError ? "alert" : "status"}
          >
            {error || loadError || ok}
          </p>
        )}

        <form
          action={action}
          className="grid max-w-2xl gap-3 rounded-xl border border-border/50 bg-muted/20 p-4 md:grid-cols-2"
        >
          <label className="space-y-1 md:col-span-2">
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
          <label className="space-y-1 md:col-span-2">
            <span className="text-sm">Name</span>
            <input
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              name="name"
              placeholder="HubSpot Workflows competency"
              required
            />
          </label>
          <label className="space-y-1 md:col-span-2">
            <span className="text-sm">
              Competency focus (taxonomy ids, comma-separated)
            </span>
            <input
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              name="competency_focus"
              placeholder="hubspot.workflows, marketing.analytics"
              required
            />
          </label>
          <label className="space-y-1">
            <span className="text-sm">Cadence (days, optional)</span>
            <input
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              max="365"
              min="1"
              name="cadence_days"
              placeholder="30"
              type="number"
            />
          </label>
          <div className="flex items-end md:col-span-2">
            <button className="btn-primary text-sm" type="submit">
              Create series
            </button>
          </div>
        </form>

        {series.length === 0 ? (
          <p className="text-muted-foreground text-sm">No series yet.</p>
        ) : (
          <table className="w-full overflow-hidden rounded-xl border border-border/50 bg-muted/20 text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground text-xs uppercase">
              <tr>
                <th className="px-4 py-2">Series</th>
                <th className="px-4 py-2">Subject</th>
                <th className="px-4 py-2">Focus</th>
                <th className="px-4 py-2">Cadence</th>
                <th className="px-4 py-2">Next due</th>
                <th className="px-4 py-2">Assignments</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {series.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2 font-medium">{s.name}</td>
                  <td className="px-4 py-2">
                    <p>{s.subject_full_name ?? "—"}</p>
                    <p className="text-muted-foreground text-xs">
                      {s.subject_email ?? ""}
                    </p>
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {s.competency_focus.join(", ")}
                  </td>
                  <td className="px-4 py-2">
                    {s.cadence_days ? `${s.cadence_days}d` : "ad-hoc"}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {s.next_due_at
                      ? new Date(s.next_due_at).toLocaleString()
                      : "—"}
                  </td>
                  <td className="px-4 py-2">{s.assignment_count}</td>
                  <td className="px-4 py-2 text-right">
                    <form action={issueNext}>
                      <input name="series_id" type="hidden" value={s.id} />
                      <button
                        className="rounded border border-primary/40 bg-primary/10 px-2 py-1 text-primary text-xs hover:bg-primary/20"
                        type="submit"
                      >
                        Issue next
                      </button>
                    </form>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
