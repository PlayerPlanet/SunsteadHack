#!/usr/bin/env bash
# Bootstrap an Amazon Cognito user pool as the OIDC IdP that AgentCore validates inbound
# tokens against. Creates: a user pool, a resource server exposing the control:* scopes,
# a machine (client-credentials) app client, and a test user for a quick bearer token.
#
# Prints the values AgentCore needs: Discovery URL + Client ID (for `agentcore create`)
# and a Bearer token (for a smoke test). Requires: aws CLI, jq.
#
#   REGION=us-west-2 USERNAME=ops PASSWORD='<strong>' source scripts/setup_cognito.sh
#
# `source` so the exported vars (POOL_ID, CLIENT_ID, BEARER_TOKEN) land in your shell.
set -euo pipefail

: "${REGION:?set REGION, e.g. us-west-2}"
: "${USERNAME:?set USERNAME for the test user}"
: "${PASSWORD:?set PASSWORD for the test user (>=8 chars)}"
RESOURCE_ID="${RESOURCE_ID:-sunstead-control}"   # OAuth audience identifier

POOL_ID=$(aws cognito-idp create-user-pool \
  --pool-name "sunstead-control-pool" \
  --policies '{"PasswordPolicy":{"MinimumLength":8}}' \
  --region "$REGION" | jq -r '.UserPool.Id')

# Resource server exposes the per-tool scopes the MCP server enforces (auth.TOOL_SCOPES).
aws cognito-idp create-resource-server \
  --user-pool-id "$POOL_ID" \
  --identifier "$RESOURCE_ID" \
  --name "sunstead-control" \
  --scopes \
     ScopeName=control:read,ScopeDescription="read tasks/runs/curves/boundary" \
     ScopeName=control:register,ScopeDescription="register tasks" \
     ScopeName=control:dispatch,ScopeDescription="dispatch/cancel runs" \
     ScopeName=control:adjudicate,ScopeDescription="adjudicate escalations" \
  --region "$REGION" >/dev/null

# Machine caller: client-credentials with all scopes (tighten per-caller in prod).
MACHINE_CLIENT_ID=$(aws cognito-idp create-user-pool-client \
  --user-pool-id "$POOL_ID" \
  --client-name "sunstead-machine" \
  --generate-secret \
  --allowed-o-auth-flows client_credentials \
  --allowed-o-auth-flows-user-pool-client \
  --allowed-o-auth-scopes \
     "$RESOURCE_ID/control:read" "$RESOURCE_ID/control:register" \
     "$RESOURCE_ID/control:dispatch" "$RESOURCE_ID/control:adjudicate" \
  --region "$REGION" | jq -r '.UserPoolClient.ClientId')

# Interactive client + test user for a quick USER_PASSWORD bearer token.
export CLIENT_ID=$(aws cognito-idp create-user-pool-client \
  --user-pool-id "$POOL_ID" --client-name "sunstead-test" --no-generate-secret \
  --explicit-auth-flows "ALLOW_USER_PASSWORD_AUTH" "ALLOW_REFRESH_TOKEN_AUTH" \
  --region "$REGION" | jq -r '.UserPoolClient.ClientId')
aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username "$USERNAME" \
  --region "$REGION" --message-action SUPPRESS >/dev/null
aws cognito-idp admin-set-user-password --user-pool-id "$POOL_ID" --username "$USERNAME" \
  --password "$PASSWORD" --region "$REGION" --permanent >/dev/null
export BEARER_TOKEN=$(aws cognito-idp initiate-auth --client-id "$CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters "USERNAME=$USERNAME,PASSWORD=$PASSWORD" \
  --region "$REGION" | jq -r '.AuthenticationResult.AccessToken')

export POOL_ID MACHINE_CLIENT_ID
echo "Discovery URL : https://cognito-idp.$REGION.amazonaws.com/$POOL_ID/.well-known/openid-configuration"
echo "Audience      : $RESOURCE_ID  (set OAUTH_AUDIENCE/OAUTH_RESOURCE if self-hosting)"
echo "Test Client ID: $CLIENT_ID   (use at \`agentcore create\`)"
echo "Machine Client: $MACHINE_CLIENT_ID  (client_credentials; secret in the console)"
echo "Bearer token (test): exported as \$BEARER_TOKEN"
