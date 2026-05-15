import Link from "next/link";
import { redirect } from "next/navigation";
import {
  createSubject,
  listSubjects,
  type SubjectSummary,
  type SubjectType,
} from "@/lib/api";
import { loadOrApiError, redirectOnApi } from "@/lib/api-helpers";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

type TypeFilter = "all" | "candidate" | "employee";

type SearchParams = Promise<{
  error?: string;
  ok?: string;
  type?: string;
}>;

function normalizeFilter(value: string | undefined): TypeFilter {
  if (value === "all" || value === "candidate" || value === "employee") {
    return value;
  }
  // Spec §12.1: default the /candidates list to candidate-type subjects.
  return "candidate";
}

export default async function CandidatesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error, ok, type } = await searchParams;
  const filter = normalizeFilter(type);

  const { data, error: loadError } = await loadOrApiError(() => listSubjects());
  const all: SubjectSummary[] = data ?? [];

  const candidates =
    filter === "all" ? all : all.filter((c) => c.type === filter);

  async function action(formData: FormData): Promise<void> {
    "use server";
    const submittedType = String(
      formData.get("type") ?? "candidate"
    ) as SubjectType;
    const full_name = String(formData.get("full_name") ?? "").trim();
    const email = String(formData.get("email") ?? "").trim();
    if (!(full_name && email)) {
      redirect(
        "/candidates?error=" +
          encodeURIComponent("Name and email are required.")
      );
    }
    return redirectOnApi(
      () => createSubject({ type: submittedType, full_name, email }),
      "/candidates",
      "Candidate created."
    );
  }

  return (
    <>
      <Header page="Candidates" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h1 className="font-semibold text-xl">Candidates</h1>
          <p className="text-muted-foreground text-sm">
            People who can be assigned assessments.
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

        <TypeFilterChips active={filter} all={all} />

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
              Add candidate
            </button>
          </div>
        </form>

        <ul className="divide-y divide-border/40 rounded-xl border border-border/50 bg-muted/20">
          {candidates.length === 0 ? (
            <li className="px-4 py-3 text-muted-foreground text-sm">
              {all.length === 0
                ? "No candidates yet."
                : `No ${filter === "all" ? "people" : `${filter}s`} match this filter.`}
            </li>
          ) : (
            candidates.map((c) => (
              <li
                className="flex items-center justify-between px-4 py-3"
                key={c.id}
              >
                <Link
                  className="block min-w-0 flex-1 hover:underline"
                  href={`/candidates/${c.id}`}
                >
                  <p className="truncate font-medium">{c.full_name}</p>
                  <p className="truncate text-muted-foreground text-xs">
                    {c.email}
                  </p>
                </Link>
                <span className="ml-3 rounded bg-muted px-2 py-0.5 text-xs">
                  {c.type}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </>
  );
}

function TypeFilterChips({
  active,
  all,
}: {
  active: TypeFilter;
  all: SubjectSummary[];
}) {
  const counts = {
    all: all.length,
    candidate: all.filter((c) => c.type === "candidate").length,
    employee: all.filter((c) => c.type === "employee").length,
  } as const;

  const options: Array<{ value: TypeFilter; label: string }> = [
    { value: "all", label: "All" },
    { value: "candidate", label: "Candidates" },
    { value: "employee", label: "Employees" },
  ];

  return (
    <fieldset
      aria-label="Filter by subject type"
      className="flex flex-wrap items-center gap-2 border-0 p-0"
    >
      {options.map((opt) => {
        const isActive = active === opt.value;
        return (
          <Link
            aria-pressed={isActive}
            className={`rounded border px-3 py-1.5 text-xs transition ${
              isActive
                ? "border-primary/60 bg-primary/15 text-primary"
                : "border-border bg-card text-muted-foreground hover:border-primary/40"
            }`}
            href={`/candidates?type=${opt.value}`}
            key={opt.value}
          >
            {opt.label}
            <span className="ml-1.5 text-[10px] opacity-70">
              ({counts[opt.value]})
            </span>
          </Link>
        );
      })}
    </fieldset>
  );
}
