output "function_arn" {
  value = aws_lambda_function.stock_ingest.arn
}

output "function_name" {
  value = aws_lambda_function.stock_ingest.function_name
}
