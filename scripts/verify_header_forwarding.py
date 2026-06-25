#!/usr/bin/env python3
"""Verify the deployed AgentCore runtime forwards the Authorization header.

Read-only: calls GetAgentRuntime and asserts requestHeaderConfiguration's allowlist
contains "Authorization". Until this is true, the runtime authenticates callers at the
edge but never forwards the token to the container — so per-tool scope enforcement and
per-caller SET ROLE (cleanroom.control.server) are dormant and every caller runs with
the same uniform privilege. After `agentcore deploy` picks up requestHeaderAllowlist
from agentcore.json, this should print OK.

Shells out to the AWS CLI (already used by the setup scripts) so it needs no boto3.

Usage:
  AWS_REGION=us-east-1 AGENT_RUNTIME_ID=sunsteadcontrol_sunstead_control-u9zi87DjdX \
    python scripts/verify_header_forwarding.py
  # or pass the full ARN:
  AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:ACCT:runtime/<id> python scripts/verify_header_forwarding.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def _runtime_id() -> str:
    rid = os.environ.get("AGENT_RUNTIME_ID")
    if rid:
        return rid.strip()
    arn = os.environ.get("AGENT_ARN")
    if arn and ":runtime/" in arn:
        return arn.split(":runtime/", 1)[1].strip()
    sys.exit("set AGENT_RUNTIME_ID (or AGENT_ARN) to the runtime to inspect")


def main() -> int:
    region = os.environ.get("AWS_REGION", "us-east-1")
    rid = _runtime_id()
    try:
        out = subprocess.run(
            [
                "aws", "bedrock-agentcore-control", "get-agent-runtime",
                "--agent-runtime-id", rid, "--region", region, "--output", "json",
            ],
            check=True, capture_output=True, text=True,
        ).stdout
    except FileNotFoundError:
        sys.exit("aws CLI not found on PATH — install it or run the GetAgentRuntime call manually")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"GetAgentRuntime failed:\n{exc.stderr.strip()}")

    resp = json.loads(out)
    cfg = resp.get("requestHeaderConfiguration") or {}
    allowlist = cfg.get("requestHeaderAllowlist") or []
    forwards_auth = any(h.lower() == "authorization" for h in allowlist)

    print(f"runtime           : {rid}")
    print(f"status            : {resp.get('status')}  (version {resp.get('agentRuntimeVersion')})")
    print(f"authorizerType    : {'CUSTOM_JWT' if resp.get('authorizerConfiguration') else 'IAM (SigV4)'}")
    print(f"header allowlist  : {allowlist or '(none — Authorization NOT forwarded)'}")
    if forwards_auth:
        print("[ok] Authorization is forwarded -> per-tool scope + SET ROLE are LIVE")
        return 0
    print(
        "[!!] Authorization NOT forwarded -> app-level authZ is dormant; the runtime "
        "runs every caller as the base sunstead_app login.\n"
        "     Fix: ensure agentcore.json runtime has \"requestHeaderAllowlist\": "
        "[\"Authorization\"], then re-run `agentcore deploy` from sunsteadcontrol/."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
