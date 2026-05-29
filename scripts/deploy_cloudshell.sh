#!/usr/bin/env bash
set -euo pipefail

# Deployment helper template only.
#
# This script intentionally refuses to run unless explicitly enabled because
# deploys and environment updates are not part of local cleanup work.
#
# Real Microsoft / OneDrive values must come from an uncommitted local .env file
# or a secret manager. Do not paste them into this script, docs, chat, commits,
# screenshots, or logs.

if [[ "${ALLOW_DEPLOY_CLOUDSHELL:-}" != "yes" ]]; then
  echo "Refusing to deploy. Set ALLOW_DEPLOY_CLOUDSHELL=yes only during an approved deployment."
  exit 1
fi

required_env=(
  MS_CLIENT_ID
  MS_REFRESH_TOKEN
  ONEDRIVE_DRIVE_ID
  ONEDRIVE_FILE_ID
)

for key in "${required_env[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    echo "Missing required environment variable: ${key}" >&2
    exit 1
  fi
done

MS_TENANT_ID="${MS_TENANT_ID:-consumers}"

gcloud run deploy order-app \
  --source . \
  --project "${GCP_PROJECT_ID:?Missing required environment variable: GCP_PROJECT_ID}" \
  --region "${GCP_REGION:-us-central1}" \
  --platform managed \
  --allow-unauthenticated \
  --update-env-vars "MS_CLIENT_ID=${MS_CLIENT_ID}" \
  --update-env-vars "MS_TENANT_ID=${MS_TENANT_ID}" \
  --update-env-vars "ONEDRIVE_FILE_ID=${ONEDRIVE_FILE_ID}" \
  --update-env-vars "ONEDRIVE_DRIVE_ID=${ONEDRIVE_DRIVE_ID}" \
  --update-env-vars "MS_REFRESH_TOKEN=${MS_REFRESH_TOKEN}"
