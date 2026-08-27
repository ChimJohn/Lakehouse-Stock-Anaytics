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
    # Technology
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "AMD", "INTC", "QCOM", "TXN", "IBM",
    "CSCO", "NOW", "INTU", "AMAT",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "BLK", "AXP", "V", "MA", "C",
    "USB", "PNC", "SCHW", "COF", "CB",
    # Healthcare
    "JNJ", "UNH", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT",
    "DHR", "BMY", "AMGN", "GILD", "CVS", "MDT",
    # Consumer
    "PG", "KO", "PEP", "WMT", "COST", "MCD", "NKE", "SBUX",
    "TGT", "HD", "LOW", "DIS", "CMCSA", "VZ", "T",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "PSX", "MPC", "OXY",
    # Industrials
    "CAT", "HON", "UPS", "BA", "GE", "MMM", "RTX", "LMT", "DE", "ETN",
    # Materials & Real Estate
    "LIN", "APD", "SHW", "AMT", "PLD", "EQIX",
    # International ADRs
    "TSM", "ASML", "SAP", "TM", "NVO", "SHEL", "BP", "BHP", "SE"
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
