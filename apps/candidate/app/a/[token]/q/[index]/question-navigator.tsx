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
          className="rounded-l border border-r-0 border-emerald-900/60 bg-emerald-950/80 px-1 py-3 text-emerald-300/70 text-xs hover:bg-emerald-950"
          onClick={() => setOpen((v) => !v)}
          type="button"
        >
          {open ? "›" : "‹"}
        </button>
        <nav className="rounded-l border border-emerald-900/60 bg-emerald-950/60 p-3 backdrop-blur">
          <p className="mb-2 text-emerald-300/60 text-xs uppercase tracking-wide">
            Questions
          </p>
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
                          ? "bg-emerald-500 font-medium text-emerald-950"
                          : "bg-emerald-900/60 text-emerald-100 hover:bg-emerald-900"
                      }`}
                      href={`/a/${token}/q/${i}`}
                    >
                      {i + 1}
                    </a>
                  ) : (
                    <span
                      aria-disabled
                      className="block w-8 cursor-not-allowed rounded bg-emerald-950/40 px-2 py-1 text-center font-mono text-emerald-300/30 text-xs"
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
