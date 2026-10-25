variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private data subnets for the RDS DB subnet group"
}

variable "backend_security_group_id" {
  type        = string
  description = "Only this security group may connect to PostgreSQL"
}

variable "db_name" {
  type    = string
  default = "task_manager"
}

variable "db_username" {
  type    = string
  default = "appadmin"
}

variable "engine_version" {
  type    = string
  default = "16"
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "allocated_storage" {
  type    = number
  default = 20
}

variable "backup_retention_period" {
  type    = number
  default = 1
}