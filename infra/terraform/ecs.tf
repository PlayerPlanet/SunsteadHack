# ECS Fargate: a stateless web service (behind the ALB) and a worker service (polls the
# Postgres run queue). Both run the same image; only the command + ingress differ. The
# app DSN is injected from Secrets Manager; OAuth config is plain env (non-secret).

resource "aws_ecs_cluster" "this" {
  name = var.project
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.project}"
  retention_in_days = 14
}

locals {
  common_env = [
    { name = "CLEANROOM_SKIP_SCHEMA_INIT", value = "1" }, # admin owns migrations
    { name = "AWS_REGION", value = var.region },
  ]
  oauth_env = [
    { name = "OAUTH_ISSUER", value = local.oauth_issuer },
    { name = "OAUTH_JWKS_URI", value = local.oauth_jwks_uri },
    { name = "OAUTH_AUDIENCE", value = "https://${var.domain_name}/mcp" },
    { name = "OAUTH_RESOURCE", value = "https://${var.domain_name}/mcp" },
  ]
  app_dsn_secret = [
    { name = "CLEANROOM_PG_APP_DSN", valueFrom = aws_secretsmanager_secret.app_dsn.arn },
  ]
}

# ---- web tier ----------------------------------------------------------------
resource "aws_ecs_task_definition" "web" {
  family                   = "${var.project}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "web"
    image     = var.container_image
    essential = true
    command   = ["python", "-m", "cleanroom.control.server.http"]
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = concat(local.common_env, local.oauth_env, [
      { name = "CLEANROOM_DISPATCH_MODE", value = "queue" },
      { name = "PORT", value = "8000" },
    ])
    secrets = local.app_dsn_secret
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "web"
      }
    }
  }])
}

resource "aws_ecs_service" "web" {
  name            = "${var.project}-web"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.web_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.https]
}

# ---- worker tier -------------------------------------------------------------
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "worker"
    image     = var.container_image
    essential = true
    command   = ["python", "-m", "cleanroom.control.worker"]
    environment = concat(local.common_env, [
      { name = "CLEANROOM_WORKER_POLL_SECONDS", value = "1.0" },
    ])
    secrets = local.app_dsn_secret
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])
}

resource "aws_ecs_service" "worker" {
  name            = "${var.project}-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }
}
