output "ecr_backend_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.backend.name
}

output "ecs_service_name" {
  value = aws_ecs_service.backend.name
}

output "backend_secret_arn" {
  value = aws_secretsmanager_secret.backend.arn
}

output "backend_log_group" {
  value = aws_cloudwatch_log_group.backend.name
}

output "backend_security_group_id" {
  value = var.backend_security_group_id
}

output "backend_target_group_arn" {
  value = aws_lb_target_group.backend.arn
}