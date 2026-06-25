"""Cognito PreSignUp trigger: auto-confirm self-registrations (username + password only).

This pool uses a username as the sign-in id and email is an OPTIONAL attribute, so the
Hosted UI sign-up form shows only username + password. Without an email/phone to verify,
a self-signup would otherwise be stuck UNCONFIRMED. This trigger confirms the user
immediately, so registration "just works" and the user lands as a read-only viewer
(no elevated access until an operator adds them to the sunstead-operators group).

Security note: auto-confirm grants nothing beyond read-only — the brokered role
(sunstead_readonly) and the runtime's SET ROLE are the real boundary. Open registration
to a viewer is intentional for this dashboard.

Deployed + wired by scripts/setup_presignup_autoconfirm.sh.
"""


def lambda_handler(event, context):
    event.setdefault("response", {})["autoConfirmUser"] = True
    # If the user did supply an email/phone, mark it verified so recovery works.
    attrs = event.get("request", {}).get("userAttributes", {})
    if attrs.get("email"):
        event["response"]["autoVerifyEmail"] = True
    if attrs.get("phone_number"):
        event["response"]["autoVerifyPhone"] = True
    return event
