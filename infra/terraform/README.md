# infra/terraform — control-plane on AWS (review-only)

Stands up the deployment-grade control plane: VPC + ALB(TLS) + ECS Fargate (web +
worker) + Secrets Manager (app DSN) + Cognito (OAuth Authorization Server).

> **Review-only.** This HCL was authored to be coherent and idiomatic but has **not**
> been `terraform plan`/`apply`-validated in the environment it was written in. Run
> `terraform init && terraform plan` and reconcile before any apply.

## Inputs you must supply
| var | what |
|---|---|
| `domain_name` | FQDN you serve on; also the OAuth audience/resource |
| `acm_certificate_arn` | validated ACM cert for `domain_name`, in the ALB region |
| `container_image` | ECR URI built from the repo `Dockerfile` |
| `app_dsn_secret_value` | the **non-superuser** `sunstead_app` Aiven DSN (never avnadmin) |

## Order of operations
1. Provision Aiven roles + schema out-of-band (`sql/roles.sql`, `sql/run_queue.sql`) — see `docs/deploy-aws.md`.
2. Build + push the image to ECR.
3. `terraform apply` here.
4. Point `domain_name` at the `alb_dns_name` output.
5. Configure the plugin with `plugin/.mcp.remote.json`.

## Files
- `vpc.tf` — VPC, 2 public subnets, ALB + task security groups
- `alb.tf` — public ALB, HTTPS listener, `/healthz` target group
- `ecs.tf` — cluster, web + worker task defs/services, log group
- `cognito.tf` — user pool, resource server (the `control:*` scopes), machine client
- `secrets.tf` — app DSN in Secrets Manager
- `iam.tf` — execution role (image pull + secret read) + task role
- `outputs.tf` — ALB DNS, MCP URL, OAuth issuer/JWKS, Cognito token endpoint

## Production hardening (not done here)
- Move tasks to private subnets + NAT; restrict task egress to Aiven + Cognito.
- Add autoscaling policies; add WAF on the ALB; enable access logs.
- Per-request `SET ROLE` tenant isolation on the serving connection (see runbook).
