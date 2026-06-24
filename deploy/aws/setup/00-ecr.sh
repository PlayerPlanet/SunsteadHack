#!/bin/bash
# Story E AWS Deployment: ECR Setup
# Creates ECR repo and pushes the proposer container image.
# Idempotent: safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.env"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.env not found at $CONFIG_FILE"
    echo "Please copy config.env.example to config.env and customize it."
    exit 1
fi

source "$CONFIG_FILE"

echo "===== ECR Setup ====="
echo "Region: $AWS_REGION"
echo "Account: $AWS_ACCOUNT_ID"
echo "ECR Repo: $ECR_REPO_NAME"
echo "Image Tag: $ECR_IMAGE_TAG"
echo ""

# ---- Step 1: Create ECR repo if not exists -------
echo "Step 1: Creating ECR repository (idempotent)..."

if aws ecr describe-repositories \
    --region "$AWS_REGION" \
    --repository-names "$ECR_REPO_NAME" \
    --query 'repositories[0].repositoryUri' \
    --output text 2>/dev/null | grep -q "ecr"; then
    echo "✓ ECR repo '$ECR_REPO_NAME' already exists."
else
    echo "Creating new ECR repo..."
    aws ecr create-repository \
        --region "$AWS_REGION" \
        --repository-name "$ECR_REPO_NAME" \
        --image-scanning-configuration scanOnPush=false
    echo "✓ ECR repo created."
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"
echo "ECR URI: $ECR_URI"
echo ""

# ---- Step 2: Build the proposer image --------
echo "Step 2: Building proposer container image..."
PROPOSER_DIR="${REPO_ROOT}/proposer-container"

if [ ! -d "$PROPOSER_DIR" ]; then
    echo "Error: proposer-container not found at $PROPOSER_DIR"
    exit 1
fi

docker build \
    -t "${ECR_URI}:${ECR_IMAGE_TAG}" \
    -f "${PROPOSER_DIR}/Dockerfile" \
    "$PROPOSER_DIR"
echo "✓ Image built: ${ECR_URI}:${ECR_IMAGE_TAG}"
echo ""

# ---- Step 3: Login to ECR and push --------
echo "Step 3: Pushing image to ECR..."

aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ECR_URI"

docker push "${ECR_URI}:${ECR_IMAGE_TAG}"
echo "✓ Image pushed to ECR."
echo ""

echo "===== ECR Setup Complete ====="
echo "Image URI: ${ECR_URI}:${ECR_IMAGE_TAG}"
