# 4-Tier App — Operations Runbook

Last updated: 2026-10-29
AWS Region: us-east-1

## 1. Architecture

- CloudFront distribution: E3TCGFC1YZ2995
- CloudFront domain: dii6w08edudfe.cloudfront.net
- Public Application Load Balancer: 4-tier-app-alb
- ECS cluster: 4-tier-app-dev-backend
- API service: 4-tier-app-dev-backend
- Worker service: 4-tier-app-dev-backend-worker
- PostgreSQL RDS instance: dev-4-tier-app-postgres
- Valkey replication group: tierapp-dev-cache
- S3 uploads bucket: 4-tier-app-dev-uploads-707575990308
- SQS queue: 4-tier-app-dev-upload-processing
- SQS DLQ: 4-tier-app-dev-upload-processing-dlq

The API and worker currently run in public subnets with public IP assignment.
The backend security group restricts inbound port 8000 to the ALB security
group. RDS and Valkey are private. No NAT gateway has been created.

## 2. Health checks

Check the public health endpoint:

    curl -i https://dii6w08edudfe.cloudfront.net/health

Check the ECS services:

    aws ecs describe-services \
      --cluster 4-tier-app-dev-backend \
      --services 4-tier-app-dev-backend 4-tier-app-dev-backend-worker \
      --region us-east-1 \
      --query 'services[].{Name:serviceName,Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' \
      --output table \
      --no-cli-pager

Expected: both services ACTIVE, with one desired and one running task.

## 3. Logs

API logs:

    aws logs tail /ecs/4-tier-app-dev-backend \
      --since 15m --region us-east-1

Worker logs:

    aws logs tail /ecs/4-tier-app-dev-backend-worker \
      --since 15m --region us-east-1

Look for application exceptions, SQS permission failures, database connection
failures, repeated worker errors, and upload_job_acknowledged messages.

## 4. Queue and dead-letter monitoring

Queue configuration:
- Server-side encryption enabled.
- Visibility timeout: 120 seconds.
- Long polling: 20 seconds.
- Messages are redriven to the DLQ after 3 receives.

Check queue counts:

    for QUEUE in \
      4-tier-app-dev-upload-processing \
      4-tier-app-dev-upload-processing-dlq
    do
      URL=$(aws sqs get-queue-url \
        --queue-name "$QUEUE" \
        --region us-east-1 \
        --query QueueUrl --output text)

      echo "=== $QUEUE ==="

      aws sqs get-queue-attributes \
        --queue-url "$URL" \
        --attribute-names \
          ApproximateNumberOfMessages \
          ApproximateNumberOfMessagesNotVisible \
          ApproximateNumberOfMessagesDelayed \
        --region us-east-1 \
        --output table
    done

Check the DLQ alarm:

    aws cloudwatch describe-alarms \
      --alarm-names 4-tier-app-dev-upload-dlq-not-empty \
      --region us-east-1 \
      --query 'MetricAlarms[].{Name:AlarmName,State:StateValue,Reason:StateReason}' \
      --output table \
      --no-cli-pager

If the DLQ count increases, inspect worker logs and identify the failed job.
Do not purge the DLQ. Preserve and inspect the message before deciding whether
it is safe to redrive or delete it.

A controlled AWS failure test confirmed three worker receives followed by
DLQ redrive. The synthetic test message was subsequently removed, and both
queues returned to zero visible, in-flight, and delayed messages.

## 5. CloudWatch performance alarms

The following Terraform-managed alarms are installed:
- 4-tier-app-dev-api-cpu-high
- 4-tier-app-dev-api-memory-high
- 4-tier-app-dev-worker-cpu-high
- 4-tier-app-dev-worker-memory-high
- 4-tier-app-dev-alb-target-latency-high
- 4-tier-app-dev-alb-target-5xx
- 4-tier-app-dev-alb-5xx
- 4-tier-app-dev-rds-cpu-high
- 4-tier-app-dev-upload-dlq-not-empty

Check their states:

    aws cloudwatch describe-alarms \
      --region us-east-1 \
      --query 'MetricAlarms[].{Name:AlarmName,State:StateValue,Metric:MetricName,Reason:StateReason}' \
      --output table \
      --no-cli-pager

The alarms currently track state in CloudWatch; email and SMS notifications
are not configured. An OK state accompanied by missing datapoints treated as
non-breaching does not independently prove that no errors occurred.

## 6. Deployment procedure

List recent workflow runs:

    gh run list --branch main --limit 5

Follow the selected run:

    gh run watch RUN_ID --exit-status

Replace RUN_ID with the actual run ID.

After deployment, verify API and worker ECS services, check the public health
endpoint, and inspect logs before performing an authenticated upload test.

Do not apply Terraform automatically as part of a deployment unless the plan
has been reviewed. The live API and worker task definitions are updated by
the GitHub Actions deployment workflow; Terraform lifecycle settings preserve
the workflow-managed task definitions and desired counts.

## 7. Upload smoke test

Use a dedicated test account and a small test file. Confirm:
1. The authenticated upload returns an upload ID.
2. The upload initially reports processing.
3. The worker processes and acknowledges the job.
4. The status eventually becomes complete.
5. The SHA-256 checksum matches the local file.
6. The main queue and DLQ have no leftover test messages.

Do not repeatedly upload test files to compensate for a failed job. Inspect
the API logs, worker logs, queue counts, and DLQ first.

## 8. Performance baseline

A 45-second test used 3 concurrent workers and 74 authenticated GET /tasks
requests. All returned HTTP 200:
- Throughput: 1.62 requests/second.
- p50 latency: 359 ms.
- p95 latency: 6.97 seconds.
- p99 and maximum: 24.66 seconds.

A later six-request authenticated test returned HTTP 200 in approximately
0.34–0.58 seconds. ALB target response time was low during the busiest minute.
The initial high latency tail was not reproduced consistently and remains
unexplained. Do not infer capacity requirements from this small test alone.

## 9. AWS credit and cost safeguards

Last verified account-plan state:
- Plan type: FREE
- Status: ACTIVE
- Remaining credits: USD 20
- Plan expiration: 2027-02-02 05:45 UTC, unless credits are exhausted earlier.

Check current remaining credits:

    aws freetier get-account-plan-state \
      --region us-east-1 \
      --no-cli-pager \
      --output json

Check this month's service costs:

    START=$(date -u +%Y-%m-01)
    END=$(date -u +%Y-%m-%d)

    aws ce get-cost-and-usage \
      --time-period "Start=$START,End=$END" \
      --granularity MONTHLY \
      --metrics UnblendedCost \
      --group-by Type=DIMENSION,Key=SERVICE \
      --region us-east-1 \
      --no-cli-pager \
      --output table

Cost Explorer data can lag, so check the account-plan credit balance separately.
Do not create a NAT gateway or run sustained load tests without reviewing the
likely cost first. Stop or clean up test resources that are no longer needed.

## 10. Terraform workflow

From the repository root:

    terraform -chdir=terraform fmt -recursive
    terraform -chdir=terraform validate
    terraform -chdir=terraform plan -out=/tmp/review.tfplan
    terraform show /tmp/review.tfplan

Review the plan for replacements or deletions before applying:

    terraform -chdir=terraform apply /tmp/review.tfplan

Never apply a plan that has not been reviewed. Avoid committing state files,
secret values, local credentials, or backup files.
