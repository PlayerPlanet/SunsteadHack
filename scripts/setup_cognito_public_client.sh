#!/usr/bin/env bash
# Create a PUBLIC (no-secret) Cognito app client for the *shipped* Claude Code plugin.
#
# Why a second client: the dashboard client (setup_cognito_dashboard.sh) is CONFIDENTIAL
# — it has a secret. A secret can't ship inside a downloadable plugin (anyone who has the
# file has the secret). The OAuth answer for a distributable native/CLI app is a PUBLIC
# client: no secret, authorization-code + PKCE only. PKCE (S256) is what protects the
# flow instead of a secret, so the client_id is safe to bake into plugin/.mcp.remote.json
# and hand to the world. A random person who downloads the plugin uses THIS client_id;
# they sign in as themselves and land as a read-only viewer until an operator promotes
# their Cognito user to a group.
#
#   REGION=us-east-1 POOL_ID=us-east-1_8d4jfqwov bash scripts/setup_cognito_public_client.sh
#
# Prints the new public client_id. Then:
#   1) add it to sunsteadcontrol/agentcore/agentcore.json -> allowedClients
#   2) cd sunsteadcontrol && agentcore deploy --yes
#   3) it goes into plugin/.mcp.remote.json (no secret) — env-overridable for BYO pools.
set -euo pipefail

REGION="${REGION:-us-east-1}"
POOL_ID="${POOL_ID:-us-east-1_8d4jfqwov}"
CLIENT_NAME="${CLIENT_NAME:-sunstead-control-plugin}"
# Claude Code's remote-MCP OAuth loopback redirect is http://localhost:<callbackPort>/callback.
# Must match plugin/.mcp.remote.json oauth.callbackPort (8080).
CALLBACK="${CALLBACK:-http://localhost:8080/callback}"

CLIENT_ID=$(aws cognito-idp create-user-pool-client \
  --user-pool-id "$POOL_ID" --client-name "$CLIENT_NAME" \
  --no-generate-secret \
  --allowed-o-auth-flows code \
  --allowed-o-auth-flows-user-pool-client \
  --allowed-o-auth-scopes openid email profile \
  --callback-urls "$CALLBACK" \
  --supported-identity-providers COGNITO \
  --explicit-auth-flows "ALLOW_REFRESH_TOKEN_AUTH" \
  --region "$REGION" --query 'UserPoolClient.ClientId' --output text)

echo
echo "================ public plugin client created ================"
echo "Public client_id : $CLIENT_ID    (NO secret — safe to ship)"
echo "Pool             : $POOL_ID"
echo "Callback         : $CALLBACK"
echo "Scopes           : openid email profile (no control:* — role comes from group)"
echo
echo "NEXT:"
echo "  1) Add \"$CLIENT_ID\" to sunsteadcontrol/agentcore/agentcore.json"
echo "     -> runtimes[0].authorizerConfiguration.customJwtAuthorizer.allowedClients"
echo "  2) cd sunsteadcontrol && agentcore deploy --yes"
echo "  3) Tell me the id and I'll bake it into plugin/.mcp.remote.json."
echo "=============================================================="
