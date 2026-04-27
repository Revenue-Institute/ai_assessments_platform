"use client";

import { useEffect, useState } from "react";

/** Live countdown driven by the server's expires_at — the timer is a
 * display only; deadline enforcement happens server-side per spec §10.1.
 *
 * Accessibility: the visible countdown is `aria-hidden` so it doesn't
 * spam screen readers every second. A separate `aria-live="polite"`
 * region announces remaining time only on minute boundaries above 5 min,
 * every 30 s under 5 min, and on each second in the final minute, plus
 * an `aria-live="assertive"` announcement when the deadline elapses. */
export function CountdownTimer({ deadlineIso }: { deadlineIso: string }) {
  const deadline = new Date(deadlineIso).getTime();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const remainingMs = Math.max(0, deadline - now);
  const totalSeconds = Math.floor(remainingMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const expired = remainingMs === 0;

  const tone = expired
    ? "border-destructive/60 bg-destructive/15 text-destructive"
    : minutes < 5
      ? "border-warning/60 bg-warning/15 text-warning"
      : "border-primary/40 bg-primary/10 text-primary";

  // Quantize for the screen-reader announcement. Above 5 min: announce
  // each whole minute. Under 5 min: announce every 30 s. Final minute:
  // announce each second. This avoids per-second SR spam while keeping
  // candidates informed as time gets tight.
  let spokenLabel: string | null = null;
  if (expired) {
    spokenLabel = "Time has expired";
  } else if (minutes >= 5 && seconds === 0) {
    spokenLabel = `${minutes} minutes remaining`;
  } else if (minutes >= 1 && minutes < 5 && seconds % 30 === 0) {
    spokenLabel = `${minutes} minutes ${seconds} seconds remaining`;
  } else if (minutes === 0) {
    spokenLabel = `${seconds} seconds remaining`;
  }

  const visible = expired
    ? "00:00 — time up"
    : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")} left`;

  return (
    // Wrap both elements so the parent flex container sees a single
    // child — fragmenting them would split the timer into two flex items
    // and break the question header's justify-between layout.
    <span className="inline-flex">
      <span
        aria-hidden="true"
        className={`whitespace-nowrap rounded border px-2 py-1 font-mono text-xs tabular-nums ${tone}`}
      >
        {visible}
      </span>
      <span
        aria-live={expired || minutes === 0 ? "assertive" : "polite"}
        className="sr-only"
      >
        {spokenLabel ?? ""}
      </span>
    </span>
  );
}
