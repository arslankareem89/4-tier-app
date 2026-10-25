output "aws_region" {
  value = var.aws_region
}

output "project_name" {
  value = var.project_name
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_app_subnet_ids" {
  value = module.network.private_app_subnet_ids
}

output "private_data_subnet_ids" {
  value = module.network.private_data_subnet_ids
}

output "ecr_backend_repository_url" {
  description = "ECR repository URL for the backend image"
  value       = module.ecs.ecr_backend_repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster running the backend service"
  value       = module.ecs.ecs_cluster_name
}

output "ecs_service_name" {
  description = "ECS backend service name"
  value       = module.ecs.ecs_service_name
}

output "backend_secret_arn" {
  description = "Secrets Manager ARN for the backend JWT secret"
  value       = module.ecs.backend_secret_arn
}

output "backend_log_group" {
  description = "CloudWatch log group for backend tasks"
  value       = module.ecs.backend_log_group
}

output "uploads_bucket_name" {
  description = "Private S3 bucket storing application uploads"
  value       = module.storage.uploads_bucket_name
}

output "uploads_bucket_arn" {
  description = "ARN of the private S3 uploads bucket"
  value       = module.storage.uploads_bucket_arn
}

output "database_endpoint" {
  description = "Private RDS PostgreSQL endpoint"
  value       = module.database.endpoint
}

output "database_name" {
  description = "PostgreSQL database name"
  value       = module.database.database_name
}

output "database_secret_arn" {
  description = "ARN of the RDS-managed database credentials secret"
  value       = module.database.master_user_secret_arn
}

output "backend_security_group_id" {
  description = "Security group shared by ECS tasks and database ingress rules"
  value       = aws_security_group.backend.id
}

output "frontend_bucket_name" {
  description = "Private S3 bucket for built frontend assets"
  value       = module.frontend.frontend_bucket_name
}

output "frontend_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.frontend.cloudfront_distribution_id
}

output "frontend_domain_name" {
  description = "Public CloudFront domain for the frontend and API"
  value       = module.frontend.cloudfront_domain_name
}
