data "aws_iam_role" "github_actions_deploy" {
  name = "4-tier-app-github-actions-deploy"
}

resource "aws_iam_role_policy" "github_actions_cache_discovery" {
  name = "4-tier-app-github-actions-cache-discovery"
  role = data.aws_iam_role.github_actions_deploy.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DescribeValkeyReplicationGroup"
        Effect = "Allow"
        Action = [
          "elasticache:DescribeReplicationGroups",
          "sqs:GetQueueUrl"
        ]
        Resource = "*"
      }
    ]
  })
}
