import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AlertBanner } from "@/components/alert-banner";
import { FormField, FormInput, FormTextarea } from "@/components/form-fields";
import { SubmitButton } from "@/components/submit-button";
import {
  ApiError,
  deleteReference,
  fetchAdminMe,
  listReferences,
  type ReferenceDocumentSummary,
  uploadReferenceText,
  uploadReferenceUrl,
} from "@/lib/api";
import { redirectOnApi } from "@/lib/api-helpers";
import { roleSatisfies } from "@/lib/role-policy";

import { Header } from "../components/header";

export const metadata: Metadata = { title: "References" };

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ error?: string; ok?: string }>;

export default async function ReferencesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error, ok } = await searchParams;

  const [refsResult, meResult] = await Promise.allSettled([
    listReferences(),
    fetchAdminMe(),
  ]);

  const documents: ReferenceDocumentSummary[] =
    refsResult.status === "fulfilled" ? refsResult.value : [];
  let loadError: string | null = null;
  if (refsResult.status === "rejected") {
    loadError =
      refsResult.reason instanceof ApiError
        ? refsResult.reason.message
        : "Could not load references.";
  }

  // Soft-fail: reviewers fall through with canRemove=false; hard backend rules still apply at /api.
  if (
    meResult.status === "rejected" &&
    !(meResult.reason instanceof ApiError)
  ) {
    throw meResult.reason;
  }
  const canRemove =
    meResult.status === "fulfilled" &&
    roleSatisfies(meResult.value.role, "admin");

  async function uploadUrlAction(formData: FormData): Promise<void> {
    "use server";
    const url = String(formData.get("url") ?? "").trim();
    const title = String(formData.get("title") ?? "").trim() || null;
    const domain = String(formData.get("domain") ?? "").trim() || null;
    if (!url) {
      redirect(`/references?error=${encodeURIComponent("URL is required.")}`);
    }
    return redirectOnApi(
      () => uploadReferenceUrl({ url, title, domain }),
      "/references",
      (result) =>
        `Uploaded "${result.document.title}", ${result.chunks_inserted} chunks indexed.`
    );
  }

  async function uploadTextAction(formData: FormData): Promise<void> {
    "use server";
    const title = String(formData.get("title") ?? "").trim();
    const content = String(formData.get("content") ?? "").trim();
    const domain = String(formData.get("domain") ?? "").trim() || null;
    if (!(title && content)) {
      redirect(
        "/references?error=" +
          encodeURIComponent("Title and content are required.")
      );
    }
    return redirectOnApi(
      () => uploadReferenceText({ title, content, domain }),
      "/references",
      (result) =>
        `Uploaded "${result.document.title}", ${result.chunks_inserted} chunks indexed.`
    );
  }

  async function deleteAction(formData: FormData): Promise<void> {
    "use server";
    const id = String(formData.get("id") ?? "");
    if (!id) {
      return;
    }
    return redirectOnApi(
      () => deleteReference(id),
      "/references",
      "Document removed."
    );
  }

  return (
    <>
      <Header page="References" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h2 className="font-semibold text-xl">Reference library</h2>
          <p className="text-muted-foreground text-sm">
            Documents are chunked and embedded with Voyage-3. The generator
            retrieves the top 10 chunks per topic when references are attached
            to a brief.
          </p>
        </section>

        <AlertBanner variant={error || loadError ? "error" : "success"}>
          {error || loadError || ok}
        </AlertBanner>

        <div className="grid gap-4 md:grid-cols-2">
          <form
            action={uploadUrlAction}
            className="space-y-3 rounded-xl border border-border/50 bg-muted/20 p-4"
          >
            <h2 className="font-medium text-sm">Upload from URL</h2>
            <FormField label="URL">
              <FormInput
                className="focus:border-primary focus:outline-none"
                name="url"
                placeholder="https://..."
                required
              />
            </FormField>
            <FormField label="Title (optional)">
              <FormInput
                className="focus:border-primary focus:outline-none"
                name="title"
              />
            </FormField>
            <FormField label="Domain (optional)">
              <FormInput
                className="focus:border-primary focus:outline-none"
                name="domain"
                placeholder="hubspot, ai..."
              />
            </FormField>
            <SubmitButton
              className="btn-primary text-sm"
              pendingLabel="Fetching..."
            >
              Fetch + index
            </SubmitButton>
          </form>

          <form
            action={uploadTextAction}
            className="space-y-3 rounded-xl border border-border/50 bg-muted/20 p-4"
          >
            <h2 className="font-medium text-sm">
              Upload markdown / plain text
            </h2>
            <FormField label="Title">
              <FormInput
                className="focus:border-primary focus:outline-none"
                name="title"
                required
              />
            </FormField>
            <FormField label="Domain (optional)">
              <FormInput
                className="focus:border-primary focus:outline-none"
                name="domain"
              />
            </FormField>
            <FormField label="Content">
              <FormTextarea
                className="h-40 focus:border-primary focus:outline-none"
                name="content"
              />
            </FormField>
            <SubmitButton
              className="btn-primary text-sm"
              pendingLabel="Indexing..."
            >
              Index
            </SubmitButton>
          </form>
        </div>

        <p className="text-muted-foreground text-xs">
          PDF upload is exposed at{" "}
          <code className="rounded bg-muted px-1">
            POST /api/references/pdf
          </code>{" "}
          (multipart). UI lands once we add a file picker.
        </p>

        <section className="rounded-xl border border-border/50 bg-muted/20">
          <header className="border-border/40 border-b px-4 py-2 text-muted-foreground text-xs uppercase tracking-wide">
            Indexed documents
          </header>
          {documents.length === 0 ? (
            <p className="px-4 py-3 text-muted-foreground text-sm">
              Nothing indexed yet.
            </p>
          ) : (
            <ul className="divide-y divide-border/40">
              {documents.map((d) => (
                <li
                  className="flex items-start justify-between gap-4 px-4 py-3 text-sm"
                  key={d.id}
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{d.title}</p>
                    <p className="text-muted-foreground text-xs">
                      {d.chunk_count} chunks · {d.domain ?? "no domain"}
                      {d.source_url ? ` · ${d.source_url}` : ""}
                    </p>
                  </div>
                  {canRemove && (
                    <form action={deleteAction}>
                      <input name="id" type="hidden" value={d.id} />
                      <SubmitButton
                        className="rounded border border-destructive/40 bg-destructive/15 px-2 py-1 text-destructive text-xs hover:bg-destructive/25"
                        pendingLabel="Removing..."
                      >
                        Remove
                      </SubmitButton>
                    </form>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
