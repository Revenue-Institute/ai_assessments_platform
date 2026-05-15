import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = process.cwd();
const EXTENSIONS = new Set([".ts", ".tsx"]);
const IMPORT_RE =
  /(?:import|export)\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?["']([^"']+)["']/g;

function extname(path: string): string {
  const idx = path.lastIndexOf(".");
  return idx === -1 ? "" : path.slice(idx);
}

function walk(dir: string, out: string[] = []): string[] {
  let entries: ReturnType<typeof readdirSync>;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    if (
      entry.name === "node_modules" ||
      entry.name === ".next" ||
      entry.name === "dist"
    ) {
      continue;
    }
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(path, out);
    } else if (entry.isFile() && EXTENSIONS.has(extname(path))) {
      out.push(path);
    }
  }
  return out;
}

const violations: string[] = [];

for (const file of walk(join(ROOT, "packages"))) {
  const source = readFileSync(file, "utf8");
  for (const match of source.matchAll(IMPORT_RE)) {
    const specifier = match[1];
    if (
      specifier.startsWith("@/") ||
      specifier.startsWith("apps/") ||
      specifier.includes("/apps/")
    ) {
      violations.push(`${relative(ROOT, file)} imports ${specifier}`);
    }
  }
}

const schemaFiles = walk(join(ROOT, "packages/schemas/src"));
for (const file of schemaFiles) {
  const source = readFileSync(file, "utf8");
  for (const match of source.matchAll(IMPORT_RE)) {
    const specifier = match[1];
    if (!specifier.startsWith(".") && specifier !== "zod") {
      violations.push(
        `${relative(ROOT, file)} imports ${specifier}; packages/schemas may only depend on zod and local files`
      );
    }
  }
}

try {
  statSync(join(ROOT, "packages/database"));
  violations.push("packages/database exists; this repo uses packages/db.");
} catch {
  // Good: the stale next-forge package name is absent.
}

if (violations.length > 0) {
  console.error("Boundary check failed:");
  for (const violation of violations) {
    console.error(`  - ${violation}`);
  }
  process.exit(1);
}

console.log("Boundary check passed.");
