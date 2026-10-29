# Durable upload processing queue and dead-letter queue.

resource "aws_sqs_queue" "upload_processing_dlq" {
  name                      = "${var.project_name}-${var.environment}-upload-processing-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = {
    Name        = "${var.project_name}-${var.environment}-upload-processing-dlq"
    Environment = var.environment
    Purpose     = "Failed upload processing jobs"
  }
}

resource "aws_sqs_queue" "upload_processing" {
  name                       = "${var.project_name}-${var.environment}-upload-processing"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.upload_processing_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "${var.project_name}-${var.environment}-upload-processing"
    Environment = var.environment
    Purpose     = "Durable upload processing jobs"
  }
}

resource "aws_cloudwatch_metric_alarm" "upload_dlq_not_empty" {
  alarm_actions       = [aws_sns_topic.operations_alerts.arn]
  ok_actions          = [aws_sns_topic.operations_alerts.arn]
  alarm_name          = "${var.project_name}-${var.environment}-upload-dlq-not-empty"
  alarm_description   = "One or more upload jobs need investigation in the SQS dead-letter queue."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.upload_processing_dlq.name
  }

  tags = {
    Environment = var.environment
  }
}
