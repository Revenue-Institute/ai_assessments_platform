"use client";

import { useEffect, useMemo, useState } from "react";

/** Live countdown driven by the server's expires_at. The timer is a
 * display only; deadline enforcement happens server-side per spec §10.1.
 *
 * Accessibility: the visible countdown is `aria-hidden` so it doesn't
 * spam screen readers every second. A separate `aria-live="polite"`
 * region announces remaining time only on minute boundaries above 5 min,
 * every 30 s under 5 min, and on each second in the final minute, plus
 * an `aria-live="assertive"` announcement when the deadline elapses. */
export function CountdownTimer({ deadlineIso }: { deadlineIso: string }) {
  const deadline = useMemo(
    () => new Date(deadlineIso).getTime(),
    [deadlineIso]
  );
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Before hydration, defer rendering to avoid server/client mismatch.
  if (now === null) {
    return (
      <span className="inline-flex">
        <span
          aria-hidden="true"
          className="whitespace-nowrap rounded border border-primary/40 bg-primary/10 px-2 py-1 font-mono text-primary text-xs tabular-nums"
        >
          --:--
        </span>
        <span aria-live="polite" className="sr-only" />
      </span>
    );
  }

  const remainingMs = Math.max(0, deadline - now);
  const totalSeconds = Math.floor(remainingMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const expired = remainingMs === 0;

  let tone = "border-primary/40 bg-primary/10 text-primary";
  if (expired) {
    tone = "border-destructive/60 bg-destructive/15 text-destructive";
  } else if (minutes < 5) {
    tone = "border-warning/60 bg-warning/15 text-warning";
  }

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
    ? "00:00 time up"
    : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")} left`;

  return (
    // Wrap both elements so the parent flex container sees a single
    // child, since fragmenting them would split into two flex items
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
