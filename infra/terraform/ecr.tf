# Image registry the CI/CD pipeline pushes to. Point var.container_image at
# "<repo_url>:latest" so an ECS force-new-deployment rolls the freshly-pushed image.

resource "aws_ecr_repository" "this" {
  name                 = var.project
  image_tag_mutability = "MUTABLE" # ":latest" is re-pointed each deploy
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep only recent images.
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}
