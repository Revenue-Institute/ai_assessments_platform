import { redirect } from "next/navigation";
import {
  ApiError,
  type AssessmentSummary,
  type AssignmentMagicLink,
  bulkCreateAssignments,
  listAssessments,
  listSubjects,
  type SubjectSummary,
} from "@/lib/api";
import { CopyButton } from "../../components/copy-button";
import { Header } from "../../components/header";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  error?: string;
  ok?: string;
  links?: string;
  failed?: string;
}>;

export default async function NewAssignmentPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const sp = await searchParams;

  let assessments: AssessmentSummary[] = [];
  let subjects: SubjectSummary[] = [];
  let loadError: string | null = null;
  try {
    [assessments, subjects] = await Promise.all([
      listAssessments(),
      listSubjects(),
    ]);
  } catch (e) {
    if (e instanceof ApiError) loadError = e.message;
    else throw e;
  }

  const publishable = assessments.filter((a) => a.status === "published");

  async function action(formData: FormData): Promise<void> {
    "use server";
    const assessment_id = String(formData.get("assessment_id") ?? "");
    const subject_ids = formData.getAll("subject_ids").map((v) => String(v));
    const expires_in_days = Number.parseInt(
      String(formData.get("expires_in_days") ?? "7"),
      10
    );
    const send_email = formData.get("send_email") === "on";

    if (!assessment_id || subject_ids.length === 0) {
      redirect(
        "/assignments/new?error=" +
          encodeURIComponent("Pick an assessment and at least one subject.")
      );
    }

    try {
      const result = await bulkCreateAssignments({
        assessment_id,
        subject_ids,
        expires_in_days,
        send_email,
      });
      const linksJson = encodeURIComponent(
        JSON.stringify(result.created.map(linkPair))
      );
      const failedJson = encodeURIComponent(JSON.stringify(result.failed));
      redirect(
        `/assignments/new?links=${linksJson}&failed=${failedJson}` +
          (send_email ? "&ok=" + encodeURIComponent("Invites sent") : "")
      );
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/assignments/new?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  const issuedLinks = decodeIssuedLinks(sp.links);
  const failedRows = decodeFailedRows(sp.failed);

  return (
    <>
      <Header page="New assignment" pages={["Assignments"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h1 className="font-semibold text-xl">Issue magic-link assignments</h1>
          <p className="text-muted-foreground text-sm">
            Pick one or more subjects and a published assessment. Each subject
            gets their own assignment + JWT. Invites are emailed via Resend
            when enabled and configured; otherwise copy the URLs from the
            response.
          </p>
        </section>

        {(sp.error || loadError) && (
          <p
            className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
            role="alert"
          >
            {sp.error || loadError}
          </p>
        )}

        {issuedLinks.length > 0 && (
          <section
            className="rounded-xl border border-primary/40 bg-primary/10 p-4 text-sm"
            role="status"
          >
            <p className="font-medium text-primary">
              {issuedLinks.length} magic link
              {issuedLinks.length === 1 ? "" : "s"} issued
              {sp.ok ? ` · ${sp.ok}` : ""}
            </p>
            <p className="mt-1 text-muted-foreground text-xs">
              Tokens are not retrievable later. Copy what you need now.
            </p>
            <ul className="mt-2 space-y-2 text-xs">
              {issuedLinks.map((row, i) => (
                <li className="flex flex-col gap-1" key={i}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">
                      Assignment <code>{row.assignment_id.slice(0, 8)}…</code>
                    </span>
                    <CopyButton label="Copy link" value={row.magic_link_url} />
                  </div>
                  <code className="break-all rounded bg-secondary p-2 text-foreground">
                    {row.magic_link_url}
                  </code>
                </li>
              ))}
            </ul>
          </section>
        )}

        {failedRows.length > 0 && (
          <section
            className="rounded-xl border border-destructive/50 bg-destructive/15 p-4 text-sm"
            role="alert"
          >
            <p className="font-medium text-destructive">
              {failedRows.length} subject{failedRows.length === 1 ? "" : "s"} failed
            </p>
            <ul className="mt-2 space-y-1 text-xs">
              {failedRows.map((f, i) => (
                <li key={i}>
                  <code className="text-destructive">{f.subject_id}</code> ·{" "}
                  {f.detail}
                </li>
              ))}
            </ul>
          </section>
        )}

        <form
          action={action}
          className="grid max-w-3xl gap-3 rounded-xl border border-border/50 bg-muted/20 p-4"
        >
          <label className="space-y-1">
            <span className="text-sm">Assessment (published only)</span>
            <select
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              defaultValue=""
              name="assessment_id"
              required
            >
              <option disabled value="">
                {publishable.length === 0
                  ? "No published assessments, publish one first"
                  : "Pick an assessment"}
              </option>
              {publishable.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.title} ({a.question_count} q · {a.total_duration_minutes} min · {a.module_count} modules)
                </option>
              ))}
            </select>
          </label>

          <fieldset className="space-y-2 rounded border border-border/40 bg-background/30 p-3">
            <legend className="px-1 text-sm">Subjects</legend>
            {subjects.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No subjects, add one in Subjects first.
              </p>
            ) : (
              <ul className="grid max-h-72 gap-1 overflow-auto md:grid-cols-2">
                {subjects.map((s) => (
                  <li key={s.id}>
                    <label className="flex cursor-pointer items-start gap-2 rounded p-1 hover:bg-muted/40">
                      <input
                        className="mt-1"
                        name="subject_ids"
                        type="checkbox"
                        value={s.id}
                      />
                      <span className="min-w-0 flex-1 text-sm">
                        <span className="block truncate font-medium">
                          {s.full_name}
                        </span>
                        <span className="block truncate text-muted-foreground text-xs">
                          {s.email} · {s.type}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>

          <div className="flex flex-wrap items-end gap-3">
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
            <label className="flex items-center gap-2 text-sm">
              <input defaultChecked name="send_email" type="checkbox" />
              <span>Send invite email via Resend</span>
            </label>
          </div>

          <button
            className="btn-primary mt-1 text-sm"
            disabled={publishable.length === 0 || subjects.length === 0}
            type="submit"
          >
            Issue magic links
          </button>
        </form>
      </div>
    </>
  );
}

function linkPair(link: AssignmentMagicLink) {
  return {
    assignment_id: link.assignment_id,
    magic_link_url: link.magic_link_url,
  };
}

function decodeIssuedLinks(
  raw: string | undefined,
): Array<{ assignment_id: string; magic_link_url: string }> {
  if (!raw) return [];
  try {
    return JSON.parse(decodeURIComponent(raw));
  } catch {
    return [];
  }
}

function decodeFailedRows(
  raw: string | undefined,
): Array<{ subject_id: string; detail: string }> {
  if (!raw) return [];
  try {
    return JSON.parse(decodeURIComponent(raw));
  } catch {
    return [];
  }
}
