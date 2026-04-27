import Link from "next/link";
import { ApiError, listModules, type ModuleSummary } from "@/lib/api";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

export default async function ModulesPage() {
  let modules: ModuleSummary[] = [];
  let error: string | null = null;
  try {
    modules = await listModules();
  } catch (e) {
    if (e instanceof ApiError) error = e.message;
    else throw e;
  }

  return (
    <>
      <Header page="Modules" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="flex items-start justify-between rounded-xl border border-border/50 bg-muted/30 p-4">
          <div>
            <h1 className="font-semibold text-xl">Modules</h1>
            <p className="text-muted-foreground text-sm">
              Question modules. Drafts can be edited; published modules can be assigned.
            </p>
          </div>
          <Link className="btn-primary text-sm" href="/modules/new">
            New module
          </Link>
        </section>

        {error && (
          <p
            className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
            role="alert"
          >
            {error}
          </p>
        )}

        {modules.length === 0 && !error ? (
          <div className="rounded-xl border border-dashed border-border/60 bg-muted/10 px-6 py-10 text-center">
            <p className="text-muted-foreground text-sm">
              No modules yet.
            </p>
            <Link className="btn-primary mt-3 text-sm" href="/modules/new">
              Create your first module
            </Link>
          </div>
        ) : (
          <ul className="divide-y divide-border/40 rounded-xl border border-border/50 bg-muted/20">
            {modules.map((m) => (
              <li className="flex items-center justify-between gap-4 px-4 py-3" key={m.id}>
                <div className="min-w-0 flex-1">
                  <Link
                    className="block font-medium hover:underline"
                    href={`/modules/${m.id}`}
                  >
                    {m.title}
                  </Link>
                  <p className="truncate text-muted-foreground text-xs">
                    {m.slug} · {m.domain} · {m.difficulty} · {m.target_duration_minutes} min ·{" "}
                    {m.question_count} questions
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

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "published"
      ? "bg-primary/20 text-primary"
      : status === "archived"
        ? "bg-muted text-muted-foreground"
        : "bg-warning/20 text-warning";
  return (
    <span className={`rounded px-2 py-0.5 font-medium text-xs ${tone}`}>
      {status}
    </span>
  );
}
