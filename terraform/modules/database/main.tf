locals {
  # RDS identifiers must begin with a letter.
  identifier = lower("${var.environment}-${var.project_name}-postgres")
  name       = "${var.project_name}-${var.environment}-database"
}

resource "aws_db_subnet_group" "this" {
  name        = "${local.identifier}-subnets"
  description = "Private data subnets for ${local.identifier}"
  subnet_ids  = var.private_subnet_ids

  tags = {
    Name        = "${local.identifier}-subnets"
    Environment = var.environment
  }
}

resource "aws_security_group" "database" {
  name        = "${local.name}-sg"
  description = "Allow PostgreSQL only from the backend ECS security group"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from backend ECS tasks only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.backend_security_group_id]
  }

  egress {
    description = "Outbound traffic for stateful responses and database maintenance"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${local.name}-sg"
    Environment = var.environment
  }
}

resource "aws_db_instance" "postgres" {
  identifier = local.identifier

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  db_name  = var.db_name
  username = var.db_username

  # AWS creates and manages the master password in Secrets Manager.
  # The password is not specified in Terraform source or a .tfvars file.
  manage_master_user_password = true

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false

  # Keep the configured backup retention period (currently one day due to
  # the account's Free Tier restriction). Protect against accidental deletion
  # and require a final snapshot for intentional deletion.
  multi_az                   = false
  backup_retention_period    = var.backup_retention_period
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true
  deletion_protection        = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = "${local.identifier}-final-20261026"

  tags = {
    Name        = local.identifier
    Environment = var.environment
    Purpose     = "Application PostgreSQL database"
  }
}