#!/usr/bin/env bash
# Convenience wrapper for the Zod -> Pydantic codegen pipeline. Resolves
# the repo root, ensures bun deps are present, then runs gen_schemas.py
# inside the apps/api uv environment.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$repo_root"

if [[ ! -d packages/schemas/node_modules ]]; then
  echo "==> Installing packages/schemas deps with bun"
  bun install --filter @repo/schemas
fi

cd "$repo_root/apps/api"
uv run python scripts/gen_schemas.py "$@"
