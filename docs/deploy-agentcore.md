# Deploying the control plane on Amazon Bedrock AgentCore

We host the control-plane MCP server on **AgentCore Runtime** and front it with
**AgentCore Gateway**. AgentCore provides the authenticated HTTPS endpoint, inbound
OAuth, scaling, and per-session microVM isolation — so the bespoke ALB / ECS / OAuth
resource-server / Terraform from the earlier approach is retired.

```
 Claude plugin ──Bearer JWT──▶ AgentCore Gateway ──▶ AgentCore Runtime (our MCP server)
                                  (inbound authz,        0.0.0.0:8000/mcp, stateless        │
                                   tool catalog,         FastMCP; identity hint only)        ▼
                                   outbound creds)                                       Aiven Postgres
        IdP (Cognito/Auth0/Okta/Entra) — AgentCore validates the JWT at the edge      (sunstead_control DB,
                                                                                       non-superuser roles)
```

## What AgentCore handles vs what we keep

| AgentCore provides | We keep / own |
|---|---|
| HTTPS endpoint, scaling, microVM session isolation (≤8h) | the MCP tool surface (`ops.py`, `mcp.py`, 11 tools) |
| Inbound OAuth: validates the JWT, serves `401 + RFC 9728` PRM | per-tool scope authZ (`auth.TOOL_SCOPES` via `mcp._enforce`) |
| Outbound credential exchange (Gateway, RFC 8693) | Aiven role-brokering / truth boundary (`roles.py`, `sql/roles.sql`) |
| Observability (CloudWatch traces) | the autoresearch loop, the frozen pore/loss (untouched) |

The server only **decodes** the forwarded token to recover scopes/role (it does **not**
re-validate — AgentCore did). That's safe *only* behind AgentCore; the non-superuser
`sunstead_app` DB login is the hard backstop regardless (`runtime_app.py` header).

## Prerequisites
- Node 20+ (`agentcore` CLI is an npm package), Python 3.10+, AWS account + credentials.
- The Aiven `sunstead_app` DSN (ends `/sunstead_control`).

## Step A — Aiven non-superuser roles  ✅ done
Provisioned into a dedicated `sunstead_control` DB (brokered
`sunstead_readonly`/`operator`/`proposer`; serving login is non-superuser):
```bash
ADMIN_DSN='postgresql://avnadmin:…@…:11244/defaultdb?sslmode=require' \
    python scripts/provision_control_roles.py
```
It verifies the boundary (`rolsuper=False`, proposer denied `judgment` INSERT) and
writes the app DSN to a **gitignored** `app_dsn.secret` (masked in stdout). The app DSN
is `postgresql://sunstead_app:…@…:11244/sunstead_control?sslmode=require`.

**Rotate credentials** (do before going internet-facing, or if a DSN leaks): re-run the
command above — it ALTERs `sunstead_app`'s password to a fresh value without echoing it
(new DSN lands in `app_dsn.secret`). Rotate `avnadmin` separately in the Aiven console /
`avn service user-password-reset`.

## Step B — Inbound IdP (Cognito example)
AgentCore needs an OIDC **Discovery URL** + **Client ID** to validate inbound tokens:
```bash
export REGION=us-west-2 USERNAME=ops PASSWORD='<strong>'
# pool + resource server (control:* scopes) + machine & test clients + test user;
# prints Discovery URL, Client IDs, and a test Bearer token
source scripts/setup_cognito.sh
```
(Any OIDC IdP works — Auth0 with Dynamic Client Registration is convenient for the
Claude connector's auth-code flow; Cognito for machine/client-credentials callers.)

## Step C — Scaffold the AgentCore MCP project
See `agentcore/README.md`. In brief:
```bash
npm install -g @aws/agentcore
agentcore create --protocol MCP        # entrypoint -> cleanroom.control.server.runtime_mcp
```
Wire in: `requirements-runtime.txt`, the `cleanroom` package, the `CLEANROOM_PG_APP_DSN`
env (the sunstead_control DSN), and the IdP Discovery URL + Client ID from Step B.
Commit the generated `agentcore/agentcore.json` + `agentcore/aws-targets.json`.

Test locally first:
```bash
python -m cleanroom.control.server.runtime_mcp   # serves http://localhost:8000/mcp
agentcore dev                                     # CLI inspector + hot reload
```

## Step D — Deploy the Runtime
```bash
agentcore deploy        # packages, uploads, creates the runtime; prints an ARN
agentcore status
```
You get `arn:aws:bedrock-agentcore:REGION:ACCT:runtime/sunstead-control-xxxx`. The
invocation URL is
`https://bedrock-agentcore.REGION.amazonaws.com/runtimes/<URL-ENCODED-ARN>/invocations?qualifier=DEFAULT`.

## Step E — Front it with AgentCore Gateway
```bash
agentcore add gateway        # then `agentcore deploy`
```
Configure the Gateway with:
- **Inbound auth:** JWT (the same IdP) — Gateway validates the caller.
- **Target:** the Runtime MCP server from Step D (Gateway proxies + aggregates it;
  add more API/Lambda/MCP targets later for one unified tool catalog).
- **Outbound:** AgentCore Identity for on-behalf-of (RFC 8693) credential exchange if
  the server later calls third-party APIs on the user's behalf.

Gateway gives one unified MCP endpoint, dynamic tool listing with the caller's
identity, and centralized credential management.

## Step F — Point the plugin at it
Edit `plugin/.mcp.remote.json` → set `url` to the **Gateway** endpoint (or the Runtime
invocation URL for Runtime-only). Claude's connector does the OAuth handshake via the
`.well-known/oauth-protected-resource` document AgentCore serves.

## CI/CD
`.github/workflows/deploy.yml` runs `agentcore deploy` on push to `main` (OIDC, no
static keys), **gated behind the `DEPLOY_ENABLED=true` repo variable** so it stays
skipped until bootstrap is done. One-time GitHub config:
- **Secrets:** `AWS_DEPLOY_ROLE_ARN` (an IAM role trusting GitHub OIDC with AgentCore +
  ECR/S3 deploy perms).
- **Variables:** `AWS_REGION`, `DEPLOY_ENABLED=true`.
- A `production` Environment with required reviewers to gate deploys.

`ci.yml` runs the test suite on every PR/push (unchanged).

## The dispatch worker
AgentCore Runtime supports long-running invocations (≤8h), so a dispatched run can
execute in-session (`CLEANROOM_DISPATCH_MODE=thread`). For fire-and-return at scale,
keep the queue split (`CLEANROOM_DISPATCH_MODE=queue`) and run
`python -m cleanroom.control.worker` as a separate process (its own AgentCore runtime,
a small ECS/Fargate task, or a scheduled job) against the same `sunstead_control` DB.

## Honesty / scope edges
- `agentcore.json` is **CLI-generated** (schema owned by the CLI version) — we don't
  commit a hand-written one; generate with `agentcore create`. The deploy workflow is a
  skeleton until that config + AWS exist.
- The runtime identity middleware **decodes without verifying** — correct only behind
  AgentCore's edge validation; never expose the runtime app directly.
- Gateway/Runtime specifics (env wiring, IAM, packaging the `cleanroom` package) are
  validated on first real `agentcore deploy`, not in this environment.
- Rotate the `avnadmin` DSN before anything is internet-facing.
