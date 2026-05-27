import { describe, expect, it } from "vitest";
import {
  parseCodeConfig,
  parseDiagramConfig,
  parseMcqConfig,
  parseMultiSelectConfig,
  parseN8nConfig,
  parseNotebookConfig,
  parseSqlConfig,
} from "../src/index.js";

describe("interactive-helpers lax parsers", () => {
  it("returns an empty object for non-object input", () => {
    expect(parseCodeConfig(null)).toEqual({});
    expect(parseCodeConfig(undefined)).toEqual({});
    expect(parseCodeConfig("oops")).toEqual({});
    expect(parseCodeConfig(42)).toEqual({});
  });

  it("McqConfig: keeps valid fields and drops invalid ones", () => {
    const out = parseMcqConfig({
      options: ["A", "B", "C"],
      correct_index: 1,
      unknown_extra: "ignored",
    });
    expect(out).toEqual({ options: ["A", "B", "C"], correct_index: 1 });

    const partial = parseMcqConfig({ options: ["A"], correct_index: "nope" });
    // options fails (min 2), correct_index fails (string not int).
    expect(partial).toEqual({});
  });

  it("MultiSelectConfig: round-trips the typical happy path", () => {
    const out = parseMultiSelectConfig({
      options: ["A", "B", "C"],
      correct_indices: [0, 2],
    });
    expect(out).toEqual({ options: ["A", "B", "C"], correct_indices: [0, 2] });
  });

  it("CodeConfig: per-field laxness", () => {
    const out = parseCodeConfig({
      language: "python",
      starter_code: "print('hi')",
      hidden_tests: "assert True",
      packages: ["numpy"],
      time_limit_exec_ms: 5000,
      extra: 42,
    });
    expect(out.language).toBe("python");
    expect(out.starter_code).toBe("print('hi')");
    expect(out.hidden_tests).toBe("assert True");
    expect(out.packages).toEqual(["numpy"]);
    expect(out.time_limit_exec_ms).toBe(5000);
  });

  it("CodeConfig: drops fields with wrong types", () => {
    const out = parseCodeConfig({
      language: "scala", // not in enum
      starter_code: 42, // not a string
      hidden_tests: "assert True",
    });
    expect(out.language).toBeUndefined();
    expect(out.starter_code).toBeUndefined();
    expect(out.hidden_tests).toBe("assert True");
  });

  it("SqlConfig: keeps optional expected fields when present", () => {
    const out = parseSqlConfig({
      schema_sql: "create table t (...)",
      seed_sql: "insert into t ...",
      expected_query_result: { rows: [] },
      expected_sql_patterns: ["select.*from"],
    });
    expect(out.schema_sql).toBe("create table t (...)");
    expect(out.expected_query_result).toEqual({ rows: [] });
    expect(out.expected_sql_patterns).toEqual(["select.*from"]);
  });

  it("NotebookConfig: dataset_urls + required_outputs", () => {
    const out = parseNotebookConfig({
      starter_notebook: { cells: [] },
      dataset_urls: ["s3://bucket/x.csv"],
      validation_script: "import pandas",
      required_outputs: ["accuracy"],
    });
    expect(out.dataset_urls).toEqual(["s3://bucket/x.csv"]);
    expect(out.required_outputs).toEqual(["accuracy"]);
  });

  it("N8nConfig: discards malformed required_connections entries", () => {
    const out = parseN8nConfig({
      mode: "build",
      starter_workflow: { nodes: [] },
      reference_workflow: { nodes: [] },
      required_nodes: ["webhook"],
      required_connections: [{ from: "a", to: "b" }],
      test_payloads: [],
      credentials_provided: [],
    });
    expect(out.mode).toBe("build");
    expect(out.required_connections).toEqual([{ from: "a", to: "b" }]);
  });

  it("DiagramConfig: enum gating on grading_mode", () => {
    const valid = parseDiagramConfig({
      mode: "build",
      starter_nodes: [],
      reference_structure: {},
      grading_mode: "structural",
    });
    expect(valid.grading_mode).toBe("structural");

    const invalid = parseDiagramConfig({
      mode: "build",
      starter_nodes: [],
      reference_structure: {},
      grading_mode: "vibes_based",
    });
    expect(invalid.grading_mode).toBeUndefined();
    expect(invalid.mode).toBe("build");
  });
});
