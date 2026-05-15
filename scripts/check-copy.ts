import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = process.cwd();

// Broadened scope: scan the entire repo for em / en dashes except for
// directories that hold third-party content, build artifacts, vendored
// templates we do not author, or generated changelogs.
const EXCLUDED_DIRS = new Set([
  "node_modules",
  ".next",
  ".turbo",
  ".git",
  "dist",
  ".venv",
  ".react-email",
  "build",
  ".cache",
  "generated",
  ".vercel",
  "coverage",
  "docs",
  "skills",
]);

// File names to skip even when they live in an otherwise scanned directory.
const EXCLUDED_FILES = new Set([
  "CHANGELOG.md",
  "bun.lock",
  "package-lock.json",
  "yarn.lock",
  "pnpm-lock.yaml",
]);

const EXTENSIONS = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".md",
  ".mdx",
  ".json",
  ".jsonc",
  ".yml",
  ".yaml",
  ".toml",
  ".sh",
  ".py",
  ".sql",
  ".env",
  ".example",
  ".html",
  ".css",
]);

const DASH_RE = /[—–]/g;

function extname(path: string): string {
  const idx = path.lastIndexOf(".");
  return idx === -1 ? "" : path.slice(idx);
}

function shouldScan(path: string, name: string): boolean {
  if (EXCLUDED_FILES.has(name)) {
    return false;
  }
  if (name.endsWith(".env.local") || name === ".env" || name === ".env.local") {
    // Local secrets file. Never tracked, never scanned.
    return false;
  }
  if (name === ".env.example" || name.endsWith(".env.example")) {
    return true;
  }
  const ext = extname(path);
  return EXTENSIONS.has(ext);
}

function walk(dir: string, out: string[] = []): string[] {
  let entries: ReturnType<typeof readdirSync>;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }

  for (const entry of entries) {
    if (EXCLUDED_DIRS.has(entry.name)) {
      continue;
    }
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(path, out);
    } else if (entry.isFile() && shouldScan(path, entry.name)) {
      out.push(path);
    }
  }
  return out;
}

const violations: Array<{ file: string; line: number; text: string }> = [];

const scanRoot = ROOT;
try {
  if (!statSync(scanRoot).isDirectory()) {
    console.error(`Copy check: ${scanRoot} is not a directory.`);
    process.exit(2);
  }
} catch {
  console.error(`Copy check: cannot stat ${scanRoot}.`);
  process.exit(2);
}

// Skip this script itself: the dash characters appear inside the
// regex literal and would self-flag. Matched by relative path so it
// works under ESM where __filename is not defined.
const SELF_REL = "scripts/check-copy.ts";

for (const file of walk(scanRoot)) {
  const rel = relative(ROOT, file);
  if (rel === SELF_REL) {
    continue;
  }
  const lines = readFileSync(file, "utf8").split(/\r?\n/);
  lines.forEach((line, i) => {
    if (DASH_RE.test(line)) {
      violations.push({
        file: rel,
        line: i + 1,
        text: line.trim(),
      });
    }
    DASH_RE.lastIndex = 0;
  });
}

if (violations.length > 0) {
  console.error(
    "Copy check failed: replace em dashes and en dashes with hyphens, commas, or parentheses."
  );
  for (const v of violations) {
    console.error(`${v.file}:${v.line}: ${v.text}`);
  }
  process.exit(1);
}

console.log("Copy check passed.");
