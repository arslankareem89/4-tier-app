output "frontend_bucket_name" {
  description = "Private S3 bucket containing the production frontend"
  value       = aws_s3_bucket.frontend.bucket
}

output "frontend_bucket_arn" {
  description = "ARN of the private frontend bucket"
  value       = aws_s3_bucket.frontend.arn
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID for deployment and cache invalidation"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_domain_name" {
  description = "Public CloudFront domain for the frontend and same-origin API"
  value       = aws_cloudfront_distribution.frontend.domain_name
}
