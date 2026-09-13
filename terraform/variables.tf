variable "aws_region" {
  description = "AWS region to deploy resources in"
  type        = string
  default     = "ap-southeast-1"
}

variable "s3_bucket_prefix" {
  description = "Prefix for S3 bucket names (must be globally unique)"
  type        = string
}

variable "databricks_host" {
  description = "Databricks workspace URL"
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
    # Technology (9)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA",
    "AMD", "INTC",
    # Financials (3)
    "JPM", "GS", "V",
    # Healthcare (2)
    "JNJ", "UNH",
    # Energy (1)
    "CVX",
    # International ADRs (1)
    "TSM"
  ]
}

variable "aws_access_key" {
  description = "AWS access key for Databricks to access S3"
  type        = string
  sensitive   = true
}

variable "aws_secret_key" {
  description = "AWS secret key for Databricks to access S3"
  type        = string
  sensitive   = true
}

variable "telegram_bot_token" {
  description = "Telegram bot token for valuation alerts"
  type        = string
  sensitive   = true
}

variable "telegram_chat_id" {
  description = "Telegram chat ID to send reports to"
  type        = string
}

variable "fmp_api_key" {
  description = "Financial Modeling Prep API key"
  type        = string
  sensitive   = true
}
