"use client";

import { useEffect, useState } from "react";

/** Live countdown driven by the server's expires_at — the timer is a
 * display only; deadline enforcement happens server-side per spec §10.1. */
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
    ? "border-red-900/60 bg-red-950/40 text-red-200"
    : minutes < 5
      ? "border-amber-900/60 bg-amber-950/40 text-amber-200"
      : "border-emerald-900/60 bg-emerald-950/40 text-emerald-200";

  return (
    <p
      aria-live="polite"
      aria-label={
        expired
          ? "Time has expired"
          : `${minutes} minutes and ${seconds} seconds remaining`
      }
      className={`rounded border px-2 py-1 font-mono text-xs tabular-nums ${tone}`}
    >
      {expired
        ? "00:00 — time up"
        : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")} left`}
    </p>
  );
}
