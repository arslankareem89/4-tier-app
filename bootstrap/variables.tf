variable "aws_region" {
  description = "AWS region for the Terraform state bucket"
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for Terraform state"
  type        = string
}

variable "project_name" {
  description = "Project identifier used in resource tags"
  type        = string
  default     = "4-tier-app"
}
