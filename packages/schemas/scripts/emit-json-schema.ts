#!/usr/bin/env bun
// Emits one JSON Schema file per Zod schema in @repo/schemas to the path
// given as argv[2] (default: "./schemas-out"). Used by
// apps/api/scripts/gen_schemas.py as the first step of the Zod -> Pydantic
// codegen pipeline (spec §5).

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { z } from "zod";
import * as schemas from "../src/index.js";

const outDir = resolve(process.argv[2] ?? "./schemas-out");
mkdirSync(outDir, { recursive: true });

let written = 0;
for (const [name, value] of Object.entries(schemas)) {
  if (!(value instanceof z.ZodType)) continue;
  const json = z.toJSONSchema(value, { target: "draft-7" });
  // datamodel-code-generator wants a top-level title for the model name.
  const withTitle = { title: name, ...(json as Record<string, unknown>) };
  const path = resolve(outDir, `${name}.json`);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(withTitle, null, 2)}\n`);
  written++;
}

console.log(`emit-json-schema: wrote ${written} schemas to ${outDir}`);
