#!/usr/bin/env bash
# Build + deploy apps/api (FastAPI) to Cloud Run.
#
# Prereqs:
#   - gcloud CLI authenticated (gcloud auth login)
#   - A Google Cloud project with Cloud Run + Cloud Build APIs enabled
#   - .env populated (run scripts/check-env.sh api first)
#
# Usage:
#   GCP_PROJECT=my-project GCP_REGION=us-central1 \
#   bash infra/cloud-run/deploy-api.sh [tag]
#
# Pass a tag arg to deploy a specific image version; otherwise we tag with
# the current git SHA.
set -euo pipefail

if ! command -v gcloud >/dev/null 2>&1; then
  echo "error: gcloud CLI not found." >&2
  exit 2
fi

: "${GCP_PROJECT:?GCP_PROJECT must be set}"
: "${GCP_REGION:=us-central1}"

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

env_file="${ENV_FILE:-.env}"
if [[ ! -f "$env_file" ]]; then
  echo "error: $env_file not found." >&2
  exit 2
fi

tag="${1:-$(git rev-parse --short HEAD)}"
image="gcr.io/${GCP_PROJECT}/ri-assessments-api:${tag}"

echo "==> Building image: $image"
gcloud builds submit \
  --project "$GCP_PROJECT" \
  --tag "$image" \
  apps/api

echo "==> Collecting env vars from $env_file"
# Cloud Run accepts repeatable --set-env-vars KEY=VALUE; we pass the
# variables that FastAPI actually reads. Anything containing commas is
# escaped with the alternate '^@^' delimiter syntax.
api_vars=(
  APP_ENV
  SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET DATABASE_URL
  JWT_SIGNING_SECRET SESSION_COOKIE_SECRET
  ANTHROPIC_API_KEY_GENERATION ANTHROPIC_API_KEY_SCORING
  E2B_API_KEY
  N8N_HOST N8N_ADMIN_API_KEY N8N_WEBHOOK_SECRET
  UPSTASH_REDIS_URL UPSTASH_REDIS_TOKEN
  RESEND_API_KEY RESEND_FROM_EMAIL
  VOYAGE_API_KEY EMBEDDING_MODEL EMBEDDING_DIMS
  SENTRY_DSN_API SENTRY_ORG SENTRY_PROJECT
  AXIOM_TOKEN AXIOM_DATASET
  SUPABASE_STORAGE_BUCKET_ARTIFACTS SUPABASE_STORAGE_BUCKET_REFERENCES
  NEXT_PUBLIC_ADMIN_URL NEXT_PUBLIC_CANDIDATE_URL
)
# shellcheck disable=SC1090
set -a; . "$env_file"; set +a

env_args=()
for var in "${api_vars[@]}"; do
  value="${!var:-}"
  if [[ -n "$value" ]]; then
    env_args+=("--set-env-vars" "${var}=${value}")
  fi
done

echo "==> Deploying ri-assessments-api to Cloud Run"
gcloud run deploy ri-assessments-api \
  --project "$GCP_PROJECT" \
  --region "$GCP_REGION" \
  --image "$image" \
  --platform managed \
  --allow-unauthenticated \
  --concurrency 30 \
  --timeout 300 \
  --memory 1Gi \
  --cpu 1 \
  --port 8000 \
  --min-instances 0 \
  --max-instances 10 \
  "${env_args[@]}"

echo
echo "==> Done. Service URL:"
gcloud run services describe ri-assessments-api \
  --project "$GCP_PROJECT" --region "$GCP_REGION" \
  --format 'value(status.url)'
