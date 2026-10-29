data "aws_lb" "application" {
  name = "${var.project_name}-alb"
}

data "aws_lb_target_group" "api" {
  name = "${var.project_name}-${var.environment}-api"
}

data "aws_db_instance" "postgres" {
  db_instance_identifier = "${var.environment}-${var.project_name}-postgres"
}

resource "aws_cloudwatch_metric_alarm" "api_cpu_high" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-api-cpu-high"
  alarm_description   = "API ECS service CPU remains high."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "${var.project_name}-${var.environment}-backend"
    ServiceName = "${var.project_name}-${var.environment}-backend"
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "api_memory_high" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-api-memory-high"
  alarm_description   = "API ECS service memory utilization remains high."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "${var.project_name}-${var.environment}-backend"
    ServiceName = "${var.project_name}-${var.environment}-backend"
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_cpu_high" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-worker-cpu-high"
  alarm_description   = "Upload worker ECS service CPU remains high."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "${var.project_name}-${var.environment}-backend"
    ServiceName = "${var.project_name}-${var.environment}-backend-worker"
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_memory_high" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-worker-memory-high"
  alarm_description   = "Upload worker ECS service memory utilization remains high."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "${var.project_name}-${var.environment}-backend"
    ServiceName = "${var.project_name}-${var.environment}-backend-worker"
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_target_latency_high" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-alb-target-latency-high"
  alarm_description   = "Average API target response time exceeds one second in three of five minutes."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Average"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = data.aws_lb.application.arn_suffix
    TargetGroup  = data.aws_lb_target_group.api.arn_suffix
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_target_5xx" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-alb-target-5xx"
  alarm_description   = "One or more API targets returned HTTP 5xx responses during a five-minute period."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = data.aws_lb.application.arn_suffix
    TargetGroup  = data.aws_lb_target_group.api.arn_suffix
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-alb-5xx"
  alarm_description   = "The application load balancer returned HTTP 5xx responses during a five-minute period."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_ELB_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = data.aws_lb.application.arn_suffix
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-rds-cpu-high"
  alarm_description   = "RDS database CPU utilization remains high."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 70
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = data.aws_db_instance.postgres.db_instance_identifier
  }

  tags = {
    Environment = var.environment
  }
}
