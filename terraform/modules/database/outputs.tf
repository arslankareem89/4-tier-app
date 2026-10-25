output "endpoint" {
  description = "Private DNS endpoint for the PostgreSQL instance"
  value       = aws_db_instance.postgres.address
}

output "port" {
  description = "PostgreSQL listener port"
  value       = aws_db_instance.postgres.port
}

output "database_name" {
  description = "Created PostgreSQL database name"
  value       = aws_db_instance.postgres.db_name
}

output "username" {
  description = "PostgreSQL master username"
  value       = aws_db_instance.postgres.username
}

output "master_user_secret_arn" {
  description = "ARN of the RDS-managed master credentials secret (not the password itself)"
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "security_group_id" {
  description = "Security group attached to the PostgreSQL instance"
  value       = aws_security_group.database.id
}