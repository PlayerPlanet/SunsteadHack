#!/usr/bin/env bash
# Add a *dashboard user-registration* path to the existing Cognito user pool that
# AgentCore validates against. This is the human-facing complement to setup_cognito.sh
# (which set up machine client_credentials): here we add a hosted-UI domain, an
# authorization-code + PKCE app client for the dashboard BFF (Auth.js), and the groups
# that map a registered user to a brokered Postgres role.
#
#   registration  -> Cognito user + group (operators / proposers / default=viewer)
#   login (BFF)    -> authorization_code+PKCE -> access token carrying cognito:groups
#   AgentCore      -> validates token, forwards Authorization (requestHeaderAllowlist)
#   control plane  -> cleanroom.control.server.auth maps cognito:groups -> db_role
#                     -> SET ROLE in Postgres (the truth boundary actually enforces).
#
# We DELIBERATELY do not grant the app client any control:* resource-server scopes:
# the dashboard user's *role* (from their group) implies their scopes server-side
# (auth._ROLE_SCOPES). Machine callers that need precise scopes use setup_cognito.sh.
#
# Self-registration: a user pool created without AllowAdminCreateUserOnly=true (the
# default, as setup_cognito.sh leaves it) already permits hosted-UI sign-up, so we do
# NOT call update-user-pool (it is a full replace and would clobber other settings).
#
# Requires: aws CLI (uses --query, no jq). Run AFTER setup_cognito.sh (needs POOL_ID).
#
#   REGION=us-east-1 POOL_ID=us-east-1_xxxx \
#   DOMAIN_PREFIX=sunstead-control-528081867249 \
#   DASHBOARD_URL=https://your-dashboard.vercel.app \
#     source scripts/setup_cognito_dashboard.sh
#
# `source` so DASH_CLIENT_ID lands in your shell. The client secret is written to a
# gitignored file (dashboard_client.secret), never echoed — paste it into the BFF env.
set -euo pipefail

: "${REGION:?set REGION, e.g. us-east-1}"
: "${POOL_ID:?set POOL_ID from setup_cognito.sh (e.g. us-east-1_8d4jfqwov)}"
: "${DOMAIN_PREFIX:?set DOMAIN_PREFIX — globally-unique Cognito hosted-UI subdomain}"
: "${DASHBOARD_URL:?set DASHBOARD_URL — the dashboard origin, e.g. https://app.example.com}"
RESOURCE_ID="${RESOURCE_ID:-sunstead-control}"
SECRET_FILE="${SECRET_FILE:-dashboard_client.secret}"

# Local dev callback too, so the BFF works on localhost and in prod. Auth.js mounts the
# Cognito callback at /api/auth/callback/cognito.
CALLBACKS="${DASHBOARD_URL%/}/api/auth/callback/cognito http://localhost:3000/api/auth/callback/cognito"
LOGOUTS="${DASHBOARD_URL%/} http://localhost:3000"

# 1) Hosted-UI domain (the OAuth authorize/token/login endpoints for the BFF).
#    Idempotent: a 'domain already exists' error is fine.
aws cognito-idp create-user-pool-domain \
  --user-pool-id "$POOL_ID" --domain "$DOMAIN_PREFIX" --region "$REGION" \
  >/dev/null 2>&1 && echo "created hosted-UI domain: $DOMAIN_PREFIX" \
  || echo "hosted-UI domain $DOMAIN_PREFIX already exists (or name taken) — continuing"

# 2) Groups whose names match auth.DEFAULT_GROUP_ROLE_MAP. Default (no group) = viewer
#    => sunstead_readonly. Promote a user by adding them to a group (precedence: lower
#    number wins for AWS-cred mapping; irrelevant to us — we take the highest db_role).
create_group () {  # name, precedence, description
  aws cognito-idp create-group --user-pool-id "$POOL_ID" --group-name "$1" \
    --precedence "$2" --description "$3" --region "$REGION" >/dev/null 2>&1 \
    && echo "created group: $1" || echo "group $1 exists — continuing"
}
create_group "sunstead-operators" 1 "Dispatch/cancel runs, adjudicate escalations (sunstead_operator)"
create_group "sunstead-proposers" 2 "Register tasks, write experiments (sunstead_proposer)"
create_group "sunstead-viewers"   3 "Read-only governance log + curves (sunstead_readonly)"

# 3) Dashboard BFF app client: authorization_code + PKCE, OIDC scopes only (no control:*).
#    --generate-secret => a confidential client (Auth.js Cognito provider uses the secret
#    on the server side; PKCE still applies). Refresh-token flow for silent renewal.
DASH_CLIENT_ID=$(aws cognito-idp create-user-pool-client \
  --user-pool-id "$POOL_ID" --client-name "sunstead-dashboard" \
  --generate-secret \
  --allowed-o-auth-flows code \
  --allowed-o-auth-flows-user-pool-client \
  --allowed-o-auth-scopes openid email profile \
  --callback-urls $CALLBACKS \
  --logout-urls $LOGOUTS \
  --supported-identity-providers COGNITO \
  --explicit-auth-flows "ALLOW_REFRESH_TOKEN_AUTH" \
  --region "$REGION" --query 'UserPoolClient.ClientId' --output text)
export DASH_CLIENT_ID

# Pull the secret WITHOUT echoing it; stash in a gitignored file (matches the app_dsn
# pattern). chmod best-effort (no-op on Windows filesystems).
aws cognito-idp describe-user-pool-client \
  --user-pool-id "$POOL_ID" --client-id "$DASH_CLIENT_ID" \
  --region "$REGION" --query 'UserPoolClient.ClientSecret' --output text > "$SECRET_FILE"
chmod 600 "$SECRET_FILE" 2>/dev/null || true

ISSUER="https://cognito-idp.$REGION.amazonaws.com/$POOL_ID"
DOMAIN_URL="https://$DOMAIN_PREFIX.auth.$REGION.amazoncognito.com"

echo
echo "================ dashboard auth wired ================"
echo "Issuer (OIDC)     : $ISSUER"
echo "Discovery URL     : $ISSUER/.well-known/openid-configuration"
echo "Hosted-UI domain  : $DOMAIN_URL"
echo "Dashboard client  : $DASH_CLIENT_ID   (exported as \$DASH_CLIENT_ID)"
echo "Client secret     : written to $SECRET_FILE (gitignored; do NOT paste in chat)"
echo "Groups            : sunstead-operators | sunstead-proposers | sunstead-viewers"
echo
echo "NEXT — two manual steps to make this live:"
echo "  1) Allow this client at the AgentCore edge: add \"$DASH_CLIENT_ID\" to"
echo "     sunsteadcontrol/agentcore/agentcore.json -> authorizerConfiguration"
echo "     .customJwtAuthorizer.allowedClients, then redeploy:"
echo "         cd sunsteadcontrol && agentcore deploy --yes"
echo "     (the redeploy also applies requestHeaderAllowlist:[\"Authorization\"]; verify"
echo "      with:  AGENT_RUNTIME_ID=... python scripts/verify_header_forwarding.py )"
echo "  2) Hand the BFF agent docs/dashboard-auth.md + these values (issuer, client id,"
echo "     secret file). New sign-ups are viewers (read-only) until added to a group:"
echo "         aws cognito-idp admin-add-user-to-group --user-pool-id $POOL_ID \\"
echo "           --username <user> --group-name sunstead-operators --region $REGION"
echo "======================================================"
