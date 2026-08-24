variable "aws_region" {
  description = "AWS region to deploy resources in"
  type        = string
  default     = "ap-southeast-1"  # Singapore
}

variable "s3_bucket_prefix" {
  description = "Prefix for S3 bucket names (must be globally unique)"
  type        = string
}

variable "databricks_host" {
  description = "Databricks workspace URL (e.g. https://<id>.cloud.databricks.com)"
  type        = string
  sensitive   = true
}

variable "databricks_token" {
  description = "Databricks Personal Access Token"
  type        = string
  sensitive   = true
}

variable "tickers" {
  description = "List of stock tickers to track"
  type        = list(string)
  default     = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "BRK-B", "JPM", "V"
  ]
}
