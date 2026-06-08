"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface ScoringEvent {
  assignment_id: string;
  type: "scoring_queued" | "scoring_completed" | "scoring_failed";
}

type ScoringPhase = "idle" | "queued" | "completed" | "failed";

function toneFor(phase: ScoringPhase): string {
  if (phase === "failed") {
    return "bg-destructive/15 text-destructive";
  }
  if (phase === "completed") {
    return "bg-primary/15 text-primary";
  }
  return "bg-muted text-muted-foreground";
}

// Listens to the SSE scoring stream and calls router.refresh() when the score lands; shows a live badge during queued/failed states.
export function ScoringListener({ assignmentId }: { assignmentId: string }) {
  const router = useRouter();
  const [phase, setPhase] = useState<ScoringPhase>("idle");

  useEffect(() => {
    const url = `/api/scoring-events?assignment_id=${encodeURIComponent(assignmentId)}`;
    const source = new EventSource(url);
    source.addEventListener("scoring", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as ScoringEvent;
        if (data.assignment_id !== assignmentId) {
          return;
        }
        if (data.type === "scoring_queued") {
          setPhase("queued");
        } else if (data.type === "scoring_completed") {
          setPhase("completed");
          router.refresh();
        } else if (data.type === "scoring_failed") {
          setPhase("failed");
          router.refresh();
        }
      } catch {
        // Malformed payload; skip.
      }
    });
    return () => source.close();
  }, [assignmentId, router]);

  if (phase === "idle") {
    return null;
  }
  const labels: Record<ScoringPhase, string> = {
    idle: "",
    queued: "Scoring...",
    completed: "Score updated",
    failed: "Scoring failed",
  };
  return (
    <span
      aria-live="polite"
      className={`inline-flex items-center rounded px-2 py-0.5 font-medium text-[11px] uppercase tracking-wide ${toneFor(phase)}`}
    >
      {labels[phase]}
    </span>
  );
}
