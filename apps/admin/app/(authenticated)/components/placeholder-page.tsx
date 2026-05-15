import type { ReactNode } from "react";
import { Header } from "./header";

interface PlaceholderPageProps {
  children?: ReactNode;
  description: string;
  page: string;
  pages?: string[];
  phase: string;
}

export function PlaceholderPage({
  page,
  pages = [],
  description,
  phase,
  children,
}: PlaceholderPageProps) {
  return (
    <>
      <Header page={page} pages={pages} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <p className="eyebrow-label">{phase}</p>
          <h1 className="mt-1 font-semibold text-2xl">{page}</h1>
          <p className="mt-2 max-w-prose text-muted-foreground text-sm">
            {description}
          </p>
        </section>
        {children}
      </div>
    </>
  );
}
