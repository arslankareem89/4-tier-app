# --------------------------------------------------
# Private Valkey cache for shared task-list caching
# --------------------------------------------------

resource "aws_security_group" "cache" {
  name        = "tierapp-${var.environment}-cache-sg"
  description = "Allow TLS connections to Valkey only from backend tasks"
  vpc_id      = module.network.vpc_id

  ingress {
    description     = "Valkey TLS from ECS backend tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.backend.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "tierapp-${var.environment}-cache-sg"
    Environment = var.environment
  }
}

resource "aws_elasticache_subnet_group" "cache" {
  name        = "tierapp-${var.environment}-cache-subnets"
  description = "Private subnets for the Valkey cache"
  subnet_ids  = module.network.private_data_subnet_ids
}

resource "aws_elasticache_replication_group" "cache" {
  replication_group_id = "tierapp-${var.environment}-cache"
  description          = "Shared task-list cache for the 4-tier app"

  engine         = "valkey"
  engine_version = "7.2"
  node_type      = "cache.t4g.micro"
  port           = 6379

  # Small development configuration: one primary node, no replica.
  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false

  # Encrypt cache data at rest and connections in transit.
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  subnet_group_name  = aws_elasticache_subnet_group.cache.name
  security_group_ids = [aws_security_group.cache.id]

  # The cache is derived data. PostgreSQL remains the durable source.
  snapshot_retention_limit = 0

  tags = {
    Name        = "tierapp-${var.environment}-cache"
    Environment = var.environment
    Purpose     = "Shared task-list cache"
  }
}
