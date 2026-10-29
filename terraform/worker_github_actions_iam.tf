resource "aws_iam_role_policy" "github_actions_worker_deploy" {
  name = "4-tier-app-github-actions-worker-deploy"
  role = data.aws_iam_role.github_actions_deploy.name

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid      = "RegisterUploadWorkerTaskDefinition"
        Effect   = "Allow"
        Action   = "ecs:RegisterTaskDefinition"
        Resource = "arn:aws:ecs:us-east-1:707575990308:task-definition/4-tier-app-dev-backend-worker:*"
      },
      {
        Sid    = "DeployUploadWorkerService"
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:UpdateService"
        ]
        Resource = "arn:aws:ecs:us-east-1:707575990308:service/4-tier-app-dev-backend/4-tier-app-dev-backend-worker"
      },
      {
        Sid      = "PassUploadWorkerTaskRole"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = "arn:aws:iam::707575990308:role/4-tier-app-dev-backend-worker-task"

        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      }
    ]
  })
}
