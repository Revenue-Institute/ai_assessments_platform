#!/usr/bin/env bash
# One-shot local dev: validates env, ensures symlinks are in place, then
# starts all three services (api on :8000, admin on :3000, candidate on
# :3001) via turbo. Use after editing .env.local.
#
#   bash scripts/dev-all.sh
# or via the package.json alias:
#   bun run dev:full

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

# 1. Confirm the source-of-truth env file exists.
if [[ ! -f .env.local ]]; then
  cat <<EOF >&2
error: $repo_root/.env.local does not exist.

  Run:
    cp .env.example .env.local
    # fill in your Supabase / Anthropic / E2B / Resend keys
    bash scripts/link-env.sh

EOF
  exit 2
fi

# 2. Re-run the symlink wiring. Idempotent — replaces stale links,
# leaves real files alone, prints what it did.
bash scripts/link-env.sh

# 3. Preflight env validation. Warnings don't block dev; missing
# REQUIRED keys do.
if ! bash scripts/check-env.sh all; then
  echo
  echo "error: required env vars missing. Edit .env.local and re-run." >&2
  exit 1
fi

# 4. Confirm uv + bun are available — turbo dev will surface the same
# error eventually but a precheck is friendlier.
for bin in bun uv; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "error: '$bin' not found in PATH. Install before running dev." >&2
    exit 2
  fi
done

# 5. Hand off to turbo. `dev` is configured persistent + non-cached in
# turbo.json; output goes to a TUI so the three streams are tabbed.
echo
echo "==> Starting api (:8000) · admin (:3000) · candidate (:3001)"
echo
exec turbo dev
