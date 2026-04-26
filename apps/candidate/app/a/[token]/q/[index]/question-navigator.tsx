"use client";

import { useState } from "react";

type Props = {
  token: string;
  current: number;
  total: number;
};

/** Collapsible side panel that lets the candidate jump back to any
 * already-viewed question. Default forward-only — the rail only renders
 * links for indices ≤ current, per spec §13.3 ("only forward navigation
 * allowed unless module config says otherwise"). */
export function QuestionNavigator({ token, current, total }: Props) {
  const [open, setOpen] = useState(true);

  return (
    <aside
      aria-label="Question navigator"
      className={`fixed top-1/2 right-0 -translate-y-1/2 ${
        open ? "translate-x-0" : "translate-x-[calc(100%-1.5rem)]"
      } z-40 hidden transition-transform md:block`}
    >
      <div className="flex items-center">
        <button
          aria-expanded={open}
          aria-label={open ? "Collapse navigator" : "Expand navigator"}
          className="rounded-l border border-r-0 border-border bg-card/90 px-1 py-3 text-muted-foreground text-xs hover:bg-card"
          onClick={() => setOpen((v) => !v)}
          type="button"
        >
          {open ? "›" : "‹"}
        </button>
        <nav className="rounded-l border border-border bg-card/80 p-3 backdrop-blur">
          <p className="eyebrow-label mb-2">Questions</p>
          <ol className="grid grid-cols-5 gap-1.5">
            {Array.from({ length: total }, (_, i) => {
              const visited = i <= current;
              const active = i === current;
              return (
                <li key={i}>
                  {visited ? (
                    <a
                      aria-current={active ? "step" : undefined}
                      className={`block w-8 rounded px-2 py-1 text-center font-mono text-xs ${
                        active
                          ? "bg-primary font-medium text-primary-foreground"
                          : "bg-secondary text-secondary-foreground hover:bg-primary/30"
                      }`}
                      href={`/a/${token}/q/${i}`}
                    >
                      {i + 1}
                    </a>
                  ) : (
                    <span
                      aria-disabled
                      className="block w-8 cursor-not-allowed rounded bg-muted/40 px-2 py-1 text-center font-mono text-muted-foreground/40 text-xs"
                    >
                      {i + 1}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>
      </div>
    </aside>
  );
}
