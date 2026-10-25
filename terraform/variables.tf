variable "aws_region" {
  description = "AWS deployment region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming and tags"
  type        = string
  default     = "4-tier-app"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "ecs_desired_count" {
  description = "Desired number of backend ECS tasks"
  type        = number
  default     = 1
}

variable "ecs_min_capacity" {
  description = "Minimum number of backend ECS tasks for autoscaling"
  type        = number
  default     = 1
}

variable "ecs_max_capacity" {
  description = "Maximum number of backend ECS tasks for autoscaling"
  type        = number
  default     = 2
}

variable "ecs_cpu_target_percent" {
  description = "Target average ECS service CPU utilization"
  type        = number
  default     = 60
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "task_manager"
}

variable "db_username" {
  description = "PostgreSQL master username; its password is managed by RDS in Secrets Manager"
  type        = string
  default     = "appadmin"
}

variable "db_engine_version" {
  description = "PostgreSQL major engine version"
  type        = string
  default     = "16"
}

variable "db_instance_class" {
  description = "RDS instance class; db.t4g.micro is a small ARM-based development option"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial encrypted RDS storage in GiB"
  type        = number
  default     = 20
}

variable "db_backup_retention_period" {
  description = "Automated RDS backup retention in days; 1 keeps a short recovery window"
  type        = number
  default     = 1
}