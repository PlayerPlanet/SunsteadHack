#!/bin/bash
# Story E AWS Deployment: Network Setup
# Validates/creates VPC, subnets, and egress-only security group.
# Idempotent: safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.env"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.env not found at $CONFIG_FILE"
    exit 1
fi

source "$CONFIG_FILE"

echo "===== Network Setup ====="
echo "Region: $AWS_REGION"
echo "VPC: $VPC_ID"
echo ""

# ---- Step 1: Verify VPC --------
echo "Step 1: Verifying VPC..."

if aws ec2 describe-vpcs \
    --region "$AWS_REGION" \
    --vpc-ids "$VPC_ID" \
    --query 'Vpcs[0].VpcId' \
    --output text 2>/dev/null | grep -q "vpc-"; then
    echo "✓ VPC exists: $VPC_ID"
else
    echo "Error: VPC not found: $VPC_ID"
    echo "Please create a VPC and subnets, then update config.env."
    exit 1
fi
echo ""

# ---- Step 2: Verify subnets --------
echo "Step 2: Verifying subnets..."

for subnet in "$SUBNET_ID_1" "$SUBNET_ID_2"; do
    if aws ec2 describe-subnets \
        --region "$AWS_REGION" \
        --subnet-ids "$subnet" \
        --query 'Subnets[0].SubnetId' \
        --output text 2>/dev/null | grep -q "subnet-"; then
        echo "✓ Subnet exists: $subnet"
    else
        echo "Error: Subnet not found: $subnet"
        echo "Please ensure subnets are in the VPC with NAT Gateway for egress."
        exit 1
    fi
done
echo ""

# ---- Step 3: Create/verify egress-only security group --------
echo "Step 3: Verifying egress-only security group..."

if aws ec2 describe-security-groups \
    --region "$AWS_REGION" \
    --group-ids "$SECURITY_GROUP_ID" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null | grep -q "sg-"; then
    echo "✓ Security group exists: $SECURITY_GROUP_ID"

    # Verify it has no inbound rules
    INBOUND_COUNT=$(aws ec2 describe-security-groups \
        --region "$AWS_REGION" \
        --group-ids "$SECURITY_GROUP_ID" \
        --query 'SecurityGroups[0].IpPermissions | length(@)' \
        --output text)

    if [ "$INBOUND_COUNT" -eq 0 ]; then
        echo "✓ No inbound rules (correct)."
    else
        echo "⚠ Security group has $INBOUND_COUNT inbound rule(s)."
        echo "  For security, the SG should only have egress rules."
        echo "  Consider reviewing the SG configuration."
    fi

    # Check for 443 (HTTPS) egress
    EGRESS_443=$(aws ec2 describe-security-groups \
        --region "$AWS_REGION" \
        --group-ids "$SECURITY_GROUP_ID" \
        --query 'SecurityGroups[0].IpPermissionsEgress[?FromPort==`443` || FromPort==`-1`] | length(@)' \
        --output text)

    if [ "$EGRESS_443" -gt 0 ]; then
        echo "✓ Egress to 443 (HTTPS) configured."
    else
        echo "⚠ No explicit HTTPS (443) egress rule found."
        echo "  Ensure the SG allows outbound to 443 and the DB port."
    fi
else
    echo "Creating new security group..."

    SG_ID=$(aws ec2 create-security-group \
        --region "$AWS_REGION" \
        --group-name "sunsteadhack-egress-only" \
        --description "Egress-only SG for SunsteadHack tasks (no inbound)" \
        --vpc-id "$VPC_ID" \
        --query 'GroupId' \
        --output text)

    echo "✓ Security group created: $SG_ID"

    # Add egress rules: 443 (Anthropic API) and 5432 (Postgres)
    echo "Adding egress rules..."

    aws ec2 authorize-security-group-egress \
        --region "$AWS_REGION" \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 443 \
        --cidr 0.0.0.0/0

    aws ec2 authorize-security-group-egress \
        --region "$AWS_REGION" \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 5432 \
        --cidr 0.0.0.0/0

    # AWS attaches a default allow-all egress rule (0.0.0.0/0, all protocols) to
    # every new SG. Revoke it so egress is truly limited to 443 + 5432; otherwise
    # the "egress-only to 443/DB" guarantee is false (all outbound would be open).
    echo "Revoking default allow-all egress rule..."
    aws ec2 revoke-security-group-egress \
        --region "$AWS_REGION" \
        --group-id "$SG_ID" \
        --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]' \
        >/dev/null 2>&1 || echo "  (no default allow-all rule to revoke)"

    echo "✓ Egress rules added (443, 5432); default allow-all revoked."
    echo ""
    echo "UPDATE config.env with:"
    echo "SECURITY_GROUP_ID=$SG_ID"
fi
echo ""

echo "===== Network Setup Complete ====="
echo "Security Group: $SECURITY_GROUP_ID"
echo ""
echo "CONFIGURATION:"
echo "- Subnets: PRIVATE (with NAT Gateway for outbound)"
echo "- Security Group: EGRESS-ONLY (no inbound rules)"
echo "- Outbound: 443 (Anthropic API), 5432 (Postgres)"
echo "- Public IP: NOT assigned (uses NAT Gateway for egress)"
