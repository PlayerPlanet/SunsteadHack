"""OPTIONAL Cognito Pre-Token-Generation Lambda — stamp an explicit `db_role` claim.

The dashboard role path works WITHOUT this Lambda: the access token already carries
`cognito:groups`, and cleanroom.control.server.auth maps groups -> db_role server-side
(DEFAULT_GROUP_ROLE_MAP). Use this Lambda only if you want the IdP itself to be the
single source of role truth — it puts a clean `db_role` claim (and the implied
control:* scopes) into the token, which auth.principal_from_claims honors at highest
precedence.

CAVEAT (read before deploying): customizing the ACCESS token (adding claims/scopes via
the V2_0 trigger) requires the user pool to be on the **Essentials or Plus** feature
plan. On the default/Lite plan this trigger can only modify the ID token, which the
control plane does not read — so on Lite, prefer the no-Lambda cognito:groups path.

Deploy (Essentials+ pool):
  1. zip:   (cd scripts && zip /tmp/pretoken.zip cognito_pretoken_lambda.py)
  2. role:  an execution role with AWSLambdaBasicExecutionRole.
  3. create:
       aws lambda create-function --function-name sunstead-pretoken \
         --runtime python3.12 --handler cognito_pretoken_lambda.lambda_handler \
         --role <exec-role-arn> --zip-file fileb:///tmp/pretoken.zip --region $REGION
  4. allow Cognito to invoke it:
       aws lambda add-permission --function-name sunstead-pretoken \
         --statement-id cognito --action lambda:InvokeFunction \
         --principal cognito-idp.amazonaws.com \
         --source-arn arn:aws:cognito-idp:$REGION:$ACCT:userpool/$POOL_ID --region $REGION
  5. wire it as the pool's V2_0 pre-token trigger (LambdaConfig.PreTokenGenerationConfig
     with LambdaVersion=V2_0). Note: update-user-pool is a full replace — re-supply the
     pool's existing settings, or set the trigger in the Cognito console.

Keep the GROUP_ROLE_MAP / ROLE_SCOPES below in sync with cleanroom.control.server.auth.
"""

# group -> brokered Postgres role (mirror of auth.DEFAULT_GROUP_ROLE_MAP)
GROUP_ROLE_MAP = {
    "sunstead-operators": "sunstead_operator",
    "sunstead-proposers": "sunstead_proposer",
    "sunstead-viewers": "sunstead_readonly",
}
DEFAULT_ROLE = "sunstead_readonly"
ROLE_RANK = {"sunstead_readonly": 0, "sunstead_proposer": 1, "sunstead_operator": 2}

# role -> implied control:* scopes (mirror of auth._ROLE_SCOPES)
ROLE_SCOPES = {
    "sunstead_readonly": ["control:read"],
    "sunstead_proposer": ["control:read", "control:register"],
    "sunstead_operator": [
        "control:read", "control:register", "control:dispatch", "control:adjudicate",
    ],
}


def _role_for_groups(groups):
    mapped = [GROUP_ROLE_MAP[g] for g in (groups or []) if g in GROUP_ROLE_MAP]
    if not mapped:
        return DEFAULT_ROLE
    return max(mapped, key=lambda r: ROLE_RANK.get(r, -1))


def lambda_handler(event, context):
    """Cognito V2_0 pre-token trigger: add db_role + control:* scopes to the access token."""
    groups = (
        event.get("request", {})
        .get("groupConfiguration", {})
        .get("groupsToOverride", [])
    )
    role = _role_for_groups(groups)
    scopes = ROLE_SCOPES.get(role, ["control:read"])

    event.setdefault("response", {})["claimsAndScopeOverrideDetails"] = {
        "accessTokenGeneration": {
            "claimsToAddOrOverride": {"db_role": role},
            "scopesToAdd": scopes,
        }
    }
    return event
