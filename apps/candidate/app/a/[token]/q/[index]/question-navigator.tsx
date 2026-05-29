"use client";

import { useEffect, useState } from "react";

interface Props {
  current: number;
  token: string;
  total: number;
}

function storageKey(token: string) {
  return `ri-hw-${token}`;
}

function syncHighwater(token: string, current: number): number {
  try {
    const stored = sessionStorage.getItem(storageKey(token));
    const prev = stored !== null ? Number(stored) : -1;
    const next = Math.max(prev, current);
    if (next > prev) {
      sessionStorage.setItem(storageKey(token), String(next));
    }
    return next;
  } catch {
    return current;
  }
}

/** Collapsible side panel that lets the candidate jump back to any
 * already-viewed question. Default forward-only: only renders links for
 * indices <= highwater, per spec §13.3 ("only forward navigation allowed
 * unless module config says otherwise").
 *
 * Tracks the highest question index ever visited in sessionStorage so that
 * navigating back to an earlier question does not disable forward links.
 *
 * Renders two surfaces driven off the same data:
 *   - mobile: a horizontal scroll strip pinned above the question.
 *   - md+   : a collapsible right-side rail.
 * Both use the visited/active gating so the forward-only contract holds
 * on every viewport. */
export function QuestionNavigator({ token, current, total }: Props) {
  const [open, setOpen] = useState(true);
  const [highwater, setHighwater] = useState(current);

  useEffect(() => {
    setHighwater(syncHighwater(token, current));
  }, [token, current]);

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
            const visited = index <= highwater;
            const active = index === current;
            return (
              <li className="shrink-0" key={`q-mobile-${number}`}>
                {visited ? (
                  <a
                    aria-current={active ? "step" : undefined}
                    className={`block min-w-9 rounded px-2 py-1 text-center font-mono text-xs ${
                      active
                        ? "bg-primary font-medium text-primary-foreground"
                        : "bg-secondary text-secondary-foreground hover:bg-primary/30"
                    }`}
                    href={`/a/${token}/q/${index}`}
                  >
                    {number}
                  </a>
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
                const visited = index <= highwater;
                const active = index === current;
                return (
                  <li key={`q-rail-${number}`}>
                    {visited ? (
                      <a
                        aria-current={active ? "step" : undefined}
                        className={`block w-8 rounded px-2 py-1 text-center font-mono text-xs ${
                          active
                            ? "bg-primary font-medium text-primary-foreground"
                            : "bg-secondary text-secondary-foreground hover:bg-primary/30"
                        }`}
                        href={`/a/${token}/q/${index}`}
                      >
                        {number}
                      </a>
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
  const numbers: number[] = [];
  for (let number = 1; number <= total; number++) {
    numbers.push(number);
  }
  return numbers;
}
