#!/usr/bin/env bash
# On-VM deploy script invoked by .github/workflows/deploy-vm.yml after the
# Actions runner has pushed images to GHCR. The script lives at
# /srv/ai_assessments_platform/infra/deploy/deploy.sh on the VM and is
# kept in sync via the same `git pull` the workflow runs.
#
# Compose project name is locked to `ri-assessments` so this can never
# accidentally reach the box's other stacks (airbyte, prod n8n, neo4j).
#
# Env contract:
#   IMAGE_TAG  - image tag to deploy (defaults to "latest"; Actions sets to git SHA).
#
# Exit codes:
#   0  - success
#   1  - prerequisite missing (docker, .env.local, etc.)
#   2  - migration apply failed
#   3  - image pull failed
#   4  - health check failed after rollout

set -euo pipefail

cd "$(dirname "$0")/../.."

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not installed on this host." >&2
  exit 1
fi

if [[ ! -f .env.local ]]; then
  echo "ERROR: /srv/ai_assessments_platform/.env.local is missing." >&2
  echo "Populate it with production secrets before deploying." >&2
  exit 1
fi

# GitHub silently expands missing ${{ secrets.X }} / ${{ vars.X }} to "",
# producing empty lines in .env.local that survive into containers. This
# bit us on 2026-05-16 (admin Next.js crash-looped on an empty
# NEXT_PUBLIC_SUPABASE_ANON_KEY for a full deploy cycle). Fail loud
# BEFORE pulling images and recreating the stack.
REQUIRED_KEYS=(
  SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET
  DATABASE_URL JWT_SIGNING_SECRET SESSION_COOKIE_SECRET
  ANTHROPIC_API_KEY_GENERATION ANTHROPIC_API_KEY_SCORING OPENAI_API_KEY E2B_API_KEY
  RESEND_API_KEY
  NEXT_PUBLIC_ADMIN_URL NEXT_PUBLIC_CANDIDATE_URL NEXT_PUBLIC_API_URL
)
missing=()
for key in "${REQUIRED_KEYS[@]}"; do
  grep -qE "^${key}=.+" .env.local || missing+=("$key")
done
if (( ${#missing[@]} > 0 )); then
  echo "ERROR: .env.local missing/empty values for: ${missing[*]}" >&2
  echo "Check Settings -> Environments -> production." >&2
  echo "  vars.* names live in the Variables tab, secrets.* in the Secrets tab." >&2
  exit 1
fi

TAG="${IMAGE_TAG:-latest}"
export IMAGE_TAG="$TAG"

PROJECT="ri-assessments"
COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.yml -f docker-compose.prod.yml)

echo "==> deploying tag: $TAG"

# 1. Pull new images. Build stage already pushed them to GHCR via Actions.
if ! "${COMPOSE[@]}" pull; then
  echo "ERROR: image pull failed. Did the build job finish? Are the images public on GHCR?" >&2
  exit 3
fi

# 2. Apply DB migrations idempotently. Uses public._migrations ledger so
#    re-running is a no-op when there is nothing pending.
if ! "${COMPOSE[@]}" run --rm --no-deps api uv run python scripts/apply_migrations.py; then
  echo "ERROR: migration apply failed; aborting before rolling new images." >&2
  exit 2
fi

# 3. Roll the stack. `up -d` only recreates containers whose image digest
#    or env changed; everything else stays warm.
"${COMPOSE[@]}" up -d --remove-orphans

# 4. Wait for the api to report ready. Hard-fail if it never does so a bad
#    deploy is loud, not silent.
echo "==> waiting for api health..."
for attempt in $(seq 1 20); do
  if curl -fsS --max-time 3 http://127.0.0.1:18000/health/ready >/dev/null 2>&1; then
    echo "==> api ready (after ${attempt} probes)"
    curl -sS http://127.0.0.1:18000/health/ready
    echo
    echo "==> deploy complete: $TAG"
    exit 0
  fi
  sleep 2
done

echo "ERROR: api never returned 200 from /health/ready after 40s." >&2
echo "Container logs (last 50 lines):" >&2
"${COMPOSE[@]}" logs --tail=50 api >&2 || true
exit 4
