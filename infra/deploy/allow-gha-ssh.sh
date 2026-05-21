#!/usr/bin/env bash
# Allow SSH (tcp:22) from GitHub Actions runner IP ranges on the ri-master VM.
#
# GitHub publishes its current Actions runner IPs at
#   https://api.github.com/meta -> .actions[]
# The list rotates roughly weekly. Re-run this script monthly (or wire
# it into Cloud Scheduler) to keep the rules current.
#
# GCP firewall rules cap at 256 source ranges each, so this script
# creates as many `ri-allow-gha-ssh-NN` rules as needed and deletes any
# stale ones from a previous run.
#
# Required env / args:
#   GCP_PROJECT          GCP project id
#   VM_NETWORK_TAG       network tag on the VM that this rule targets
#                        (find it: gcloud compute instances describe ri-master
#                                  --format='value(tags.items)')
#
# Usage:
#   GCP_PROJECT=my-project VM_NETWORK_TAG=http-server bash infra/deploy/allow-gha-ssh.sh
#
# Safe to re-run: the script deletes old rules first, then recreates.

set -euo pipefail

: "${GCP_PROJECT:?set GCP_PROJECT to your GCP project id}"
: "${VM_NETWORK_TAG:?set VM_NETWORK_TAG to a network tag on the ri-master VM}"

RULE_PREFIX="ri-allow-gha-ssh"
MAX_RANGES_PER_RULE=256

echo "==> fetching current GitHub Actions IP ranges"
ACTIONS_IPS=$(curl -fsSL https://api.github.com/meta | python3 -c '
import json, sys
data = json.load(sys.stdin)
# IPv4 only; GCP source ranges accept v4. For v6, GCP needs source-ranges
# in v6 syntax via a separate rule. Skip v6 for simplicity.
v4 = [c for c in data["actions"] if ":" not in c]
print(" ".join(v4))
')

if [[ -z "$ACTIONS_IPS" ]]; then
  echo "ERROR: no IPv4 ranges returned from GitHub meta API." >&2
  exit 1
fi

# Convert space-separated list into an array
read -r -a RANGES <<< "$ACTIONS_IPS"
TOTAL=${#RANGES[@]}
echo "==> $TOTAL IPv4 ranges total; splitting into rules of $MAX_RANGES_PER_RULE"

# Delete any prior rules with our prefix so re-runs are clean
echo "==> removing existing $RULE_PREFIX-* rules"
OLD_RULES=$(gcloud compute firewall-rules list \
  --project="$GCP_PROJECT" \
  --filter="name~^${RULE_PREFIX}-" \
  --format='value(name)' || true)
for rule in $OLD_RULES; do
  echo "    delete $rule"
  gcloud compute firewall-rules delete "$rule" \
    --project="$GCP_PROJECT" --quiet >/dev/null
done

# Create new rules in chunks of 256
i=0
chunk=1
while (( i < TOTAL )); do
  end=$(( i + MAX_RANGES_PER_RULE ))
  (( end > TOTAL )) && end=$TOTAL
  SLICE="${RANGES[*]:$i:$(( end - i ))}"
  CSV=$(echo "$SLICE" | tr ' ' ',')
  RULE_NAME=$(printf '%s-%02d' "$RULE_PREFIX" "$chunk")

  echo "==> create $RULE_NAME with $(( end - i )) ranges"
  gcloud compute firewall-rules create "$RULE_NAME" \
    --project="$GCP_PROJECT" \
    --direction=INGRESS --action=allow \
    --rules=tcp:22 \
    --source-ranges="$CSV" \
    --target-tags="$VM_NETWORK_TAG" \
    --description="GitHub Actions SSH ingress (auto-refreshed; do not edit by hand)" \
    >/dev/null

  i=$end
  chunk=$(( chunk + 1 ))
done

echo "==> done. $(( chunk - 1 )) firewall rule(s) created."
echo "    Re-run this script monthly to keep ranges current."
