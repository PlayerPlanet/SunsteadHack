variable "region" {
  type    = string
  default = "eu-north-1"
}

variable "project" {
  type    = string
  default = "sunstead-control"
}

variable "domain_name" {
  type        = string
  description = "FQDN the MCP server is served on, e.g. control.sunstead.example. Used for the ACM cert + as the OAuth resource/audience."
}

variable "acm_certificate_arn" {
  type        = string
  description = "ACM cert ARN for domain_name (us must be in this region for ALB). Create/validate out-of-band."
}

variable "container_image" {
  type        = string
  description = "ECR image URI for the control-plane image (built from the repo Dockerfile)."
}

variable "app_dsn_secret_value" {
  type        = string
  sensitive   = true
  description = "Aiven Postgres DSN for the NON-SUPERUSER sunstead_app login (sslmode=require). Stored in Secrets Manager; never the avnadmin DSN."
}

variable "github_repo" {
  type        = string
  description = "owner/name of the GitHub repo allowed to assume the deploy role via OIDC."
  default     = "PlayerPlanet/SunsteadHack"
}

variable "create_oidc_provider" {
  type        = bool
  description = "Create the GitHub OIDC provider. Set false if the account already has one."
  default     = true
}

variable "web_desired_count" {
  type    = number
  default = 2
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}
