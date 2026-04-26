#!/usr/bin/env bash
# Bootstraps a Supabase project for the Revenue Institute Assessments
# Platform. Idempotent: safe to re-run.
#
# Prereqs:
#   - Supabase CLI installed (https://supabase.com/docs/guides/cli)
#   - You've created a Supabase project at https://supabase.com/dashboard
#   - You have the project's database password handy
#
# Usage:
#   SUPABASE_PROJECT_REF=abcd1234 bash scripts/setup-supabase.sh
#
# What this does:
#   1. Links the local repo to the Supabase project.
#   2. Enables the pgvector + pgcrypto extensions.
#   3. Pushes packages/db/migrations/*.sql via the Supabase CLI.
#   4. Prints the URLs and keys you need for .env.
set -euo pipefail

if ! command -v supabase >/dev/null 2>&1; then
  echo "error: supabase CLI not found. Install with brew install supabase/tap/supabase" >&2
  exit 2
fi

if [[ -z "${SUPABASE_PROJECT_REF:-}" ]]; then
  echo "error: SUPABASE_PROJECT_REF is required (the slug from your dashboard URL)." >&2
  exit 2
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

echo "==> Linking project $SUPABASE_PROJECT_REF"
supabase link --project-ref "$SUPABASE_PROJECT_REF"

# Supabase CLI's `db push` reads from supabase/migrations by default. We
# keep ours under packages/db/migrations to match the monorepo shape, so
# materialize a symlink for the CLI's benefit.
mkdir -p supabase
if [[ ! -e supabase/migrations ]]; then
  ln -s ../packages/db/migrations supabase/migrations
fi
if [[ ! -f supabase/config.toml ]]; then
  cat > supabase/config.toml <<'TOML'
project_id = "ri-assessments"

[db]
major_version = 15

[api]
enabled = true
TOML
fi

echo "==> Enabling extensions"
supabase db query --linked <<'SQL'
create extension if not exists "pgcrypto";
create extension if not exists "vector";
SQL

echo "==> Pushing migrations"
supabase db push

echo
echo "==> Done. Variables to add to .env:"
echo
echo "  SUPABASE_URL=https://${SUPABASE_PROJECT_REF}.supabase.co"
echo "  NEXT_PUBLIC_SUPABASE_URL=https://${SUPABASE_PROJECT_REF}.supabase.co"
echo "  DATABASE_URL=<grab from Settings → Database → Connection string → URI>"
echo
echo "  Get the API keys from Settings → API:"
echo "    NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon public key>"
echo "    SUPABASE_SERVICE_ROLE_KEY=<service_role secret key>"
echo "    SUPABASE_JWT_SECRET=<JWT secret>"
echo
echo "Then run: bash scripts/check-env.sh all"
