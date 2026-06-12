import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import {
  createSeries,
  issueNextForSeries,
  listSeries,
  listSubjects,
} from "@/lib/api";
import { loadOrApiError, redirectOnApi } from "@/lib/api-helpers";
import { AlertBanner } from "@/components/alert-banner";
import { FormField, FormInput, FormSelect } from "@/components/form-fields";
import { SubmitButton } from "@/components/submit-button";

import { Header } from "../components/header";

export const metadata: Metadata = { title: "Series" };

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ error?: string; ok?: string }>;

export default async function SeriesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error, ok } = await searchParams;

  const { data, error: loadError } = await loadOrApiError(() =>
    Promise.all([listSeries(), listSubjects()])
  );
  const [series, subjects] = data ?? [[], []];

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

    if (!(subject_id && name) || competency_focus.length === 0) {
      redirect(
        "/series?error=" +
          encodeURIComponent(
            "Subject, name, and at least one competency tag are required."
          )
      );
    }

    return redirectOnApi(
      () => createSeries({ subject_id, name, competency_focus, cadence_days }),
      "/series",
      "Series created."
    );
  }

  async function issueNext(formData: FormData): Promise<void> {
    "use server";
    const seriesId = String(formData.get("series_id") ?? "");
    if (!seriesId) {
      return;
    }
    return redirectOnApi(
      () => issueNextForSeries(seriesId),
      "/series",
      (result) =>
        `Issued sequence ${result.sequence_number}: ${result.magic_link_url}`
    );
  }

  return (
    <>
      <Header page="Series" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h2 className="font-semibold text-xl">Assessment series</h2>
          <p className="text-muted-foreground text-sm">
            Track recurring competency check-ins per subject. Auto-scheduling of
            the next assignment lands in a follow-up worker. For v1, link
            assignments to a series via the series detail endpoint.
          </p>
        </section>

        <AlertBanner variant={error || loadError ? "error" : "success"}>
          {error || loadError || ok}
        </AlertBanner>

        <form
          action={action}
          className="grid max-w-2xl gap-3 rounded-xl border border-border/50 bg-muted/20 p-4 md:grid-cols-2"
        >
          <FormField className="md:col-span-2" label="Subject">
            <FormSelect defaultValue="" name="subject_id" required>
              <option disabled value="">
                {subjects.length === 0
                  ? "No candidates, add one in Candidates"
                  : "Pick a candidate"}
              </option>
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.full_name} · {s.email} ({s.type})
                </option>
              ))}
            </FormSelect>
          </FormField>
          <FormField className="md:col-span-2" label="Name">
            <FormInput
              name="name"
              placeholder="HubSpot Workflows competency"
              required
            />
          </FormField>
          <FormField
            className="md:col-span-2"
            label="Competency focus (taxonomy ids, comma-separated)"
          >
            <FormInput
              name="competency_focus"
              placeholder="hubspot.workflows, marketing.analytics"
              required
            />
          </FormField>
          <FormField label="Cadence (days, optional)">
            <FormInput
              max="365"
              min="1"
              name="cadence_days"
              placeholder="30"
              type="number"
            />
          </FormField>
          <div className="flex items-end md:col-span-2">
            <SubmitButton className="btn-primary text-sm" pendingLabel="Creating...">
              Create series
            </SubmitButton>
          </div>
        </form>

        {series.length === 0 ? (
          <p className="text-muted-foreground text-sm">No series yet.</p>
        ) : (
          <table className="w-full overflow-hidden rounded-xl border border-border/50 bg-muted/20 text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground text-xs uppercase">
              <tr>
                <th className="px-4 py-2" scope="col">
                  Series
                </th>
                <th className="px-4 py-2" scope="col">
                  Subject
                </th>
                <th className="px-4 py-2" scope="col">
                  Focus
                </th>
                <th className="px-4 py-2" scope="col">
                  Cadence
                </th>
                <th className="px-4 py-2" scope="col">
                  Next due
                </th>
                <th className="px-4 py-2" scope="col">
                  Assignments
                </th>
                <th className="px-4 py-2" scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {series.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2 font-medium">
                    <Link
                      className="hover:text-primary hover:underline"
                      href={`/series/${s.id}`}
                    >
                      {s.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <p>{s.subject_full_name ?? "-"}</p>
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
                      : "-"}
                  </td>
                  <td className="px-4 py-2">{s.assignment_count}</td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        className="rounded border border-border/50 px-2 py-1 text-xs hover:bg-muted"
                        href={`/series/${s.id}`}
                      >
                        Open
                      </Link>
                      <form action={issueNext}>
                        <input name="series_id" type="hidden" value={s.id} />
                        <SubmitButton
                          className="rounded border border-primary/40 bg-primary/10 px-2 py-1 text-primary text-xs hover:bg-primary/20"
                          pendingLabel="Issuing..."
                        >
                          Issue next
                        </SubmitButton>
                      </form>
                    </div>
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
