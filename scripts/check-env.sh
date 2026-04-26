#!/usr/bin/env bash
# Preflight env-var validator. Reads .env (or the file passed as $1),
# checks that every variable required by the named target is non-empty,
# and prints a summary. Doesn't print the values themselves.
#
# Usage:
#   bash scripts/check-env.sh api
#   bash scripts/check-env.sh admin
#   bash scripts/check-env.sh candidate
#   bash scripts/check-env.sh all
#   ENV_FILE=.env.production bash scripts/check-env.sh api
set -euo pipefail

target="${1:-all}"
env_file="${ENV_FILE:-.env}"

if [[ ! -f "$env_file" ]]; then
  echo "error: $env_file not found. Copy .env.example to $env_file and fill in." >&2
  exit 2
fi

# Load without echoing.
# shellcheck disable=SC1090
set -a; . "$env_file"; set +a

required_for_api=(
  SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET DATABASE_URL
  JWT_SIGNING_SECRET
  ANTHROPIC_API_KEY_GENERATION ANTHROPIC_API_KEY_SCORING
  E2B_API_KEY
  RESEND_API_KEY RESEND_FROM_EMAIL
  VOYAGE_API_KEY EMBEDDING_MODEL EMBEDDING_DIMS
  NEXT_PUBLIC_CANDIDATE_URL
)

# Optional-but-recommended for FastAPI; don't fail, just warn.
recommended_for_api=(
  N8N_HOST N8N_ADMIN_API_KEY
  UPSTASH_REDIS_URL UPSTASH_REDIS_TOKEN
  SENTRY_DSN_API AXIOM_TOKEN AXIOM_DATASET
)

required_for_admin=(
  NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY
  SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY
  INTERNAL_API_URL
)

required_for_candidate=(
  INTERNAL_API_URL NEXT_PUBLIC_API_URL NEXT_PUBLIC_CANDIDATE_URL
)

failures=0
warnings=0

check_set() {
  local label="$1"; shift
  local kind="$1"; shift  # required | recommended
  for var in "$@"; do
    if [[ -z "${!var:-}" ]]; then
      if [[ "$kind" == "required" ]]; then
        echo "  ✗ $var (required for $label)"
        failures=$((failures + 1))
      else
        echo "  ! $var (recommended for $label)"
        warnings=$((warnings + 1))
      fi
    else
      echo "  ✓ $var"
    fi
  done
}

check_target() {
  local t="$1"
  echo
  echo "== $t =="
  case "$t" in
    api)
      check_set api required "${required_for_api[@]}"
      check_set api recommended "${recommended_for_api[@]}"
      ;;
    admin)
      check_set admin required "${required_for_admin[@]}"
      ;;
    candidate)
      check_set candidate required "${required_for_candidate[@]}"
      ;;
    *)
      echo "unknown target: $t (use api / admin / candidate / all)" >&2
      exit 2
      ;;
  esac
}

if [[ "$target" == "all" ]]; then
  check_target api
  check_target admin
  check_target candidate
else
  check_target "$target"
fi

echo
echo "----"
if [[ "$failures" -eq 0 ]]; then
  echo "ok ($warnings warning(s))"
  exit 0
else
  echo "FAILED: $failures missing required variable(s) ($warnings warning(s))" >&2
  exit 1
fi
