# The non-superuser app DSN lives in Secrets Manager and is injected into the tasks as
# an env var by ECS (see ecs.tf). The avnadmin/superuser DSN is NEVER stored here or
# given to the tasks — it is used only for the one-off migration (runbook), by a human.

resource "aws_secretsmanager_secret" "app_dsn" {
  name = "${var.project}/app-dsn"
}

resource "aws_secretsmanager_secret_version" "app_dsn" {
  secret_id     = aws_secretsmanager_secret.app_dsn.id
  secret_string = var.app_dsn_secret_value
}
