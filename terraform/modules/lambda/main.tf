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

# ── Lambda Function ──────────────────────────────────────────────────────────
resource "aws_lambda_function" "stock_ingest" {
  function_name = var.function_name
  role          = aws_iam_role.lambda_exec.arn
  handler       = "lambda_function.handler"
  runtime       = "python3.11"
  timeout       = 300
  memory_size   = 256

  filename         = "${path.module}/../../../ingestion/placeholder.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../ingestion/placeholder.zip")

  lifecycle {
    ignore_changes = [filename, source_code_hash, timeout]
  }

  environment {
    variables = {
      RAW_BUCKET          = var.raw_bucket_name
      TICKERS             = join(",", var.tickers)
      TELEGRAM_BOT_TOKEN  = var.telegram_bot_token
      TELEGRAM_CHAT_ID    = var.telegram_chat_id
      FMP_API_KEY         = var.fmp_api_key
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = {
    Project = "lakehouse-stock-analytics"
  }
}
