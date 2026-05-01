#!/usr/bin/env bash
# Provisions a Cloud Scheduler job that polls the FastAPI series endpoint
# and issues the next assignment for any series whose next_due_at has
# passed.
#
# v1 approach: the scheduler hits POST /api/series/dispatch-due, which
# walks every series whose next_due_at <= now and issues the next
# assignment for each. Idempotent and partial-failure tolerant. Admins
# can also force-issue per series via POST /api/series/{id}/issue-next
# from the admin UI.
#
# Prereqs:
#   - gcloud authenticated, project + region set
#   - FastAPI Cloud Run service deployed (so we have a target URL)
#   - A service account with the cloudscheduler.jobs.create permission
#
# Usage:
#   GCP_PROJECT=my-project GCP_REGION=us-central1 \
#   API_URL=https://ri-assessments-api-xxx.a.run.app \
#   ADMIN_JWT=<paste a service-account JWT signed with SUPABASE_JWT_SECRET> \
#   bash infra/scheduler/series-cron.sh
set -euo pipefail

: "${GCP_PROJECT:?GCP_PROJECT must be set}"
: "${GCP_REGION:=us-central1}"
: "${API_URL:?API_URL must be set (Cloud Run service URL)}"
: "${ADMIN_JWT:?ADMIN_JWT must be set (Supabase admin JWT for auth)}"

job_name="ri-series-issue-next"
schedule="0 9 * * *"  # 9am daily UTC

echo "==> Creating/updating Cloud Scheduler job: $job_name"

# Idempotent: delete if it exists, then create fresh.
gcloud scheduler jobs delete "$job_name" \
  --project "$GCP_PROJECT" \
  --location "$GCP_REGION" \
  --quiet || true

gcloud scheduler jobs create http "$job_name" \
  --project "$GCP_PROJECT" \
  --location "$GCP_REGION" \
  --schedule "$schedule" \
  --time-zone "UTC" \
  --uri "${API_URL}/api/series/dispatch-due" \
  --http-method POST \
  --headers "Content-Type=application/json,Authorization=Bearer ${ADMIN_JWT}" \
  --message-body '{}' \
  --attempt-deadline 300s

echo
echo "==> Done. Test with:"
echo "    gcloud scheduler jobs run $job_name --project $GCP_PROJECT --location $GCP_REGION"
