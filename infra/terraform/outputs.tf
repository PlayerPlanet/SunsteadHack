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
