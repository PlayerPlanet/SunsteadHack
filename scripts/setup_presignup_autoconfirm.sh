#!/usr/bin/env bash
# Deploy + wire the PreSignUp auto-confirm Lambda so dashboard self-registration works
# with just username + password (this pool's Hosted UI doesn't collect email, and email
# can't be made a required attribute after pool creation). Idempotent; safe to re-run.
#
# APPROVAL-GATED: creates an IAM role + Lambda and updates the shared Cognito pool's
# trigger config. Run it yourself:
#   REGION=us-east-1 POOL_ID=us-east-1_8d4jfqwov bash scripts/setup_presignup_autoconfirm.sh
set -euo pipefail

REGION="${REGION:-us-east-1}"
POOL_ID="${POOL_ID:-us-east-1_8d4jfqwov}"
FN="${FN:-sunstead-presignup-autoconfirm}"
ROLE_NAME="${ROLE_NAME:-sunstead-presignup-lambda-role}"
ACCT=$(aws sts get-caller-identity --query Account --output text)
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1) Execution role (basic Lambda logging only).
aws iam create-role --role-name "$ROLE_NAME" \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
  >/dev/null 2>&1 && echo "created role $ROLE_NAME" || echo "role $ROLE_NAME exists"
aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole >/dev/null 2>&1 || true
ROLE_ARN="arn:aws:iam::$ACCT:role/$ROLE_NAME"

# 2) Package + create/update the function. Build locally and hand the AWS CLI a path it
#    can resolve — on Windows the native aws.exe can't read git-bash's /tmp, so convert
#    to a Windows path with cygpath when available.
BUILD="$HERE/.lambda-build"
mkdir -p "$BUILD"
cp "$HERE/cognito_presignup_autoconfirm.py" "$BUILD/index.py"
( cd "$BUILD" && rm -f presignup.zip && zip -q -j presignup.zip index.py )
ZIP_PATH="$BUILD/presignup.zip"
[ -f "$ZIP_PATH" ] || { echo "ERROR: zip not produced at $ZIP_PATH (is 'zip' installed?)"; exit 1; }
if command -v cygpath >/dev/null 2>&1; then ZIP_REF="fileb://$(cygpath -w "$ZIP_PATH")"; else ZIP_REF="fileb://$ZIP_PATH"; fi

if aws lambda get-function --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FN" --zip-file "$ZIP_REF" --region "$REGION" >/dev/null
  echo "updated function $FN"
else
  echo "waiting for role to propagate…"; sleep 10
  aws lambda create-function --function-name "$FN" --runtime python3.12 \
    --handler index.lambda_handler --role "$ROLE_ARN" \
    --zip-file "$ZIP_REF" --region "$REGION" >/dev/null
  echo "created function $FN"
fi
rm -rf "$BUILD"
FN_ARN="arn:aws:lambda:$REGION:$ACCT:function:$FN"

# 3) Let Cognito invoke it.
aws lambda add-permission --function-name "$FN" --statement-id cognito-presignup \
  --action lambda:InvokeFunction --principal cognito-idp.amazonaws.com \
  --source-arn "arn:aws:cognito-idp:$REGION:$ACCT:userpool/$POOL_ID" --region "$REGION" \
  >/dev/null 2>&1 && echo "granted Cognito invoke" || echo "invoke permission already present"

# 4) Wire the trigger. update-user-pool is full-replace, so re-supply current settings.
aws cognito-idp update-user-pool --user-pool-id "$POOL_ID" --region "$REGION" \
  --lambda-config "{\"PreSignUp\":\"$FN_ARN\"}" \
  --auto-verified-attributes email \
  --policies '{"PasswordPolicy":{"MinimumLength":8,"RequireUppercase":false,"RequireLowercase":false,"RequireNumbers":false,"RequireSymbols":false,"TemporaryPasswordValidityDays":7}}' \
  --account-recovery-setting '{"RecoveryMechanisms":[{"Priority":1,"Name":"verified_email"},{"Priority":2,"Name":"verified_phone_number"}]}' \
  --admin-create-user-config '{"AllowAdminCreateUserOnly":false,"UnusedAccountValidityDays":7}' \
  --email-configuration '{"EmailSendingAccount":"COGNITO_DEFAULT"}' \
  --verification-message-template '{"DefaultEmailOption":"CONFIRM_WITH_CODE"}'

echo
echo "✓ PreSignUp auto-confirm wired. Self-registration now needs only username + password."
echo "  New users are read-only viewers; promote with:"
echo "    aws cognito-idp admin-add-user-to-group --user-pool-id $POOL_ID --username <u> --group-name sunstead-operators --region $REGION"
