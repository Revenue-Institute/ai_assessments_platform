#!/usr/bin/env bash
# Single source of truth for env vars: one .env.local at the repo root,
# symlinked into each app's directory so Next.js + FastAPI both pick it
# up via their normal lookup rules.
#
# Run once after cloning:
#   cp .env.example .env.local         # fill in your values
#   bash scripts/link-env.sh
#
# Idempotent: re-running replaces existing symlinks, leaves real files
# in place, and prints what it did.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

if [[ ! -f .env.local ]]; then
  echo "error: $repo_root/.env.local does not exist." >&2
  echo "       cp .env.example .env.local and fill in your values first." >&2
  exit 2
fi

link_file() {
  local link_path="$1"
  local target_dir
  target_dir="$(dirname "$link_path")"

  if [[ ! -d "$target_dir" ]]; then
    echo "skip: $target_dir (not present)"
    return
  fi

  if [[ -L "$link_path" ]]; then
    rm "$link_path"
  elif [[ -e "$link_path" ]]; then
    echo "warn: $link_path is a real file, not a symlink, leaving it alone." >&2
    echo "      Move it aside if you want this script to manage it." >&2
    return
  fi

  ln -s "../../.env.local" "$link_path"
  echo "linked: $link_path -> ../../.env.local"
}

link_file apps/admin/.env.local
link_file apps/candidate/.env.local

# FastAPI in docker reads the env_file declared in docker-compose.yml,
# which points at apps/api/.env.local. FastAPI run directly via
# uvicorn (local dev outside docker) uses pydantic-settings which
# reads .env by default. Symlink both names at the same target so
# both code paths work without copy-pasting values.
link_file apps/api/.env.local
link_file apps/api/.env

echo
echo "Done. Edit /.env.local; all three apps will see your changes."
