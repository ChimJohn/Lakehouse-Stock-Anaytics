resource "aws_cloudwatch_event_rule" "daily_ingest" {
  name                = "stock-daily-ingest"
  description         = "Trigger stock ingestion Lambda daily at midnight UTC"
  schedule_expression = var.schedule_expression

  tags = {
    Project = "lakehouse-stock-analytics"
  }
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.daily_ingest.name
  target_id = "StockIngestLambda"
  arn       = var.lambda_function_arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_ingest.arn
}
