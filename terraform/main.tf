module "network" {
  source = "./modules/network"

  project_name       = var.project_name
  vpc_cidr           = "10.20.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
}

module "alb" {
  source = "./modules/alb"

  project_name      = var.project_name
  vpc_id            = module.network.vpc_id
  public_subnet_ids = module.network.public_subnet_ids
}

# Shared backend security group. ECS and RDS both reference this group.
resource "aws_security_group" "backend" {
  name        = "${var.project_name}-${var.environment}-backend-sg"
  description = "Allow backend API traffic only from the application load balancer"
  vpc_id      = module.network.vpc_id

  ingress {
    description     = "Backend API from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [module.alb.alb_security_group_id]
  }

  egress {
    description = "Outbound traffic for AWS APIs and database connections"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-backend-sg"
    Environment = var.environment
  }
}

module "storage" {
  source = "./modules/storage"

  project_name = var.project_name
  environment  = var.environment
  account_id   = "707575990308"
}

module "database" {
  source = "./modules/database"

  project_name              = var.project_name
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  private_subnet_ids        = module.network.private_data_subnet_ids
  backend_security_group_id = aws_security_group.backend.id

  db_name                 = var.db_name
  db_username             = var.db_username
  engine_version          = var.db_engine_version
  instance_class          = var.db_instance_class
  allocated_storage       = var.db_allocated_storage
  backup_retention_period = var.db_backup_retention_period
}

module "ecs" {
  source = "./modules/ecs"

  project_name              = var.project_name
  environment               = var.environment
  aws_region                = var.aws_region
  vpc_id                    = module.network.vpc_id
  public_subnet_ids         = module.network.public_subnet_ids
  alb_arn                   = module.alb.alb_arn
  alb_security_group_id     = module.alb.alb_security_group_id
  backend_security_group_id = aws_security_group.backend.id

  uploads_bucket_name = module.storage.uploads_bucket_name
  uploads_bucket_arn  = module.storage.uploads_bucket_arn

  database_endpoint   = module.database.endpoint
  database_port       = module.database.port
  database_name       = module.database.database_name
  database_username   = var.db_application_username
  database_secret_arn = var.db_application_secret_arn

  desired_count      = var.ecs_desired_count
  min_capacity       = var.ecs_min_capacity
  max_capacity       = var.ecs_max_capacity
  cpu_target_percent = var.ecs_cpu_target_percent
}

module "frontend" {
  source = "./modules/frontend"

  project_name = var.project_name
  environment  = var.environment
  account_id   = "707575990308"

  alb_dns_name = module.alb.alb_dns_name
}
