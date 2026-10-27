locals {
  bucket_name = lower(
    "${var.project_name}-${var.environment}-frontend-${var.account_id}"
  )

  frontend_origin_id = "frontend-s3-origin"
  backend_origin_id  = "backend-alb-origin"

  # AWS-managed CloudFront cache policies.
  static_cache_policy_id   = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  disabled_cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"

  # Forward viewer headers except Host, plus cookies and query strings.
  api_origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
}

# --------------------------------------------------
# Private S3 bucket for frontend build files
# --------------------------------------------------

resource "aws_s3_bucket" "frontend" {
  bucket = local.bucket_name

  tags = {
    Name        = local.bucket_name
    Environment = var.environment
    Purpose     = "Static React frontend"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --------------------------------------------------
# CloudFront Origin Access Control for private S3
# --------------------------------------------------

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-${var.environment}-frontend-oac"
  description                       = "CloudFront access to the private frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --------------------------------------------------
# CloudFront distribution
# --------------------------------------------------

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name}-${var.environment} React frontend"
  default_root_object = "index.html"

  price_class = "PriceClass_200"

  # Private S3 frontend origin using Origin Access Control.
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = local.frontend_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id

    connection_attempts         = 3
    connection_timeout          = 10
    response_completion_timeout = 0
  }

  # Existing ALB origin for FastAPI requests.
  origin {
    domain_name = var.alb_dns_name
    origin_id   = local.backend_origin_id

    connection_attempts         = 3
    connection_timeout          = 10
    response_completion_timeout = 0

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # ------------------------------------------------
  # Default behavior: React static files from S3
  # ------------------------------------------------

  default_cache_behavior {
    target_origin_id       = local.frontend_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = [
      "GET",
      "HEAD",
      "OPTIONS"
    ]

    cached_methods = [
      "GET",
      "HEAD"
    ]

    cache_policy_id = local.static_cache_policy_id
    compress        = true
  }

  # ------------------------------------------------
  # API behavior: authentication
  # ------------------------------------------------

  ordered_cache_behavior {
    path_pattern           = "/auth/*"
    target_origin_id       = local.backend_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = [
      "DELETE",
      "GET",
      "HEAD",
      "OPTIONS",
      "PATCH",
      "POST",
      "PUT"
    ]

    cached_methods = [
      "GET",
      "HEAD",
      "OPTIONS"
    ]

    cache_policy_id          = local.disabled_cache_policy_id
    origin_request_policy_id = local.api_origin_request_policy_id
    compress                 = true
  }

  # ------------------------------------------------
  # API behavior: tasks
  # ------------------------------------------------

  ordered_cache_behavior {
    path_pattern           = "/tasks*"
    target_origin_id       = local.backend_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = [
      "DELETE",
      "GET",
      "HEAD",
      "OPTIONS",
      "PATCH",
      "POST",
      "PUT"
    ]

    cached_methods = [
      "GET",
      "HEAD",
      "OPTIONS"
    ]

    cache_policy_id          = local.disabled_cache_policy_id
    origin_request_policy_id = local.api_origin_request_policy_id
    compress                 = true
  }

  # ------------------------------------------------
  # API behavior: uploads and downloads
  # ------------------------------------------------

  ordered_cache_behavior {
    path_pattern           = "/uploads*"
    target_origin_id       = local.backend_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = [
      "DELETE",
      "GET",
      "HEAD",
      "OPTIONS",
      "PATCH",
      "POST",
      "PUT"
    ]

    cached_methods = [
      "GET",
      "HEAD",
      "OPTIONS"
    ]

    cache_policy_id          = local.disabled_cache_policy_id
    origin_request_policy_id = local.api_origin_request_policy_id
    compress                 = true
  }

  # ------------------------------------------------
  # Distribution restrictions
  # ------------------------------------------------

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-frontend"
    Environment = var.environment
  }
}

# --------------------------------------------------
# Allow only this CloudFront distribution to read S3
# --------------------------------------------------

data "aws_iam_policy_document" "frontend_bucket" {
  statement {
    sid    = "AllowCloudFrontReadOnly"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions = [
      "s3:GetObject"
    ]

    resources = [
      "${aws_s3_bucket.frontend.arn}/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket.json
}