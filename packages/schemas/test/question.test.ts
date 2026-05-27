import { describe, expect, it } from "vitest";
import {
  McqConfig,
  MultiSelectConfig,
  QuestionTemplate,
  Rubric,
  VariableSpec,
} from "../src/index";

function baseRubric() {
  return {
    version: "1",
    scoring_mode: "rubric_ai" as const,
    criteria: [
      {
        id: "c1",
        label: "Accuracy",
        weight: 1,
        description: "Captures the right answer.",
        scoring_guidance: "Full marks for a complete, correct response.",
      },
    ],
  };
}

function baseQuestion() {
  return {
    type: "short_answer" as const,
    prompt_template: "What is 2 + {{ n }}?",
    variable_schema: {
      n: { kind: "int" as const, min: 1, max: 5, step: 1 },
    },
    rubric: baseRubric(),
    competency_tags: ["data.python_analysis"],
    max_points: 10,
    difficulty: "junior" as const,
  };
}

describe("QuestionTemplate", () => {
  it("parses a valid input", () => {
    const parsed = QuestionTemplate.parse(baseQuestion());
    expect(parsed.type).toBe("short_answer");
    expect(parsed.competency_tags).toEqual(["data.python_analysis"]);
  });

  it("rejects empty competency_tags", () => {
    const bad = { ...baseQuestion(), competency_tags: [] };
    expect(() => QuestionTemplate.parse(bad)).toThrow();
  });

  it("rejects Rubric.criteria empty array", () => {
    const bad = {
      ...baseQuestion(),
      rubric: { ...baseRubric(), criteria: [] },
    };
    expect(() => QuestionTemplate.parse(bad)).toThrow();
    expect(() => Rubric.parse({ ...baseRubric(), criteria: [] })).toThrow();
  });

  it("rejects max_points greater than 100", () => {
    const bad = { ...baseQuestion(), max_points: 101 };
    expect(() => QuestionTemplate.parse(bad)).toThrow();
  });

  it("rejects time_limit_seconds below 30", () => {
    const bad = { ...baseQuestion(), time_limit_seconds: 29 };
    expect(() => QuestionTemplate.parse(bad)).toThrow();
  });

  it("rejects time_limit_seconds above 1800", () => {
    const bad = { ...baseQuestion(), time_limit_seconds: 1801 };
    expect(() => QuestionTemplate.parse(bad)).toThrow();
  });
});

describe("VariableSpec int", () => {
  it("rejects min greater than max", () => {
    expect(() =>
      VariableSpec.parse({ kind: "int", min: 10, max: 5, step: 1 })
    ).toThrow();
  });

  it("rejects step <= 0", () => {
    expect(() =>
      VariableSpec.parse({ kind: "int", min: 1, max: 5, step: 0 })
    ).toThrow();
    expect(() =>
      VariableSpec.parse({ kind: "int", min: 1, max: 5, step: -1 })
    ).toThrow();
  });

  it("accepts a well-formed int spec", () => {
    const ok = VariableSpec.parse({ kind: "int", min: 1, max: 10, step: 2 });
    expect(ok.kind).toBe("int");
  });
});

describe("McqConfig", () => {
  it("requires options length >= 2", () => {
    expect(() =>
      McqConfig.parse({ options: ["only"], correct_index: 0 })
    ).toThrow();
    expect(() => McqConfig.parse({ options: [], correct_index: 0 })).toThrow();
  });

  it("parses with two options", () => {
    const ok = McqConfig.parse({
      options: ["a", "b"],
      correct_index: 1,
    });
    expect(ok.options).toHaveLength(2);
  });
});

describe("MultiSelectConfig", () => {
  it("requires correct_indices to be non-empty", () => {
    expect(() =>
      MultiSelectConfig.parse({
        options: ["a", "b", "c"],
        correct_indices: [],
      })
    ).toThrow();
  });

  it("parses with at least one correct index", () => {
    const ok = MultiSelectConfig.parse({
      options: ["a", "b", "c"],
      correct_indices: [0, 2],
    });
    expect(ok.correct_indices).toEqual([0, 2]);
  });
});
