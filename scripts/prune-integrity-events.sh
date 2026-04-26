#!/usr/bin/env bash
# Spec §11.4: prune attempt_events older than 12 months.
#
# Usage:
#   bash scripts/prune-integrity-events.sh                # 365-day default
#   RETENTION_DAYS=180 bash scripts/prune-integrity-events.sh
#
# Wire this into Cloud Scheduler (or any cron) to run weekly. Requires
# DATABASE_URL or the Supabase CLI to be linked locally.

set -euo pipefail

DAYS="${RETENTION_DAYS:-365}"

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "==> Pruning attempt_events older than ${DAYS} days via DATABASE_URL"
  psql "$DATABASE_URL" -c \
    "select deleted_count from prune_integrity_events(${DAYS});"
  exit 0
fi

if command -v supabase >/dev/null 2>&1; then
  echo "==> Pruning attempt_events older than ${DAYS} days via Supabase CLI"
  supabase db query --linked <<SQL
select deleted_count from prune_integrity_events(${DAYS});
SQL
  exit 0
fi

echo "error: neither DATABASE_URL nor the supabase CLI is available." >&2
exit 2
