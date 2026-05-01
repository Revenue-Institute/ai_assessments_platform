import { redirect } from "next/navigation";
import {
  ApiError,
  deleteReference,
  listReferences,
  type ReferenceDocumentSummary,
  uploadReferenceText,
  uploadReferenceUrl,
} from "@/lib/api";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ error?: string; ok?: string }>;

export default async function ReferencesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error, ok } = await searchParams;

  let documents: ReferenceDocumentSummary[] = [];
  let loadError: string | null = null;
  try {
    documents = await listReferences();
  } catch (e) {
    if (e instanceof ApiError) loadError = e.message;
    else throw e;
  }

  async function uploadUrlAction(formData: FormData): Promise<void> {
    "use server";
    const url = String(formData.get("url") ?? "").trim();
    const title = String(formData.get("title") ?? "").trim() || null;
    const domain = String(formData.get("domain") ?? "").trim() || null;
    if (!url) {
      redirect("/references?error=" + encodeURIComponent("URL is required."));
    }
    try {
      const result = await uploadReferenceUrl({ url, title, domain });
      redirect(
        "/references?ok=" +
          encodeURIComponent(
            `Uploaded "${result.document.title}", ${result.chunks_inserted} chunks indexed.`
          )
      );
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/references?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  async function uploadTextAction(formData: FormData): Promise<void> {
    "use server";
    const title = String(formData.get("title") ?? "").trim();
    const content = String(formData.get("content") ?? "").trim();
    const domain = String(formData.get("domain") ?? "").trim() || null;
    if (!title || !content) {
      redirect(
        "/references?error=" +
          encodeURIComponent("Title and content are required.")
      );
    }
    try {
      const result = await uploadReferenceText({ title, content, domain });
      redirect(
        "/references?ok=" +
          encodeURIComponent(
            `Uploaded "${result.document.title}", ${result.chunks_inserted} chunks indexed.`
          )
      );
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/references?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  async function deleteAction(formData: FormData): Promise<void> {
    "use server";
    const id = String(formData.get("id") ?? "");
    if (!id) return;
    try {
      await deleteReference(id);
      redirect("/references?ok=" + encodeURIComponent("Document removed."));
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/references?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  return (
    <>
      <Header page="References" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h1 className="font-semibold text-xl">Reference library</h1>
          <p className="text-muted-foreground text-sm">
            Documents are chunked and embedded with Voyage-3. The generator
            retrieves the top 10 chunks per topic when references are attached
            to a brief.
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

        <div className="grid gap-4 md:grid-cols-2">
          <form
            action={uploadUrlAction}
            className="space-y-3 rounded-xl border border-border/50 bg-muted/20 p-4"
          >
            <h2 className="font-medium text-sm">Upload from URL</h2>
            <Field label="URL" name="url" placeholder="https://..." required />
            <Field label="Title (optional)" name="title" />
            <Field label="Domain (optional)" name="domain" placeholder="hubspot, ai..." />
            <button className="btn-primary text-sm" type="submit">
              Fetch + index
            </button>
          </form>

          <form
            action={uploadTextAction}
            className="space-y-3 rounded-xl border border-border/50 bg-muted/20 p-4"
          >
            <h2 className="font-medium text-sm">Upload markdown / plain text</h2>
            <Field label="Title" name="title" required />
            <Field label="Domain (optional)" name="domain" />
            <Field label="Content" name="content" textarea />
            <button className="btn-primary text-sm" type="submit">
              Index
            </button>
          </form>
        </div>

        <p className="text-muted-foreground text-xs">
          PDF upload is exposed at{" "}
          <code className="rounded bg-muted px-1">POST /api/references/pdf</code>{" "}
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
                <li className="flex items-start justify-between gap-4 px-4 py-3 text-sm" key={d.id}>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{d.title}</p>
                    <p className="text-muted-foreground text-xs">
                      {d.chunk_count} chunks · {d.domain ?? "no domain"}
                      {d.source_url ? ` · ${d.source_url}` : ""}
                    </p>
                  </div>
                  <form action={deleteAction}>
                    <input name="id" type="hidden" value={d.id} />
                    <button
                      className="rounded border border-destructive/40 bg-destructive/15 px-2 py-1 text-destructive text-xs hover:bg-destructive/25"
                      type="submit"
                    >
                      Remove
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

function Field({
  label,
  name,
  placeholder,
  required,
  textarea = false,
}: {
  label: string;
  name: string;
  placeholder?: string;
  required?: boolean;
  textarea?: boolean;
}) {
  const className =
    "block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none";
  return (
    <label className="space-y-1">
      <span className="text-sm">{label}</span>
      {textarea ? (
        <textarea
          className={`${className} h-40`}
          name={name}
          placeholder={placeholder}
          required={required}
        />
      ) : (
        <input
          className={className}
          name={name}
          placeholder={placeholder}
          required={required}
          type="text"
        />
      )}
    </label>
  );
}
