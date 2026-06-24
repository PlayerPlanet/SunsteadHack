"""AWS ECS Fargate dispatcher seam for launching SunsteadHack optimization runs.

This module provides the `launch_run()` function that Story D's dispatcher calls to
spawn optimization tasks on AWS ECS/Fargate. Each task runs the full-run loop,
writing experiments to the shared Aiven log database, which the dispatcher observes
via `read_experiments()`.

The function performs an ecs:RunTask with environment overrides (TASK_ID, MODEL,
ITERATIONS) and Secrets Manager injection (ANTHROPIC_API_KEY, DB_DSN), then
returns the task ARN as the run_id.

Cost attribution is handled via ECS task tags: every task is tagged with task_id
and model for per-run billing by Story C.
"""

import os
import sys
from typing import Optional

# Soft import: boto3 is only required at runtime, not for imports.
# This allows the module to be imported and inspected without AWS dependencies.
try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


def launch_run(
    task_id: str,
    *,
    model: str,
    iterations: int,
    cluster: Optional[str] = None,
    task_def: Optional[str] = None,
    subnets: Optional[list[str]] = None,
    security_groups: Optional[list[str]] = None,
    region: Optional[str] = None,
) -> str:
    """Launch a full-run optimization task on AWS ECS Fargate.

    Performs ecs:RunTask with the given task_id, model, and iterations as
    environment variable overrides. Secrets (ANTHROPIC_API_KEY, DB_DSN) are
    injected from AWS Secrets Manager, not as plaintext env vars.

    Each task is tagged with task_id and model for cost attribution by Story C.

    Args:
        task_id: Task identifier (e.g., "search_v2_opt_001"). Becomes the
            TASK_ID environment variable passed to the container.
        model: Claude model to use (e.g., "claude-opus-4-20250805"). Becomes
            the MODEL environment variable.
        iterations: Number of optimization iterations to run. Becomes the
            ITERATIONS environment variable.
        cluster: ECS cluster name. Defaults to ECS_CLUSTER_NAME from config.env
            (read from environment if not overridden).
        task_def: Task definition family name. Defaults to TASK_FAMILY_NAME_FULL_RUN
            from config.env.
        subnets: List of VPC subnet IDs for awsvpc network mode. Defaults to
            [SUBNET_ID_1, SUBNET_ID_2] from config.env.
        security_groups: List of security group IDs (egress-only). Defaults to
            [SECURITY_GROUP_ID] from config.env.
        region: AWS region. Defaults to AWS_REGION from config.env.

    Returns:
        The ECS task ARN (run_id) as a string. Example:
            "arn:aws:ecs:us-east-1:123456789012:task/story-e-cluster/abc123def456"

    Raises:
        RuntimeError: If ecs:RunTask fails or boto3 is not installed.
        ValueError: If required parameters are missing or invalid.

    Example:
        >>> run_id = launch_run(
        ...     task_id="search_opt_42",
        ...     model="claude-opus-4-20250805",
        ...     iterations=5
        ... )
        >>> print(f"Launched: {run_id}")
        Launched: arn:aws:ecs:us-east-1:123456789012:task/...
    """
    if not HAS_BOTO3:
        raise RuntimeError(
            "boto3 is not installed. Install it with: pip install boto3"
        )

    # Load configuration from environment (or use provided overrides)
    region = region or os.getenv("AWS_REGION", "us-east-1")
    cluster = cluster or os.getenv("ECS_CLUSTER_NAME", "story-e-cluster")
    task_def = task_def or os.getenv(
        "TASK_FAMILY_NAME_FULL_RUN", "sunsteadhack-full-run"
    )
    subnets = subnets or [
        s.strip()
        for s in os.getenv("SUBNET_IDS", "subnet-abc123,subnet-def456").split(",")
    ]
    security_groups = security_groups or [
        os.getenv("SECURITY_GROUP_ID", "sg-abc123")
    ]

    # Create ECS client
    ecs_client = boto3.client("ecs", region_name=region)

    # Prepare container overrides for environment variables
    container_overrides = {
        "name": "full-run",  # Must match container name in task def
        "environment": [
            {"name": "TASK_ID", "value": task_id},
            {"name": "MODEL", "value": model},
            {"name": "ITERATIONS", "value": str(iterations)},
        ],
    }

    # Prepare network configuration (awsvpc required for Fargate)
    network_configuration = {
        "awsvpcConfiguration": {
            "subnets": subnets,
            "securityGroups": security_groups,
            "assignPublicIp": "ENABLED",  # Public subnets (no NAT); egress-only SG blocks inbound
        }
    }

    # Prepare tags for cost attribution
    tags = [
        {"key": "task_id", "value": task_id},
        {"key": "model", "value": model},
    ]

    # Call ecs:RunTask
    try:
        response = ecs_client.run_task(
            cluster=cluster,
            taskDefinition=task_def,
            launchType="FARGATE",
            networkConfiguration=network_configuration,
            containerOverrides=[container_overrides],
            tags=tags,
        )
    except Exception as e:
        raise RuntimeError(f"ecs:RunTask failed: {e}")

    # Extract task ARN from response
    if not response.get("tasks") or len(response["tasks"]) == 0:
        error_msg = (
            response.get("failures", [{}])[0].get("reason", "Unknown error")
            if response.get("failures")
            else "No task created"
        )
        raise RuntimeError(f"ecs:RunTask returned no tasks: {error_msg}")

    task_arn = response["tasks"][0]["taskArn"]
    return task_arn


def main():
    """CLI interface for launch_run.

    Usage:
        python launch_run.py <task_id> <model> <iterations> [--cluster CLUSTER] [--region REGION]

    Example:
        python launch_run.py search_opt_1 claude-opus-4-20250805 5 --cluster story-e-cluster
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Launch a SunsteadHack optimization run on AWS ECS Fargate."
    )
    parser.add_argument(
        "task_id",
        help="Task identifier (e.g., 'search_opt_1')",
    )
    parser.add_argument(
        "model",
        help="Claude model to use",
    )
    parser.add_argument(
        "iterations",
        type=int,
        help="Number of iterations to run",
    )
    parser.add_argument(
        "--cluster",
        help="ECS cluster name (default: from env)",
    )
    parser.add_argument(
        "--task-def",
        help="Task definition family (default: from env)",
    )
    parser.add_argument(
        "--region",
        help="AWS region (default: from env or us-east-1)",
    )

    args = parser.parse_args()

    try:
        run_id = launch_run(
            task_id=args.task_id,
            model=args.model,
            iterations=args.iterations,
            cluster=args.cluster,
            task_def=args.task_def,
            region=args.region,
        )
        print(f"Launched: {run_id}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
