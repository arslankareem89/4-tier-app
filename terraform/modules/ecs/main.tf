locals {
  name = "${var.project_name}-${var.environment}-backend"
}

# --------------------------------------------------
# ECR repository
# --------------------------------------------------

resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name = "${var.project_name}-backend"
  }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the latest 10 images"

        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }

        action = {
          type = "expire"
        }
      }
    ]
  })
}

# --------------------------------------------------
# Backend application secret
# --------------------------------------------------

resource "aws_secretsmanager_secret" "backend" {
  name                    = "${var.project_name}/${var.environment}/backend/secret-key"
  description             = "Backend application JWT secret key"
  recovery_window_in_days = 7
}

# --------------------------------------------------
# ECS cluster and logs
# --------------------------------------------------

resource "aws_ecs_cluster" "backend" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
}

# --------------------------------------------------
# ECS IAM trust policy
# --------------------------------------------------

data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --------------------------------------------------
# ECS execution role (pull image, write logs, read startup secrets)
# --------------------------------------------------

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "execution_policy" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "read_secret" {
  name = "${local.name}-read-secret"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.backend.arn
      }
    ]
  })
}

# --------------------------------------------------
# ECS task role (application AWS API access)
# --------------------------------------------------

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy" "read_database_secret" {
  name = "${local.name}-read-database-secret"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.database_secret_arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "s3_uploads" {
  name = "${local.name}-s3-uploads"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "UploadAndDownloadObjects"
        Effect = "Allow"

        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]

        Resource = "${var.uploads_bucket_arn}/*"
      }
    ]
  })
}

# --------------------------------------------------
resource "aws_iam_role_policy" "upload_queue_send" {
  name = "${local.name}-upload-queue-send"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = var.upload_queue_arn
      }
    ]
  })
}

# ALB target group and listener
# --------------------------------------------------

resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-${var.environment}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = var.alb_arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# --------------------------------------------------
# Backend task definition
# --------------------------------------------------

resource "aws_ecs_task_definition" "backend" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = "${aws_ecr_repository.backend.repository_url}:bootstrap"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "APP_ENV"
          value = "production"
        },
        {
          name  = "PORT"
          value = "8000"
        },
        {
          name  = "UPLOAD_DIR"
          value = "/app/uploads"
        },
        {
          name  = "S3_BUCKET"
          value = var.uploads_bucket_name
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "DB_HOST"
          value = var.database_endpoint
        },
        {
          name  = "DB_PORT"
          value = tostring(var.database_port)
        },
        {
          name  = "DB_NAME"
          value = var.database_name
        },
        {
          name  = "DB_USER"
          value = var.database_username
        },
        {
          name  = "DATABASE_SECRET_ARN"
          value = var.database_secret_arn
        }
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.backend.arn
        }
      ]

      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)\" || exit 1"
        ]

        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }

      logConfiguration = {
        logDriver = "awslogs"

        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }
    }
  ])

  depends_on = [
    aws_iam_role_policy_attachment.execution_policy,
    aws_iam_role_policy.read_secret,
    aws_iam_role_policy.read_database_secret,
    aws_iam_role_policy.s3_uploads,
    aws_iam_role_policy.upload_queue_send
  ]
}

# --------------------------------------------------
# ECS service
# --------------------------------------------------

resource "aws_ecs_service" "backend" {
  name            = local.name
  cluster         = aws_ecs_cluster.backend.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  platform_version                   = "LATEST"
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.backend_security_group_id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy_attachment.execution_policy,
    aws_iam_role_policy.read_secret,
    aws_iam_role_policy.read_database_secret,
    aws_iam_role_policy.s3_uploads
  ]

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }
}


# --------------------------------------------------
# Durable upload-processing worker
# --------------------------------------------------

resource "aws_cloudwatch_log_group" "upload_worker" {
  name              = "/ecs/${local.name}-worker"
  retention_in_days = 30

  tags = {
    Name        = "${local.name}-worker"
    Environment = var.environment
    Purpose     = "Durable upload worker logs"
  }
}

resource "aws_iam_role" "worker_task" {
  name               = "${local.name}-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy" "worker_read_database_secret" {
  name = "${local.name}-worker-read-database-secret"
  role = aws_iam_role.worker_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.database_secret_arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "worker_s3_read" {
  name = "${local.name}-worker-s3-read"
  role = aws_iam_role.worker_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.uploads_bucket_arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "worker_sqs_consume" {
  name = "${local.name}-worker-sqs-consume"
  role = aws_iam_role.worker_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueAttributes"
        ]
        Resource = var.upload_queue_arn
      }
    ]
  })
}

resource "aws_ecs_task_definition" "upload_worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  container_definitions = jsonencode([
    {
      name        = "upload-worker"
      image       = "${aws_ecr_repository.backend.repository_url}:bootstrap"
      essential   = true
      command     = ["python", "worker.py"]
      stopTimeout = 120

      environment = [
        {
          name  = "APP_ENV"
          value = "production"
        },
        {
          name  = "S3_BUCKET"
          value = var.uploads_bucket_name
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "DB_HOST"
          value = var.database_endpoint
        },
        {
          name  = "DB_PORT"
          value = tostring(var.database_port)
        },
        {
          name  = "DB_NAME"
          value = var.database_name
        },
        {
          name  = "DB_USER"
          value = var.database_username
        },
        {
          name  = "DATABASE_SECRET_ARN"
          value = var.database_secret_arn
        },
        {
          name  = "SQS_QUEUE_URL"
          value = var.upload_queue_url
        },
        {
          name  = "SQS_MAX_RECEIVE_COUNT"
          value = "3"
        },
        {
          name  = "SQS_WAIT_TIME_SECONDS"
          value = "20"
        },
        {
          name  = "SQS_VISIBILITY_TIMEOUT_SECONDS"
          value = "120"
        }
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.backend.arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.upload_worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])

  depends_on = [
    aws_iam_role_policy_attachment.execution_policy,
    aws_iam_role_policy.read_secret,
    aws_iam_role_policy.worker_read_database_secret,
    aws_iam_role_policy.worker_s3_read,
    aws_iam_role_policy.worker_sqs_consume
  ]

  tags = {
    Name        = "${local.name}-worker"
    Environment = var.environment
    Purpose     = "Durable upload processing"
  }
}

resource "aws_ecs_service" "upload_worker" {
  name             = "${local.name}-worker"
  cluster          = aws_ecs_cluster.backend.id
  task_definition  = aws_ecs_task_definition.upload_worker.arn
  desired_count    = 0
  launch_type      = "FARGATE"
  platform_version = "LATEST"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.backend_security_group_id]
    assign_public_ip = true
  }

  depends_on = [
    aws_iam_role_policy_attachment.execution_policy,
    aws_iam_role_policy.read_secret,
    aws_iam_role_policy.worker_read_database_secret,
    aws_iam_role_policy.worker_s3_read,
    aws_iam_role_policy.worker_sqs_consume
  ]

  # GitHub Actions owns the live worker task definition and running count.
  # Start at zero so Terraform cannot launch the placeholder bootstrap image.
  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }

  tags = {
    Name        = "${local.name}-worker"
    Environment = var.environment
    Purpose     = "Durable upload processing"
  }
}
