variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "alb_arn" {
  type = string
}

variable "alb_security_group_id" {
  type = string
}

variable "backend_security_group_id" {
  description = "Backend security group created at root so RDS and ECS can share it without a module cycle"
  type        = string
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "min_capacity" {
  type    = number
  default = 1
}

variable "max_capacity" {
  type    = number
  default = 2
}

variable "cpu_target_percent" {
  type    = number
  default = 60
}

variable "uploads_bucket_name" {
  description = "S3 bucket used for application uploads"
  type        = string
}

variable "uploads_bucket_arn" {
  description = "ARN of the application uploads S3 bucket"
  type        = string
}

variable "database_endpoint" {
  description = "Private RDS PostgreSQL endpoint"
  type        = string
}

variable "database_port" {
  description = "RDS PostgreSQL port"
  type        = number
}

variable "database_name" {
  description = "Application PostgreSQL database name"
  type        = string
}

variable "database_username" {
  description = "PostgreSQL username stored in the RDS managed secret"
  type        = string
}

variable "database_secret_arn" {
  description = "Secrets Manager ARN containing the application PostgreSQL credentials"
  type        = string
}
