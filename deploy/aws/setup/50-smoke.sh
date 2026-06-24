#!/bin/bash
# Story E AWS Deployment: Phase-0 Smoke Test
# Launches one proposer task, waits for completion, retrieves logs, validates output.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.env"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.env not found at $CONFIG_FILE"
    exit 1
fi

source "$CONFIG_FILE"

echo "===== Phase-0 Smoke Test ====="
echo "Cluster: $ECS_CLUSTER_NAME"
echo "Task Family: $TASK_FAMILY_NAME"
echo "Subnets: $SUBNET_ID_1, $SUBNET_ID_2"
echo "Security Group: $SECURITY_GROUP_ID"
echo "Region: $AWS_REGION"
echo ""

# ---- Step 1: Launch task --------
echo "Step 1: Launching proposer task..."

TASK_ARN=$(aws ecs run-task \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER_NAME" \
    --task-definition "$TASK_FAMILY_NAME" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID_1,$SUBNET_ID_2],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=DISABLED}" \
    --query 'tasks[0].taskArn' \
    --output text)

TASK_ID=$(echo "$TASK_ARN" | rev | cut -d'/' -f1 | rev)
echo "✓ Task launched: $TASK_ARN"
echo "Task ID: $TASK_ID"
echo ""

# ---- Step 2: Wait for task completion --------
echo "Step 2: Waiting for task to complete..."
TIMEOUT=300  # 5 minutes
ELAPSED=0
POLL_INTERVAL=5

while [ $ELAPSED -lt $TIMEOUT ]; do
    TASK_STATUS=$(aws ecs describe-tasks \
        --region "$AWS_REGION" \
        --cluster "$ECS_CLUSTER_NAME" \
        --tasks "$TASK_ARN" \
        --query 'tasks[0].lastStatus' \
        --output text)

    if [ "$TASK_STATUS" = "STOPPED" ]; then
        echo "✓ Task stopped."
        break
    fi

    echo "  Status: $TASK_STATUS (elapsed: ${ELAPSED}s)"
    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "Error: Task did not complete within ${TIMEOUT}s"
    exit 1
fi
echo ""

# ---- Step 3: Get task exit code --------
echo "Step 3: Checking task exit code..."

EXIT_CODE=$(aws ecs describe-tasks \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER_NAME" \
    --tasks "$TASK_ARN" \
    --query 'tasks[0].containers[0].exitCode' \
    --output text)

echo "Exit Code: $EXIT_CODE"
if [ "$EXIT_CODE" != "0" ]; then
    echo "⚠ Task exited with non-zero code"
fi
echo ""

# ---- Step 4: Retrieve CloudWatch logs --------
echo "Step 4: Retrieving CloudWatch logs..."

LOG_GROUP="/ecs/${TASK_FAMILY_NAME}"
LOG_STREAM="${TASK_ID}"

# CloudWatch may take a moment to create the log stream
sleep 3

if ! aws logs describe-log-streams \
    --region "$AWS_REGION" \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name-prefix "$TASK_ID" \
    --query 'logStreams[0].logStreamName' \
    --output text 2>/dev/null | grep -q "$TASK_ID"; then

    # Try alternative log stream names
    echo "  Primary log stream not found, searching for alternatives..."
    LOG_STREAM=$(aws logs describe-log-streams \
        --region "$AWS_REGION" \
        --log-group-name "$LOG_GROUP" \
        --order-by LastEventTime \
        --descending \
        --query 'logStreams[0].logStreamName' \
        --output text)
fi

echo "Log Stream: $LOG_STREAM"
echo ""

# ---- Step 5: Fetch and display logs --------
echo "Step 5: Fetching logs..."

LOGS=$(aws logs get-log-events \
    --region "$AWS_REGION" \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --query 'events[].message' \
    --output text)

if [ -z "$LOGS" ]; then
    echo "⚠ No logs found. Task may have failed to start."
    echo "Check security group, network config, and ECR permissions."
    exit 1
fi

echo "=== Task Output ==="
echo "$LOGS"
echo "===================="
echo ""

# ---- Step 6: Validate output (contains Candidate JSON) --------
echo "Step 6: Validating output format..."

# Extract JSON from logs (claude wraps output in {"result": "..."})
JSON_OUTPUT=$(echo "$LOGS" | grep -o '{"type":"index"[^}]*}' || echo "")

if [ -n "$JSON_OUTPUT" ]; then
    echo "✓ Valid Candidate JSON found:"
    echo "$JSON_OUTPUT"
    echo ""
    echo "===== Smoke Test PASSED ====="
else
    echo "⚠ Could not extract Candidate JSON from logs."
    echo "Expected format: {\"type\":\"index\",\"params\":{...},\"reversible\":true}"
    echo ""
    echo "Full logs above may contain error details."
    echo "===== Smoke Test FAILED ====="
    exit 1
fi
