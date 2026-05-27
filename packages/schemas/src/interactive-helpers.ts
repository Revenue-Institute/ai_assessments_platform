// Lax parsers for interactive_config blobs.
//
// The admin form and the AI generator both produce
// `question.interactive_config` payloads that are *meant* to satisfy
// the strict Zod schemas in `./interactive.ts`, but practice shows
// partial / extra fields in the wild (early-revision AI outputs,
// legacy modules, in-progress drafts). The candidate runtime and the
// admin preview both need to render gracefully against that mess.
//
// The strict parsers (`McqConfig.parse(raw)` etc.) throw on the first
// missing field. These lax parsers return `Partial<T>` populated only
// with fields that round-trip through the strict schema's `.shape`
// validators. Missing or invalid fields are simply absent from the
// returned object - callers keep their existing `?? fallback` patterns.
//
// Centralizing this means a new required field on the Zod side surfaces
// the same way in both renderers instead of drifting independently
// (the bug class flagged in the 2026-05-26 architecture audit).
//
// Tests in `test/interactive-helpers.test.ts` lock the lax-parse
// behavior so renderers can rely on it.

import { z } from "zod";
import {
  CodeConfig,
  DiagramConfig,
  McqConfig,
  MultiSelectConfig,
  N8nConfig,
  NotebookConfig,
  SqlConfig,
} from "./interactive.js";

function laxParse<T extends z.ZodObject<z.ZodRawShape>>(
  schema: T,
  raw: unknown
): Partial<z.infer<T>> {
  if (raw === null || typeof raw !== "object") {
    return {};
  }
  const out: Record<string, unknown> = {};
  const source = raw as Record<string, unknown>;
  for (const key of Object.keys(schema.shape)) {
    if (!(key in source)) {
      continue;
    }
    // Zod v4's $ZodType type doesn't expose .safeParse at the type
    // level; cast through ZodType which does. Behavior is identical.
    const fieldSchema = schema.shape[key] as z.ZodType;
    const parsed = fieldSchema.safeParse(source[key]);
    if (parsed.success) {
      out[key] = parsed.data;
    }
  }
  return out as Partial<z.infer<T>>;
}

export function parseMcqConfig(raw: unknown): Partial<z.infer<typeof McqConfig>> {
  return laxParse(McqConfig, raw);
}

export function parseMultiSelectConfig(
  raw: unknown
): Partial<z.infer<typeof MultiSelectConfig>> {
  return laxParse(MultiSelectConfig, raw);
}

export function parseCodeConfig(
  raw: unknown
): Partial<z.infer<typeof CodeConfig>> {
  return laxParse(CodeConfig, raw);
}

export function parseSqlConfig(
  raw: unknown
): Partial<z.infer<typeof SqlConfig>> {
  return laxParse(SqlConfig, raw);
}

export function parseNotebookConfig(
  raw: unknown
): Partial<z.infer<typeof NotebookConfig>> {
  return laxParse(NotebookConfig, raw);
}

export function parseN8nConfig(
  raw: unknown
): Partial<z.infer<typeof N8nConfig>> {
  return laxParse(N8nConfig, raw);
}

export function parseDiagramConfig(
  raw: unknown
): Partial<z.infer<typeof DiagramConfig>> {
  return laxParse(DiagramConfig, raw);
}
