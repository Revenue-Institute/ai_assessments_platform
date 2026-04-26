import { taxonomy } from "@repo/competencies";
import { Header } from "../components/header";

const ROOTS = taxonomy.filter((c) => c.parent_id === null);

export default function CompetenciesPage() {
  return (
    <>
      <Header page="Competencies" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <h1 className="font-semibold text-2xl">Competency taxonomy</h1>
          <p className="mt-1 max-w-prose text-muted-foreground text-sm">
            Read-only view of <code className="rounded bg-muted px-1">packages/competencies/src/taxonomy.json</code>.
            Question templates must tag at least one competency from this list,
            validated at publish time.
          </p>
        </section>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {ROOTS.map((root) => {
            const children = taxonomy.filter((c) => c.parent_id === root.id);
            return (
              <article
                className="rounded-xl border border-border/50 bg-muted/20 p-4"
                key={root.id}
              >
                <header className="mb-3">
                  <h2 className="font-medium text-base">{root.label}</h2>
                  <p className="text-muted-foreground text-xs">
                    <code>{root.id}</code>
                  </p>
                </header>
                <ul className="space-y-1.5">
                  {children.map((child) => (
                    <li className="text-sm" key={child.id}>
                      <span className="font-medium">{child.label}</span>
                      <span className="ml-2 text-muted-foreground text-xs">
                        <code>{child.id}</code>
                      </span>
                    </li>
                  ))}
                </ul>
              </article>
            );
          })}
        </div>
      </div>
    </>
  );
}
