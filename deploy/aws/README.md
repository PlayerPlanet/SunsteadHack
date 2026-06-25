# AWS Fargate Deployment for SunsteadHack

## Overview

This directory contains the IaC and automation for deploying the SunsteadHack proposer and full-run containers to AWS ECS/Fargate. The deployment uses **boto3 + AWS CLI scripts** (not Terraform or CDK).

### Topology

```
┌─────────────────────────────────────────────────────────────────┐
│ AWS Account (${AWS_ACCOUNT_ID})                                 │
│                                                                   │
│  ECR                        ECS Cluster (story-e-cluster)        │
│  ┌──────────────────┐      ┌──────────────────────────────────┐ │
│  │ proposer-image   │      │ Fargate Launch Type               │ │
│  │ (Phase 0)        │      │                                    │ │
│  └──────────────────┘      │ Task Definition                   │ │
│                             │ ┌────────────────────────────────┤ │
│  ┌──────────────────┐      │ │ Container: proposer / full-run   │ │
│  │ full-run-image   │      │ │ - VPC networking (awsvpc)        │ │
│  │ (Phase 2)        │      │ │ - Secrets: ANTHROPIC_API_KEY    │ │
│  └──────────────────┘      │ │ - Secrets: DB_DSN (read-only)   │ │
│                             │ │ - Env: TASK_ID, MODEL, ITERS   │ │
│  Secrets Manager            │ │ - Task Role: minimal (empty)    │ │
│  ┌──────────────────┐      │ │ - Exec Role: ECR + CloudWatch   │ │
│  │ ANTHROPIC_API_KEY│      │ │ - Security Group: egress only   │ │
│  │ DB_DSN           │      │ │   (no inbound, 443 + DB port)  │ │
│  └──────────────────┘      │ └────────────────────────────────┤ │
│                             │                                    │
│  VPC & Networking          │ Subnets (private, egress via NAT) │
│  ┌──────────────────┐      │                                    │
│  │ Egress-only SG   │      └──────────────────────────────────┘ │
│  │ (no inbound)     │      CloudWatch Logs                      │
│  │ 443 + DB port    │      ┌──────────────────┐                │
│  └──────────────────┘      │ /ecs/task/logs   │                │
│                             └──────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            Anthropic API   Aiven Postgres    (logs collected
           (HTTPS, 443)      read-only        by dispatcher)
```

## Prerequisites

1. **AWS Account** with CLI configured (`~/.aws/credentials`, `~/.aws/config`).
2. **AWS CLI v2** installed.
3. **Python 3.9+** with `boto3` installed.
4. **Docker** installed (for building/pushing images).
5. **VPC, Subnets, NAT Gateway** already configured in your AWS account (egress for ECS tasks).
6. **Aiven Postgres** database already provisioned with:
   - Read-only role `researcher_ro` with SELECT-only permissions.
   - Accessible from your VPC (security group rules, VPC endpoints, or bastion as needed).
7. **Anthropic API key** (set in environment: `$ANTHROPIC_API_KEY`).

## Deploy Order

Run the setup scripts in numeric order. Each is idempotent (safe to re-run):

```bash
cd deploy/aws

# 1. Copy and customize the config
cp config.env.example config.env
# Edit config.env with your AWS account ID, region, VPC details, etc.

# Source the config for subsequent scripts
source config.env

# 2. Create ECR repo and push the proposer image
bash setup/00-ecr.sh

# 3. Create and populate secrets in AWS Secrets Manager
bash setup/10-secrets.sh

# 4. Create IAM roles (task execution role + task role) with least-privilege policies
bash setup/20-iam.sh

# 5. Resolve/create VPC, subnets, security group (egress-only)
bash setup/30-network.sh

# 6. Register the Fargate task definition (Phase 0: proposer)
bash setup/40-taskdef.sh

# 7. Run a smoke test: one-off proposer task, verify output
bash setup/50-smoke.sh

# (Phase 2 awaits Story B: benchmark/pore/logclient integration)
# bash setup/60-register-full-run.sh    # TODO: Story B
```

## Configuration

### `config.env`

Copy `config.env.example` and customize:

```bash
# AWS region and account
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# ECR
ECR_REPO_NAME=sunsteadhack
ECR_IMAGE_TAG=proposer-phase0

# ECS
ECS_CLUSTER_NAME=story-e-cluster
TASK_FAMILY_NAME=sunsteadhack-proposer
TASK_ROLE_NAME=sunsteadhack-task-role
TASK_EXECUTION_ROLE_NAME=sunsteadhack-task-execution-role

# Network (must exist)
VPC_ID=vpc-abc123
SUBNET_ID_1=subnet-abc123
SUBNET_ID_2=subnet-def456
SECURITY_GROUP_ID=sg-abc123

# Secrets (will be created in AWS Secrets Manager if not found)
SECRET_ANTHROPIC_API_KEY_NAME=sunsteadhack/anthropic-api-key
SECRET_DB_DSN_NAME=sunsteadhack/db-dsn

# Read-only database (Phase 2 uses this; Phase 0 reads from local)
DB_DSN=postgresql://researcher_ro:PASS@db.example.com:5432/postgres
```

**Important:** Never commit real secrets or credentials to `config.env`. Always use environment variables (`$ANTHROPIC_API_KEY`) at deploy time.

## Required Environment Variables

Set these before running setup scripts:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."  # Anthropic API key (never echoed to logs)
export DB_DSN="postgresql://researcher_ro:pass@db.example.com:5432/postgres"  # Read-only DSN
```

## Deployment Phases

### Phase 0: Proposer (Index Discovery)

**Status:** Implemented and tested.

- Image: `proposer-container/Dockerfile`
- Entrypoint: `propose-entrypoint.sh`
- Input: `TASK` (query description), `MODEL` (Claude model)
- Output: Raw JSON `{"type":"index",...}` to stdout → captured in CloudWatch Logs
- Database access: Read-only Postgres via MCP
- **No mutations, no external dependencies, fully reproducible.**

**Smoke test** (`setup/50-smoke.sh`): launches one proposer task, waits for completion, retrieves logs, asserts valid `Candidate` JSON.

### Phase 1: Proposer + Benchmark

**Status:** Awaiting Story B (benchmark harness).

(To be deployed once the benchmark fixture is integrated.)

### Phase 2: Full Run Loop

**Status:** Stubbed with fixtures; awaiting Story B real harness.

- Image: `deploy/aws/full-run/Dockerfile`
- Entrypoint: `deploy/aws/full-run/run-entrypoint.sh`
- Loop: proposes → benchmarks → pore gates → logs to shared DB
- **Note:** Currently uses fixture objects (not real proposer/benchmark/pore); see `TODO(Story B integration)` in entrypoint.

## The Dispatcher Seam: `launch_run()`

The dispatcher (Story D, branch `story-d/control-plane`) calls:

```python
run_id = launch_run(
    task_id="my_task_42",
    model="claude-opus-4-20250805",
    iterations=10
)
# launch_run performs ecs:RunTask and returns the ECS task ARN as run_id.
# The running container writes experiments to the shared log DB via logclient.
# The dispatcher observes progress via read_experiments.
```

**Module:** `deploy/aws/launch_run.py`

**Signature:**

```python
def launch_run(
    task_id: str,
    *,
    model: str,
    iterations: int,
    cluster: str = ...,
    task_def: str = ...,
    subnets: list[str] = ...,
    security_groups: list[str] = ...,
) -> str:
    """Launch a full-run task on ECS Fargate.

    Args:
        task_id: Task identifier (e.g., "my_task_42").
        model: Claude model to use (e.g., "claude-opus-4-20250805").
        iterations: Number of optimization iterations.
        cluster: ECS cluster name (defaults from config.env).
        task_def: Task definition (defaults from config.env).
        subnets: List of subnet IDs for awsvpc (defaults from config.env).
        security_groups: List of security group IDs (defaults from config.env).

    Returns:
        The ECS task ARN (run_id) that can be polled via describe-tasks.

    Raises:
        RuntimeError: If ecs:RunTask fails.
    """
```

**Example usage:**

```python
from deploy.aws.launch_run import launch_run

run_id = launch_run(
    task_id="search_v2_opt",
    model="claude-opus-4-20250805",
    iterations=5
)
print(f"Launched run: {run_id}")
# Launched run: arn:aws:ecs:us-east-1:123456789012:task/story-e-cluster/abc123...

# Dispatcher monitors via:
# aws ecs describe-tasks --cluster story-e-cluster --tasks abc123... --region us-east-1
```

## Rate Limits & Concurrency

**Important:** Anthropic API rate limits are **organization / tier-level, shared across all keys, workspaces, and tasks.** Minting additional API keys does NOT raise throughput.

The levers for scaling are:

1. **Prompt caching** (Story C/B): reduces token volume, raises effective throughput.
2. **Dispatcher concurrency cap** (Story D): enforces a single organization-wide ceiling on concurrent tasks. `launch_run()` is the per-run primitive the dispatcher throttles.

**This deployment does NOT lift rate limits.** It provides the orchestration primitive (`launch_run()`) that the dispatcher uses to respect them.

## IAM Least-Privilege Rationale

### Task Execution Role: `sunsteadhack-task-execution-role`

**Attached policies:**
- `AmazonEC2ContainerRegistryReadOnly` — pull the image from ECR.
- `CloudWatchLogsCreateLogGroup`, `CloudWatchLogsCreateLogStream`, `PutLogEvents` — write logs.
- `secretsmanager:GetSecretValue` scoped to the two secret ARNs — read ANTHROPIC_API_KEY and DB_DSN from Secrets Manager.

**Why not more?** The execution role runs *before* the container starts. It needs only to pull the image and inject secrets. Nothing else.

### Task Role (Container Identity): `sunsteadhack-task-role`

**Attached policies:** None (deny-by-default).

**Why empty?** The running container:
- Reads the `ANTHROPIC_API_KEY` and `DB_DSN` from environment (injected by the execution role as secrets).
- Calls the Anthropic API over HTTPS (no AWS permissions needed; HTTPS is a standard outbound connection).
- Calls the Aiven Postgres database over the network (no AWS permissions needed; DSN creds embedded in the string).
- Writes logs to CloudWatch via the container agent (handled by the execution role, not the task role).

There are **no AWS API calls** from within the container. An empty task role is a feature, not an omission — it enforces that your application code can never accidentally escalate permissions or reach out to other AWS resources.

### Trust Policy

Both roles trust the ECS task principal: `ecs-tasks.amazonaws.com`.

## Security Guarantees

1. **Secrets:** `ANTHROPIC_API_KEY` and `DB_DSN` are stored in AWS Secrets Manager, never baked into the image, never in plaintext env vars, never echoed by scripts.
2. **Networking:**
   - Egress-only security group (no inbound rules).
   - Outbound to HTTPS (443) for Anthropic API.
   - Outbound to the DB port (5432 default) for Aiven.
   - No public IP assignment (assumes NAT Gateway for outbound egress).
3. **IAM:** Least-privilege roles with scoped resource ARNs and explicit deny-by-default on the task role.
4. **Cost attribution:** Every `RunTask` call tags the ECS task with `task_id` and `model` so Story C can bill-track per run.

## Testing & Validation

### Static validation (no AWS calls):

```bash
# Syntax check all shell scripts
bash -n setup/00-ecr.sh
bash -n setup/10-secrets.sh
bash -n setup/20-iam.sh
bash -n setup/30-network.sh
bash -n setup/40-taskdef.sh
bash -n setup/50-smoke.sh

# Compile Python modules
python -m py_compile launch_run.py

# Run unit tests (boto3 mocked, no real AWS calls)
pytest tests/test_launch_run.py -v
```

### Smoke test (against real AWS, if deployed):

```bash
source config.env
bash setup/50-smoke.sh
# Launches one proposer task, waits for completion, retrieves logs, asserts Candidate JSON.
```

## What IS and ISN'T Deployed Yet

### Phase 0 (Index Discovery) — READY

- ✅ Proposer container image (Phase 0)
- ✅ ECR repo and image push
- ✅ AWS Secrets Manager for credentials
- ✅ IAM roles (task execution + task)
- ✅ ECS cluster, task definition, security group
- ✅ Smoke test (validates image pull, secrets, networking, output format)

### Phase 1 (Proposer + Benchmark) — BLOCKED on Story B

- ⏳ Benchmark harness (pore integration, cost estimation)
- ⏳ Composite task definition (proposer + benchmark stages)

### Phase 2 (Full Run Loop) — STUBBED

- 🔨 Full-run container image (with fixtures; real harness pending Story B)
- 🔨 Task definition for full-run
- 🔨 Integration with dispatcher's `read_experiments()` polling

**Phase 2 fixtures:** See `deploy/aws/full-run/run-entrypoint.sh` — uses fixture objects (`FakeProposer`, `FakeBenchmark`, `FakeLogClient`) with clear `TODO(Story B integration)` comments showing exactly where the real harness gets injected.

Once Story B lands (benchmark, pore, logclient), replace the fixtures and re-register the task definition.

## Troubleshooting

### "ecs:RunTask returned InvalidTaskDefinition"

Check that the task definition was registered:

```bash
aws ecs describe-task-definition \
  --task-definition "${TASK_FAMILY_NAME}" \
  --region "${AWS_REGION}"
```

### "Container failed to pull image"

Check ECR repo and image:

```bash
aws ecr describe-repositories --region "${AWS_REGION}" --query 'repositories[?repositoryName==`'${ECR_REPO_NAME}'`]'
aws ecr list-images --repository-name "${ECR_REPO_NAME}" --region "${AWS_REGION}"
```

### "Container exited with code 1"

Check CloudWatch Logs:

```bash
aws logs tail "/ecs/${TASK_FAMILY_NAME}" --follow --region "${AWS_REGION}"
```

### "Permission denied: secretsmanager:GetSecretValue"

Verify the execution role's inline policy includes the secret ARNs:

```bash
aws iam get-role-policy \
  --role-name "${TASK_EXECUTION_ROLE_NAME}" \
  --policy-name "SecretsManagerPolicy" \
  --region "${AWS_REGION}"
```

## Next Steps

1. Customize `config.env` with your AWS account details.
2. Set environment variables: `ANTHROPIC_API_KEY`, `DB_DSN`.
3. Run setup scripts in order.
4. Run `setup/50-smoke.sh` to validate Phase 0.
5. Await Story B (benchmark harness) for Phase 2 integration.
6. Integrate `deploy/aws/launch_run.py` into Story D's dispatcher.

---

**Author:** Story E (AWS deployment)  
**Status:** Phase 0 complete, Phase 2 stubbed pending Story B  
**Last updated:** 2026-06-25
