# Cognito as the OAuth 2.1 Authorization Server (the IdP the resource server trusts).
# The MCP server validates access tokens issued here against this pool's JWKS:
#   issuer  = https://cognito-idp.<region>.amazonaws.com/<pool-id>
#   jwks_uri= <issuer>/.well-known/jwks.json
# A resource server defines the custom scopes the tokens carry (control:read, etc.).

resource "aws_cognito_user_pool" "this" {
  name = "${var.project}-pool"
}

resource "aws_cognito_resource_server" "control" {
  identifier   = "https://${var.domain_name}/mcp" # == OAUTH_AUDIENCE / resource
  name         = "${var.project}-resource"
  user_pool_id = aws_cognito_user_pool.this.id

  scope {
    scope_name        = "control:read"
    scope_description = "Read tasks, runs, curves, boundary"
  }
  scope {
    scope_name        = "control:register"
    scope_description = "Register tasks (still pore-governed)"
  }
  scope {
    scope_name        = "control:dispatch"
    scope_description = "Dispatch and cancel runs"
  }
  scope {
    scope_name        = "control:adjudicate"
    scope_description = "Adjudicate escalations"
  }
}

# A confidential client for machine callers (client-credentials). Interactive Claude
# connector callers would use an auth-code+PKCE client instead.
resource "aws_cognito_user_pool_client" "machine" {
  name                                 = "${var.project}-machine"
  user_pool_id                         = aws_cognito_user_pool.this.id
  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = [for s in aws_cognito_resource_server.control.scope_identifiers : s]
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.project
  user_pool_id = aws_cognito_user_pool.this.id
}

locals {
  oauth_issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
  oauth_jwks_uri = "${local.oauth_issuer}/.well-known/jwks.json"
}
