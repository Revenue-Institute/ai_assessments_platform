import type { IntegrityEventType } from "@repo/schemas";
import { describe, expect, it } from "vitest";
import { computeIntegrityScore } from "../src/score";
import fixtureFile from "./fixtures.json" with { type: "json" };

interface RawEvent {
  event_type: string;
  payload?: { allowed?: boolean };
}

interface Fixture {
  active_time_seconds: number | null;
  events: RawEvent[];
  expected_score: number;
  name: string;
  total_time_seconds: number | null;
}

const fixtures = fixtureFile.fixtures as Fixture[];

function adapt(events: RawEvent[]): {
  counts: Partial<Record<IntegrityEventType, number>>;
  pasteDisallowed: number;
} {
  const counts: Partial<Record<IntegrityEventType, number>> = {};
  let pasteDisallowed = 0;
  for (const e of events) {
    const key = e.event_type as IntegrityEventType;
    counts[key] = (counts[key] ?? 0) + 1;
    if (e.event_type === "paste_attempted" && e.payload?.allowed === false) {
      pasteDisallowed += 1;
    }
  }
  return { counts, pasteDisallowed };
}

describe("computeIntegrityScore parity", () => {
  for (const fx of fixtures) {
    it(fx.name, () => {
      const { counts, pasteDisallowed } = adapt(fx.events);
      const score = computeIntegrityScore({
        active_time_seconds: fx.active_time_seconds,
        events: counts,
        paste_attempted_disallowed: pasteDisallowed,
        total_time_seconds: fx.total_time_seconds ?? 0,
      });
      expect(score).toBe(fx.expected_score);
    });
  }
});
