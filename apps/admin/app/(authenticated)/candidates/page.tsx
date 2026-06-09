import Link from "next/link";
import { redirect } from "next/navigation";

import {
  createSubject,
  listSubjects,
  type SubjectSummary,
  type SubjectType,
} from "@/lib/api";
import { loadOrApiError, redirectOnApi } from "@/lib/api-helpers";
import { AlertBanner } from "@/components/alert-banner";

import { Header } from "../components/header";
import { AddSubjectForm } from "./add-subject-form";

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

  const { data, error: loadError } = await loadOrApiError(listSubjects);
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
          <h2 className="font-semibold text-xl">Candidates</h2>
          <p className="text-muted-foreground text-sm">
            People who can be assigned assessments.
          </p>
        </section>

        <AlertBanner variant={error || loadError ? "error" : "success"}>
          {error || loadError || ok}
        </AlertBanner>

        <TypeFilterChips active={filter} all={all} />

        <AddSubjectForm action={action} />

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
