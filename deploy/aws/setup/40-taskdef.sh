#!/bin/bash
# Story E AWS Deployment: Task Definition Registration
# Registers the Fargate task definition for the proposer (Phase 0).
# Idempotent: creates a new revision if the task def already exists.

set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash: don't mangle slash-args like /ecs/... (no-op elsewhere)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.env"
TASKDEF_FILE="${SCRIPT_DIR}/../task-def.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.env not found at $CONFIG_FILE"
    exit 1
fi

if [ ! -f "$TASKDEF_FILE" ]; then
    echo "Error: task-def.json not found at $TASKDEF_FILE"
    exit 1
fi

source "$CONFIG_FILE"

echo "===== Task Definition Registration ====="
echo "Cluster: $ECS_CLUSTER_NAME"
echo "Task Family: $TASK_FAMILY_NAME"
echo "Region: $AWS_REGION"
echo ""

# ---- Step 1: Create ECS cluster if not exists --------
echo "Step 1: Creating ECS cluster (idempotent)..."

if aws ecs describe-clusters \
    --region "$AWS_REGION" \
    --clusters "$ECS_CLUSTER_NAME" \
    --query 'clusters[0].clusterArn' \
    --output text 2>/dev/null | grep -q "arn:"; then
    echo "✓ ECS cluster '$ECS_CLUSTER_NAME' already exists."
else
    echo "Creating new ECS cluster..."
    aws ecs create-cluster \
        --region "$AWS_REGION" \
        --cluster-name "$ECS_CLUSTER_NAME"
    echo "✓ ECS cluster created."
fi
echo ""

# ---- Step 2: Substitute placeholders in task def --------
echo "Step 2: Processing task definition template..."

TEMP_TASKDEF=$(mktemp)

cat "$TASKDEF_FILE" \
    | sed "s|\${AWS_ACCOUNT_ID}|${AWS_ACCOUNT_ID}|g" \
    | sed "s|\${AWS_REGION}|${AWS_REGION}|g" \
    | sed "s|\${TASK_FAMILY_NAME}|${TASK_FAMILY_NAME}|g" \
    | sed "s|\${TASK_CPU}|${TASK_CPU}|g" \
    | sed "s|\${TASK_MEMORY}|${TASK_MEMORY}|g" \
    | sed "s|\${ECR_REPO_NAME}|${ECR_REPO_NAME}|g" \
    | sed "s|\${ECR_IMAGE_TAG}|${ECR_IMAGE_TAG}|g" \
    | sed "s|\${TASK_EXECUTION_ROLE_NAME}|${TASK_EXECUTION_ROLE_NAME}|g" \
    | sed "s|\${TASK_ROLE_NAME}|${TASK_ROLE_NAME}|g" \
    | sed "s|\${SECRET_ANTHROPIC_API_KEY_NAME}|${SECRET_ANTHROPIC_API_KEY_NAME}|g" \
    | sed "s|\${SECRET_DB_DSN_NAME}|${SECRET_DB_DSN_NAME}|g" \
    > "$TEMP_TASKDEF"

echo "✓ Task definition processed."

# Resolve the REAL secret ARNs and substitute them into the task def. ECS
# `valueFrom` requires the full secret ARN (with its random 6-char suffix) — the
# `-*` glob used in the IAM policy is NOT valid here. Requires 10-secrets.sh first.
API_ARN=$(aws secretsmanager describe-secret --region "$AWS_REGION" \
    --secret-id "$SECRET_ANTHROPIC_API_KEY_NAME" --query 'ARN' --output text)
DSN_ARN=$(aws secretsmanager describe-secret --region "$AWS_REGION" \
    --secret-id "$SECRET_DB_DSN_NAME" --query 'ARN' --output text)
python - "$TEMP_TASKDEF" "$API_ARN" "$DSN_ARN" "$SECRET_ANTHROPIC_API_KEY_NAME" "$SECRET_DB_DSN_NAME" <<'PY'
import sys
f, api, dsn, apiname, dsnname = sys.argv[1:6]
s = open(f).read()
s = s.replace(f"secret:{apiname}-*", f"secret:{api.split(':secret:')[-1]}")
s = s.replace(f"secret:{dsnname}-*", f"secret:{dsn.split(':secret:')[-1]}")
open(f, "w").write(s)
PY
echo "✓ Resolved real secret ARNs into valueFrom."
echo ""

# ---- Step 3: Create CloudWatch Logs group --------
echo "Step 3: Creating CloudWatch Logs group..."

LOG_GROUP="/ecs/${TASK_FAMILY_NAME}"

if aws logs describe-log-groups \
    --region "$AWS_REGION" \
    --log-group-name-prefix "$LOG_GROUP" \
    --query "logGroups[?logGroupName=='$LOG_GROUP'].logGroupName" \
    --output text 2>/dev/null | grep -q "$LOG_GROUP"; then
    echo "✓ Log group '$LOG_GROUP' already exists."
else
    echo "Creating new log group..."
    aws logs create-log-group \
        --region "$AWS_REGION" \
        --log-group-name "$LOG_GROUP"
    echo "✓ Log group created."
fi
echo ""

# ---- Step 4: Register task definition --------
echo "Step 4: Registering task definition..."

TASKDEF_ARN=$(aws ecs register-task-definition \
    --region "$AWS_REGION" \
    --cli-input-json "$(cat "${TEMP_TASKDEF}")" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

rm "$TEMP_TASKDEF"

echo "✓ Task definition registered: $TASKDEF_ARN"
echo ""

echo "===== Task Definition Registration Complete ====="
echo "Task Definition ARN: $TASKDEF_ARN"
echo "CloudWatch Logs: $LOG_GROUP"
echo ""
echo "Next: Run setup/50-smoke.sh to test the deployment."
