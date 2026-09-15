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
  description = "List of stock tickers to track — candidate 50, pending FMP free-tier verification"
  type        = list(string)
  default     = [
    # Technology (24) — confirmed working core + candidate additions
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "INTC",
    "CSCO", "IBM", "TXN", "MU", "ADI", "NOW", "PANW", "CRWD", "SNOW",
    "UBER", "ABNB", "SHOP", "NFLX", "PYPL", "ADSK",
    # Financials (7)
    "JPM", "GS", "V", "WFC", "BAC", "SCHW", "PNC",
    # Healthcare (6)
    "JNJ", "UNH", "PFE", "MRK", "ABT", "CVS",
    # Consumer (6)
    "COST", "WMT", "MCD", "SBUX", "NKE", "TGT",
    # Energy (3)
    "CVX", "SLB", "OXY",
    # Industrials (3)
    "CAT", "DE", "GE",
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
