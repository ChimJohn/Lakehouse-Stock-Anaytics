locals {
  layers = ["raw", "silver", "gold"]
}

# ── S3 Buckets ───────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "layers" {
  for_each = toset(local.layers)
  bucket   = "${var.bucket_prefix}-${each.key}"

  tags = {
    Project = "lakehouse-stock-analytics"
    Layer   = each.key
  }
}

resource "aws_s3_bucket_versioning" "layers" {
  for_each = toset(local.layers)
  bucket   = aws_s3_bucket.layers[each.key].id

  versioning_configuration {
    status = "Enabled"
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "layers" {
  for_each = toset(local.layers)
  bucket   = aws_s3_bucket.layers[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: expire raw JSON after 30 days (silver/gold kept indefinitely)
resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.layers["raw"].id

  rule {
    id     = "expire-raw-after-30-days"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

# ── IAM Role for Databricks to read all three buckets ────────────────────────
data "aws_iam_policy_document" "databricks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
      aws_caller_identity = "current"
    }
  }
}

resource "aws_iam_role" "databricks_s3_access" {
  name               = "${var.bucket_prefix}-databricks-s3-role"
  assume_role_policy = data.aws_iam_policy_document.databricks_assume.json

  tags = {
    Project = "lakehouse-stock-analytics"
  }
}

data "aws_iam_policy_document" "databricks_s3" {
  statement {
    sid    = "ListBuckets"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation"
    ]
    resources = [for layer in local.layers : aws_s3_bucket.layers[layer].arn]
  }

  statement {
    sid    = "ReadWriteObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = [for layer in local.layers : "${aws_s3_bucket.layers[layer].arn}/*"]
  }
}

resource "aws_iam_role_policy" "databricks_s3" {
  name   = "databricks-s3-access"
  role   = aws_iam_role.databricks_s3_access.id
  policy = data.aws_iam_policy_document.databricks_s3.json
}
