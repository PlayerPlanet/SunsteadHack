output "alb_dns_name" {
  description = "Point your domain_name CNAME/ALIAS at this."
  value       = aws_lb.this.dns_name
}

output "mcp_url" {
  value = "https://${var.domain_name}/mcp"
}

output "protected_resource_metadata_url" {
  value = "https://${var.domain_name}/.well-known/oauth-protected-resource"
}

output "oauth_issuer" {
  value = local.oauth_issuer
}

output "oauth_jwks_uri" {
  value = local.oauth_jwks_uri
}

output "cognito_token_endpoint" {
  value = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${var.region}.amazoncognito.com/oauth2/token"
}

output "cognito_machine_client_id" {
  value = aws_cognito_user_pool_client.machine.id
}

output "ecr_repository_url" {
  description = "Set var.container_image to \"<this>:latest\" and CI's ECR_REPOSITORY to the repo name."
  value       = aws_ecr_repository.this.repository_url
}

output "github_deploy_role_arn" {
  description = "Set this as the AWS_DEPLOY_ROLE_ARN GitHub Actions secret."
  value       = aws_iam_role.github_deploy.arn
}
