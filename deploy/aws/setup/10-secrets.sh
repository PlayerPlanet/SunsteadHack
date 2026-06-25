#!/bin/bash
# Story E AWS Deployment: Secrets Manager Setup
# Creates/updates secrets for ANTHROPIC_API_KEY and DB_DSN.
# Reads from environment variables WITHOUT echoing them.
# Idempotent: safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.env"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.env not found at $CONFIG_FILE"
    exit 1
fi

source "$CONFIG_FILE"

echo "===== Secrets Manager Setup ====="
echo "Region: $AWS_REGION"
echo ""

# Verify env vars are set
if [ -z "${anthropic_aws:-}" ]; then
    echo "Error: ANTHROPIC_API_KEY environment variable not set."
    echo "Set it before running this script:"
    echo "  export ANTHROPIC_API_KEY='sk-ant-...'"
    exit 1
fi

if [ -z "${DB_DSN:-}" ]; then
    echo "Error: DB_DSN environment variable not set."
    echo "Set it before running this script:"
    echo "  export DB_DSN='postgresql://researcher_ro:pass@db.example.com:5432/postgres'"
    exit 1
fi

echo "✓ Environment variables verified (not echoed)."
echo ""

# ---- Step 1: Create/update ANTHROPIC_API_KEY secret --------
echo "Step 1: Creating/updating ANTHROPIC_API_KEY secret..."

SECRET_ARN=$(aws secretsmanager describe-secret \
    --region "$AWS_REGION" \
    --secret-id "$SECRET_ANTHROPIC_API_KEY_NAME" \
    --query 'ARN' \
    --output text 2>/dev/null || echo "")

if [ -z "$SECRET_ARN" ]; then
    echo "Creating new secret: $SECRET_ANTHROPIC_API_KEY_NAME"
    SECRET_ARN=$(aws secretsmanager create-secret \
        --region "$AWS_REGION" \
        --name "$SECRET_ANTHROPIC_API_KEY_NAME" \
        --secret-string "$anthropic_aws" \
        --query 'ARN' \
        --output text)
    echo "✓ Secret created: $SECRET_ARN"
else
    echo "Updating existing secret: $SECRET_ANTHROPIC_API_KEY_NAME"
    aws secretsmanager put-secret-value \
        --region "$AWS_REGION" \
        --secret-id "$SECRET_ANTHROPIC_API_KEY_NAME" \
        --secret-string "$ANTHROPIC_API_KEY" >/dev/null
    echo "✓ Secret updated: $SECRET_ARN"
fi
echo ""

# ---- Step 2: Create/update DB_DSN secret --------
echo "Step 2: Creating/updating DB_DSN secret..."

SECRET_ARN=$(aws secretsmanager describe-secret \
    --region "$AWS_REGION" \
    --secret-id "$SECRET_DB_DSN_NAME" \
    --query 'ARN' \
    --output text 2>/dev/null || echo "")

if [ -z "$SECRET_ARN" ]; then
    echo "Creating new secret: $SECRET_DB_DSN_NAME"
    SECRET_ARN=$(aws secretsmanager create-secret \
        --region "$AWS_REGION" \
        --name "$SECRET_DB_DSN_NAME" \
        --secret-string "$DB_DSN" \
        --query 'ARN' \
        --output text)
    echo "✓ Secret created: $SECRET_ARN"
else
    echo "Updating existing secret: $SECRET_DB_DSN_NAME"
    aws secretsmanager put-secret-value \
        --region "$AWS_REGION" \
        --secret-id "$SECRET_DB_DSN_NAME" \
        --secret-string "$DB_DSN" >/dev/null
    echo "✓ Secret updated: $SECRET_ARN"
fi
echo ""

echo "===== Secrets Manager Setup Complete ====="
echo "Secrets created/updated (values not echoed)."
