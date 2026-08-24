output "raw_bucket_name" {
  description = "S3 bucket for raw yfinance snapshots"
  value       = module.s3.raw_bucket_name
}

output "silver_bucket_name" {
  description = "S3 bucket for cleaned Parquet files"
  value       = module.s3.silver_bucket_name
}

output "gold_bucket_name" {
  description = "S3 bucket for valuation-scored Delta tables"
  value       = module.s3.gold_bucket_name
}

output "lambda_function_arn" {
  description = "ARN of the stock ingestion Lambda"
  value       = module.lambda.function_arn
}

output "lambda_function_name" {
  description = "Name of the stock ingestion Lambda"
  value       = module.lambda.function_name
}

output "databricks_job_id" {
  description = "Databricks Job ID for the daily pipeline"
  value       = module.databricks.job_id
}
