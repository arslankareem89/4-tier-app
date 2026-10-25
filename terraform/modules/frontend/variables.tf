variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "account_id" {
  description = "AWS account ID used to make the frontend bucket name unique"
  type        = string
}

variable "alb_dns_name" {
  description = "DNS name of the application load balancer used for API requests"
  type        = string
}
