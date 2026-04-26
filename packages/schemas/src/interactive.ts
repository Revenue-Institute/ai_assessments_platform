import { z } from "zod";

export const CodeConfig = z.object({
  language: z.enum(["python", "javascript", "typescript", "sql", "bash"]),
  starter_code: z.string(),
  hidden_tests: z.string(),
  visible_tests: z.string().optional(),
  allow_internet: z.boolean().default(false),
  packages: z.array(z.string()).default([]),
  time_limit_exec_ms: z.number().default(10000),
});
export type CodeConfig = z.infer<typeof CodeConfig>;

export const N8nConfig = z.object({
  mode: z.enum(["build", "fix"]),
  starter_workflow: z.any(),
  reference_workflow: z.any(),
  required_nodes: z.array(z.string()),
  required_connections: z.array(
    z.object({ from: z.string(), to: z.string() })
  ),
  test_payloads: z.array(z.any()),
  credentials_provided: z.array(z.string()),
});
export type N8nConfig = z.infer<typeof N8nConfig>;

export const NotebookConfig = z.object({
  starter_notebook: z.any(),
  dataset_urls: z.array(z.string()),
  validation_script: z.string(),
  required_outputs: z.array(z.string()),
});
export type NotebookConfig = z.infer<typeof NotebookConfig>;

export const DiagramConfig = z.object({
  mode: z.enum(["build", "analyze"]),
  starter_nodes: z.array(z.any()),
  reference_structure: z.any(),
  grading_mode: z.enum(["structural", "ai_narrative", "both"]),
});
export type DiagramConfig = z.infer<typeof DiagramConfig>;

export const SqlConfig = z.object({
  schema_sql: z.string(),
  seed_sql: z.string(),
  expected_query_result: z.any().optional(),
  expected_sql_patterns: z.array(z.string()).optional(),
});
export type SqlConfig = z.infer<typeof SqlConfig>;
