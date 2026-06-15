import type { Metadata } from "next";
import Link from "next/link";
import { AlertBanner } from "@/components/alert-banner";
import { StatusBadge } from "@/components/status-badge";
import { listModules, type ModuleSummary } from "@/lib/api";
import { loadOrApiError } from "@/lib/api-helpers";

import { Header } from "../components/header";

export const metadata: Metadata = { title: "Modules" };

export const dynamic = "force-dynamic";

export default async function ModulesPage() {
  const { data, error } = await loadOrApiError(listModules);
  const modules: ModuleSummary[] = data ?? [];

  return (
    <>
      <Header page="Modules" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="flex items-start justify-between rounded-xl border border-border/50 bg-muted/30 p-4">
          <div>
            <h2 className="font-semibold text-xl">Modules</h2>
            <p className="text-muted-foreground text-sm">
              Question modules. Drafts can be edited; published modules can be
              assigned.
            </p>
          </div>
          <Link className="btn-primary text-sm" href="/modules/new">
            New module
          </Link>
        </section>

        <AlertBanner>{error}</AlertBanner>

        {!error && modules.length === 0 ? (
          <div className="rounded-xl border border-border/60 border-dashed bg-muted/10 px-6 py-10 text-center">
            <p className="text-muted-foreground text-sm">No modules yet.</p>
            <Link className="btn-primary mt-3 text-sm" href="/modules/new">
              Create your first module
            </Link>
          </div>
        ) : (
          <ul className="divide-y divide-border/40 rounded-xl border border-border/50 bg-muted/20">
            {modules.map((m) => (
              <li
                className="flex items-center justify-between gap-4 px-4 py-3"
                key={m.id}
              >
                <div className="min-w-0 flex-1">
                  <Link
                    className="block font-medium hover:underline"
                    href={`/modules/${m.id}`}
                  >
                    {m.title}
                  </Link>
                  <p className="truncate text-muted-foreground text-xs">
                    {m.slug} · {m.domain} · {m.difficulty} ·{" "}
                    {m.target_duration_minutes} min · {m.question_count}{" "}
                    questions
                  </p>
                </div>
                <StatusBadge status={m.status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
