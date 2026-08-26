# ── IAM Role for Lambda ──────────────────────────────────────────────────────
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_s3" {
  statement {
    sid     = "WriteRawBucket"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = ["${var.raw_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "lambda_s3" {
  name   = "write-raw-s3"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_s3.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── CloudWatch Log Group ─────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = 14
}

# ── Lambda Function — package deployed separately via aws lambda update-function-code ──
# Terraform manages config only; code is deployed manually from ingestion/lambda_package.zip
# This avoids storing a large binary in git or re-deploying on every terraform apply
resource "aws_lambda_function" "stock_ingest" {
  function_name = var.function_name
  role          = aws_iam_role.lambda_exec.arn
  handler       = "lambda_function.handler"
  runtime       = "python3.11"
  timeout       = 60
  memory_size   = 256

  # Points to a placeholder zip — real code deployed via:
  # aws lambda update-function-code --s3-bucket <tfstate-bucket> --s3-key lambda_package.zip
  s3_bucket = var.tfstate_bucket
  s3_key    = "lambda_package.zip"

  environment {
    variables = {
      RAW_BUCKET = var.raw_bucket_name
      TICKERS    = join(",", var.tickers)
    }
  }

  lifecycle {
    ignore_changes = [s3_key, s3_bucket, source_code_hash]
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = {
    Project = "lakehouse-stock-analytics"
  }
}