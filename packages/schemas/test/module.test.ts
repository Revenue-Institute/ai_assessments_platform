import { describe, expect, it } from "vitest";
import { Assessment, AssessmentStatus, Module } from "../src/index.js";

function validQuestion() {
  return {
    type: "short_answer" as const,
    prompt_template: "Explain the difference between A and B.",
    variable_schema: {},
    rubric: {
      version: "1",
      scoring_mode: "rubric_ai" as const,
      criteria: [
        {
          id: "c1",
          label: "Clarity",
          weight: 1,
          description: "Clear and accurate.",
          scoring_guidance: "Full marks for unambiguous answers.",
        },
      ],
    },
    competency_tags: ["ops.process_design"],
    max_points: 10,
    difficulty: "mid" as const,
  };
}

describe("Module", () => {
  it("rejects an empty questions array", () => {
    expect(() =>
      Module.parse({
        slug: "ops-101",
        title: "Ops 101",
        description: "Intro",
        domain: "ops",
        target_duration_minutes: 30,
        difficulty: "junior",
        questions: [],
      })
    ).toThrow();
  });

  it("accepts a module with at least one question", () => {
    const ok = Module.parse({
      slug: "ops-101",
      title: "Ops 101",
      description: "Intro",
      domain: "ops",
      target_duration_minutes: 30,
      difficulty: "mid",
      questions: [validQuestion()],
    });
    expect(ok.questions).toHaveLength(1);
  });
});

describe("Assessment", () => {
  it("parses with valid module entries", () => {
    const parsed = Assessment.parse({
      slug: "marketing-bench",
      title: "Marketing Benchmark",
      modules: [
        { module_id: "0e1d4b48-9e1a-4f3d-9c4b-1b1f1a2b3c4d", position: 1 },
        { module_id: "9d6c1f5a-3b2e-4a5f-8c7d-2e3f4a5b6c7d", position: 2 },
      ],
    });
    expect(parsed.modules).toHaveLength(2);
    expect(parsed.modules[0]?.position).toBe(1);
  });

  it("defaults modules to an empty array when omitted", () => {
    const parsed = Assessment.parse({
      slug: "empty",
      title: "Empty assessment",
    });
    expect(parsed.modules).toEqual([]);
  });

  it("rejects module entries with a non-uuid module_id", () => {
    expect(() =>
      Assessment.parse({
        slug: "bad",
        title: "Bad",
        modules: [{ module_id: "not-a-uuid", position: 1 }],
      })
    ).toThrow();
  });
});

describe("AssessmentStatus", () => {
  it("exposes the canonical enum members", () => {
    expect(AssessmentStatus.options).toEqual([
      "draft",
      "published",
      "archived",
    ]);
  });

  it("parses each member", () => {
    expect(AssessmentStatus.parse("draft")).toBe("draft");
    expect(AssessmentStatus.parse("published")).toBe("published");
    expect(AssessmentStatus.parse("archived")).toBe("archived");
  });

  it("rejects values outside the enum", () => {
    expect(() => AssessmentStatus.parse("unpublished")).toThrow();
  });
});
