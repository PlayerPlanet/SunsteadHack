#!/bin/bash
# Story E AWS Deployment: IAM Setup
# Creates task execution role and task role with least-privilege policies.
# Idempotent: safe to re-run.
#
# NOTE: IAM JSON is passed inline via "$(cat ...)" rather than file://<path>,
# because aws-cli cannot load file:// paths that contain non-ASCII characters
# (e.g. a Windows home dir like C:\Users\Käyttäjä\...).

set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash: don't mangle any slash-args (no-op elsewhere)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.env"
IAM_DIR="${SCRIPT_DIR}/../iam"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.env not found at $CONFIG_FILE"
    exit 1
fi

source "$CONFIG_FILE"

echo "===== IAM Setup ====="
echo "Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo ""

# ---- Helpers --------

# Substitute placeholders in a JSON file
substitute_placeholders() {
    local input_file="$1"
    local output_file="$2"

    cat "$input_file" \
        | sed "s|\${AWS_ACCOUNT_ID}|${AWS_ACCOUNT_ID}|g" \
        | sed "s|\${AWS_REGION}|${AWS_REGION}|g" \
        | sed "s|\${TASK_FAMILY_NAME}|${TASK_FAMILY_NAME}|g" \
        | sed "s|\${ECR_REPO_NAME}|${ECR_REPO_NAME}|g" \
        | sed "s|\${SECRET_ANTHROPIC_API_KEY_NAME}|${SECRET_ANTHROPIC_API_KEY_NAME}|g" \
        | sed "s|\${SECRET_DB_DSN_NAME}|${SECRET_DB_DSN_NAME}|g" \
        > "$output_file"
}

# ---- Step 1: Create task execution role --------
echo "Step 1: Creating task execution role..."

if aws iam get-role --role-name "$TASK_EXECUTION_ROLE_NAME" 2>/dev/null | grep -q "Arn"; then
    echo "✓ Task execution role '$TASK_EXECUTION_ROLE_NAME' already exists."
else
    echo "Creating new task execution role..."

    # Create role with trust policy
    aws iam create-role \
        --role-name "$TASK_EXECUTION_ROLE_NAME" \
        --assume-role-policy-document "$(cat "${IAM_DIR}/ecs-tasks-trust-policy.json")"

    echo "✓ Task execution role created."
fi
echo ""

# ---- Step 2: Attach execution role inline policy --------
echo "Step 2: Attaching execution role policies..."

# Substitute and save the policy
TEMP_POLICY=$(mktemp)
substitute_placeholders "${IAM_DIR}/task-execution-role-policy.json" "$TEMP_POLICY"

aws iam put-role-policy \
    --role-name "$TASK_EXECUTION_ROLE_NAME" \
    --policy-name "ExecutionRolePolicy" \
    --policy-document "$(cat "${TEMP_POLICY}")"

rm "$TEMP_POLICY"
echo "✓ Execution role policy attached."
echo ""

# ---- Step 3: Create task role --------
echo "Step 3: Creating task role (minimal/empty by design)..."

if aws iam get-role --role-name "$TASK_ROLE_NAME" 2>/dev/null | grep -q "Arn"; then
    echo "✓ Task role '$TASK_ROLE_NAME' already exists."
else
    echo "Creating new task role..."

    # Create role with trust policy
    aws iam create-role \
        --role-name "$TASK_ROLE_NAME" \
        --assume-role-policy-document "$(cat "${IAM_DIR}/ecs-tasks-trust-policy.json")"

    echo "✓ Task role created."
fi
echo ""

# ---- Step 4: Attach task role explicit deny policy --------
echo "Step 4: Attaching task role policy (explicit deny-by-default)..."

aws iam put-role-policy \
    --role-name "$TASK_ROLE_NAME" \
    --policy-name "ExplicitDeny" \
    --policy-document "$(cat "${IAM_DIR}/task-role-policy.json")"

echo "✓ Task role policy attached (deny-by-default)."
echo ""

echo "===== IAM Setup Complete ====="
echo "Task Execution Role: $TASK_EXECUTION_ROLE_NAME"
echo "Task Role: $TASK_ROLE_NAME"
echo ""
echo "RATIONALE:"
echo "- Task Execution Role: Pulls ECR image, reads secrets, writes CloudWatch logs."
echo "- Task Role: Empty (deny-by-default). Container needs NO AWS API permissions."
echo "  The running code reads credentials from env (injected by exec role) and calls"
echo "  external services (Anthropic API, Aiven DB) over the network. No AWS APIs."
