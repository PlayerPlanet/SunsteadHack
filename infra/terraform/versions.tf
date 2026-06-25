# Review-only IaC. Authored to be coherent and idiomatic but NOT applied/validated in
# this environment — run `terraform init && terraform plan` on your side and reconcile
# before any apply. See infra/terraform/README.md.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}
