# Deploying the control plane so plugins can call it on AWS (Story G)

This turns the Story-D control plane from a **local stdio subprocess** into a **remote,
authenticated, horizontally-scalable service** a Claude plugin can reach over the
network. Five layers, in the order they matter.

```
 Claude plugin ──HTTPS──▶ ALB (TLS) ──▶ ECS: web (streamable-HTTP MCP + OAuth)
                                              │  enqueue (state='queued')
                                              ▼
                                         Aiven Postgres  ◀── ECS: worker (claims via
                                         (run queue + KB)      FOR UPDATE SKIP LOCKED,
                                                               runs the loop)
        Authorization Server (Cognito) issues/validates access tokens (JWKS)
```

## What changed in the app (this PR)

| Layer | Before | After |
|---|---|---|
| Transport | stdio subprocess (`server.run()`) | streamable-HTTP ASGI app (`python -m cleanroom.control.server.http`); stdio still works for local |
| Auth | none (raw avnadmin DSN in env) | OAuth 2.1 resource server: JWKS-validated bearer tokens, per-tool scopes, RFC 9728 metadata |
| DB identity | superuser `avnadmin` | non-superuser `sunstead_app` + per-caller `SET ROLE`; **boot refuses superuser** |
| Execution | daemon thread in the MCP process | `dispatch(mode="queue")` → separate worker claims from PG |
| Packaging | — | Dockerfile, docker-compose (local parity), Terraform (ECS/ALB/Cognito/Secrets) |

The **bright line is intact**: none of this touches the frozen pore/loss. Auth gates
*who may operate the plane*; it never scores anything.

## Local parity (run the whole topology on your machine)

```bash
docker compose up --build
curl localhost:8000/healthz                 # {"status":"ok"}
curl localhost:8000/.well-known/oauth-protected-resource   # 404 in insecure dev mode
```

Compose runs auth in **insecure dev mode** (`CLEANROOM_ALLOW_INSECURE=1`) because there
is no IdP locally; it exercises the transport + web/worker split + role login end to
end. Auth itself is covered by unit tests (`tests/test_control_oauth.py`,
`tests/test_control_http_app.py`).

## AWS deploy

### 0. Prereqs
- An ACM cert for your `domain_name` in the ALB's region.
- An ECR repo with the image built from this repo's `Dockerfile`.
- The Aiven service reachable with `sslmode=require`.

### 1. Provision the non-superuser roles on Aiven (GATED — you run this once, as admin)
The serving process must not be `avnadmin`. Apply the role migration as a superuser:
```bash
psql "$ADMIN_DSN" -v app_password="$APP_PWD" -f sql/roles.sql   # creates sunstead_app + brokered roles
psql "$ADMIN_DSN" -f cleanroom/db/schema.sql                     # fresh KB, OR:
psql "$ADMIN_DSN" -f sql/run_queue.sql                           # migrate an existing run table
```
Build the **app DSN** from the `sunstead_app` login (NOT avnadmin):
`postgresql://sunstead_app:<APP_PWD>@<host>:11244/defaultdb?sslmode=require`

> ⚠️ This is the only step that runs DDL against the shared `sunstead-pg-bench` service.
> It is deliberately manual and not run by any code in this repo.

### 2. Build + push the image
```bash
docker build -t "$ECR/sunstead-control:latest" .
docker push "$ECR/sunstead-control:latest"
```

### 3. Terraform (review the plan first — it is unvalidated in CI)
```bash
cd infra/terraform
terraform init
terraform plan \
  -var domain_name=control.sunstead.example \
  -var acm_certificate_arn=arn:aws:acm:... \
  -var container_image="$ECR/sunstead-control:latest" \
  -var app_dsn_secret_value="$APP_DSN"
# reconcile, then: terraform apply
```
This stands up the VPC/ALB/Fargate web+worker, the Secrets Manager entry for the app
DSN, and a Cognito pool as the Authorization Server. Point `domain_name` at the
`alb_dns_name` output. The web tasks get `OAUTH_*` (issuer/jwks/audience) and the
secret app DSN injected; **the superuser DSN never reaches the tasks.**

### 4. Point the plugin at it
Use `plugin/.mcp.remote.json` (set `url` to `https://<domain_name>/mcp`) instead of the
stdio `plugin/.mcp.json`. Claude's connector handles the OAuth handshake by reading the
server's `/.well-known/oauth-protected-resource`.

## CI/CD (GitHub Actions)

Three workflows under `.github/workflows/`:

| Workflow | Trigger | Does |
|---|---|---|
| `ci.yml` | PR + push to main | pytest, `terraform fmt -check`/`validate`, `docker build` (no push) |
| `deploy.yml` | push to `main` (app paths) + manual | OIDC → build+push to ECR (`:sha` + `:latest`) → `ecs update-service --force-new-deployment` for web+worker → wait stable |
| `infra.yml` | manual only (plan/apply input) | `terraform plan`/`apply` for VPC/ALB/ECS/Cognito |

**App deploys auto-roll on merge to main; infra never does** (manual `infra.yml` only),
so a code merge can't silently mutate infrastructure.

### One-time setup
1. `terraform apply` once (includes `ecr.tf` + `github_oidc.tf`). Grab the outputs:
   `ecr_repository_url`, `github_deploy_role_arn`.
2. Set `var.container_image = "<ecr_repository_url>:latest"` so force-new-deployment rolls the new image.
3. In GitHub repo settings:
   - **Secrets:** `AWS_DEPLOY_ROLE_ARN` (= `github_deploy_role_arn`), `APP_DSN`, `ACM_CERTIFICATE_ARN`.
   - **Variables:** `AWS_REGION`, `ECR_REPOSITORY` (repo name), `ECS_CLUSTER`, `WEB_SERVICE`, `WORKER_SERVICE`, `DOMAIN_NAME`, `CONTAINER_IMAGE`, and **`DEPLOY_ENABLED=true`** (the deploy job stays skipped until this is set — so merges to main don't fail before AWS exists).
   - Add a `production` **Environment** with required reviewers to gate deploys.
4. For shared state, configure a remote tf backend (S3+DynamoDB) before relying on `infra.yml`.

Auth is OIDC — **no static AWS keys** in the repo. The deploy role trusts only
`repo:<owner>/<name>:*` and is scoped to ECR push + ECS rollout of these two services.

## How auth flows at request time
1. Client calls `/mcp` with `Authorization: Bearer <access_token>`.
2. `BearerAuthMiddleware` validates it (RS256 against the Cognito JWKS, checks
   `iss`/`aud`/`exp`) and builds a `Principal` (subject, scopes, brokered `db_role`).
   On failure: `401` + `WWW-Authenticate: Bearer resource_metadata=…`.
3. The tool wrapper enforces the tool's scope (`control:dispatch` for `dispatch_run`, …).
4. The brokered role bounds what the request can do **in Postgres**, beneath the app.

## Honesty / scope boundaries (don't overclaim)
- **Per-request `SET ROLE` isolation between tenants** is provided by the primitives
  (`roles.role_scope`) and enforced-by-default least privilege, but threading a distinct
  role onto the singleton serving connection per request is the documented next step;
  today the concrete guarantees are: non-superuser serving login (boot-enforced),
  per-tool scope, and the SQL-level GRANTs. With PgBouncer this **requires session
  pooling** (or direct `:11244`) so roles don't leak across pooled transactions.
- **Cross-process cancel of a *running* queued run** needs a DB cancel flag (the
  cancel Event is per-process). Cancelling a still-`queued` run works (the web marks it
  cancelled; the worker's claim only takes `queued` rows).
- Terraform here is **review-only** — authored coherent but not `plan`/`apply`-validated
  in this environment. VPC uses public subnets (hackathon-grade); move tasks to private
  subnets + NAT for production.
- **Rotate the `avnadmin` DSN** that has appeared in development transcripts before this
  is internet-facing.
