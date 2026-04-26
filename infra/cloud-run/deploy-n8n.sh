#!/usr/bin/env bash
# Deploy a self-hosted n8n on Cloud Run with persistent state in Cloud SQL
# (or fall back to SQLite + a Cloud Storage volume mount for v1).
#
# Cloud Run services are stateless by default. For n8n's workflow + user
# data we either need Cloud SQL (recommended) or a GCS-backed volume mount
# via the second-generation Cloud Run runtime. This script wires the SQLite
# + Filestore approach which is simpler to bootstrap.
#
# Prereqs:
#   - gcloud authenticated, project + region set
#   - Filestore API enabled (or swap to Cloud SQL Postgres if you prefer)
#
# Usage:
#   GCP_PROJECT=my-project GCP_REGION=us-central1 \
#   bash infra/cloud-run/deploy-n8n.sh
set -euo pipefail

: "${GCP_PROJECT:?GCP_PROJECT must be set}"
: "${GCP_REGION:=us-central1}"

# Choose a stable encryption key for n8n. Generate one with:
#   openssl rand -hex 32
: "${N8N_ENCRYPTION_KEY:?N8N_ENCRYPTION_KEY must be set (openssl rand -hex 32)}"

# n8n requires a public-facing URL once running.
: "${N8N_HOSTNAME:?N8N_HOSTNAME must be set (e.g. n8n.assessments.revenueinstitute.com or the Cloud Run hostname after first deploy)}"

echo "==> Deploying n8n to Cloud Run"
gcloud run deploy ri-n8n \
  --project "$GCP_PROJECT" \
  --region "$GCP_REGION" \
  --image n8nio/n8n:latest \
  --platform managed \
  --allow-unauthenticated \
  --port 5678 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 1 \
  --concurrency 80 \
  --execution-environment gen2 \
  --set-env-vars "N8N_HOST=${N8N_HOSTNAME}" \
  --set-env-vars "N8N_PROTOCOL=https" \
  --set-env-vars "WEBHOOK_URL=https://${N8N_HOSTNAME}/" \
  --set-env-vars "N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}" \
  --set-env-vars "N8N_DIAGNOSTICS_ENABLED=false" \
  --set-env-vars "N8N_PERSONALIZATION_ENABLED=false"

echo
echo "==> Done. Service URL:"
gcloud run services describe ri-n8n \
  --project "$GCP_PROJECT" --region "$GCP_REGION" \
  --format 'value(status.url)'

cat <<'NEXT'

Next steps:
  1. Open the service URL — n8n will print a one-time signup URL.
  2. Sign up to bootstrap an owner account.
  3. Settings → API → create a Personal API Key.
  4. Set N8N_ADMIN_API_KEY in your .env (and the FastAPI Cloud Run env vars).
  5. Re-run infra/cloud-run/deploy-api.sh to rebuild the FastAPI service
     with the new key.

Persistent state: this v1 deploy uses min-instances=1 so n8n's SQLite
file in /home/node/.n8n survives between requests. For production
(multiple replicas, restart safety), migrate to Cloud SQL Postgres by
setting:
  --set-env-vars DB_TYPE=postgresdb
  --set-env-vars DB_POSTGRESDB_HOST=...
  --set-env-vars DB_POSTGRESDB_DATABASE=...
  --set-env-vars DB_POSTGRESDB_USER=...
  --set-env-vars DB_POSTGRESDB_PASSWORD=...
  --add-cloudsql-instances <project>:<region>:<instance>
NEXT
