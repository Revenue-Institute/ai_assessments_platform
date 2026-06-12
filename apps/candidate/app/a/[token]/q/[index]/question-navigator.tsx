"use client";

import { useEffect, useState } from "react";

interface Props {
  current: number;
  total: number;
}

function useBlockBackNavigation() {
  useEffect(() => {
    const url = window.location.href;

    history.pushState(null, "", url);

    function onPopState() {
      history.pushState(null, "", url);
    }

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);
}

/** Collapsible side panel showing question progress. Previously answered
 * questions are shown as non-clickable indicators; only the current question
 * is active. Forward-only navigation per spec §13.3. */
export function QuestionNavigator({ current, total }: Props) {
  useBlockBackNavigation();

  const [open, setOpen] = useState(true);
  const numbers = questionNumbers(total);

  return (
    <>
      <nav
        aria-label="Question navigator"
        className="-mx-4 mb-2 overflow-x-auto px-4 md:hidden"
      >
        <ol className="flex gap-1.5">
          {numbers.map((number) => {
            const index = number - 1;
            const active = index === current;
            return (
              <li className="shrink-0" key={`q-mobile-${number}`}>
                {active ? (
                  <span
                    aria-current="step"
                    className="block min-w-9 rounded bg-primary px-2 py-1 text-center font-medium font-mono text-primary-foreground text-xs"
                  >
                    {number}
                  </span>
                ) : (
                  <span
                    aria-disabled
                    className="block min-w-9 cursor-not-allowed rounded bg-muted/40 px-2 py-1 text-center font-mono text-muted-foreground/40 text-xs"
                  >
                    {number}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

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
            className="rounded-l border border-border border-r-0 bg-card/90 px-1 py-3 text-muted-foreground text-xs hover:bg-card"
            onClick={() => setOpen((v) => !v)}
            type="button"
          >
            {open ? "›" : "‹"}
          </button>
          <nav className="rounded-l border border-border bg-card/80 p-3 backdrop-blur">
            <p className="eyebrow-label mb-2">Questions</p>
            <ol className="grid grid-cols-5 gap-1.5">
              {numbers.map((number) => {
                const index = number - 1;
                const active = index === current;
                return (
                  <li key={`q-rail-${number}`}>
                    {active ? (
                      <span
                        aria-current="step"
                        className="block w-8 rounded bg-primary px-2 py-1 text-center font-medium font-mono text-primary-foreground text-xs"
                      >
                        {number}
                      </span>
                    ) : (
                      <span
                        aria-disabled
                        className="block w-8 cursor-not-allowed rounded bg-muted/40 px-2 py-1 text-center font-mono text-muted-foreground/40 text-xs"
                      >
                        {number}
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
          </nav>
        </div>
      </aside>
    </>
  );
}

function questionNumbers(total: number): number[] {
  return Array.from({ length: total }, (_, i) => i + 1);
}
