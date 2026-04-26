import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ApiError,
  createSubject,
  listSubjects,
  type SubjectSummary,
  type SubjectType,
} from "@/lib/api";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ error?: string; ok?: string }>;

export default async function SubjectsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error, ok } = await searchParams;

  let subjects: SubjectSummary[] = [];
  let loadError: string | null = null;
  try {
    subjects = await listSubjects();
  } catch (e) {
    if (e instanceof ApiError) loadError = e.message;
    else throw e;
  }

  async function action(formData: FormData): Promise<void> {
    "use server";
    const type = String(formData.get("type") ?? "candidate") as SubjectType;
    const full_name = String(formData.get("full_name") ?? "").trim();
    const email = String(formData.get("email") ?? "").trim();
    if (!full_name || !email) {
      redirect("/subjects?error=" + encodeURIComponent("Name and email are required."));
    }
    try {
      await createSubject({ type, full_name, email });
      redirect("/subjects?ok=" + encodeURIComponent("Subject created."));
    } catch (e) {
      if (e instanceof ApiError) {
        redirect("/subjects?error=" + encodeURIComponent(e.message));
      }
      throw e;
    }
  }

  return (
    <>
      <Header page="Subjects" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h1 className="font-semibold text-xl">Subjects</h1>
          <p className="text-muted-foreground text-sm">
            Candidates and employees who can be assigned assessments.
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
          className="grid max-w-2xl grid-cols-1 gap-3 rounded-xl border border-border/50 bg-muted/20 p-4 md:grid-cols-3"
        >
          <label className="space-y-1 md:col-span-1">
            <span className="text-sm">Type</span>
            <select
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              defaultValue="candidate"
              name="type"
            >
              <option value="candidate">candidate</option>
              <option value="employee">employee</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-sm">Full name</span>
            <input
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              name="full_name"
              required
              type="text"
            />
          </label>
          <label className="space-y-1">
            <span className="text-sm">Email</span>
            <input
              className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
              name="email"
              required
              type="email"
            />
          </label>
          <div className="md:col-span-3">
            <button className="btn-primary text-sm" type="submit">
              Add subject
            </button>
          </div>
        </form>

        <ul className="divide-y divide-border/40 rounded-xl border border-border/50 bg-muted/20">
          {subjects.length === 0 ? (
            <li className="px-4 py-3 text-muted-foreground text-sm">
              No subjects yet.
            </li>
          ) : (
            subjects.map((s) => (
              <li className="flex items-center justify-between px-4 py-3" key={s.id}>
                <Link
                  className="block min-w-0 flex-1 hover:underline"
                  href={`/subjects/${s.id}`}
                >
                  <p className="truncate font-medium">{s.full_name}</p>
                  <p className="truncate text-muted-foreground text-xs">
                    {s.email}
                  </p>
                </Link>
                <span className="ml-3 rounded bg-muted px-2 py-0.5 text-xs">
                  {s.type}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </>
  );
}
