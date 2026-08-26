terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.128"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Databricks provider — connects to your existing Free Edition workspace
provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}

# ── S3 Buckets (raw / silver / gold layers) ─────────────────────────────────
module "s3" {
  source        = "./modules/s3"
  bucket_prefix = var.s3_bucket_prefix
  aws_region    = var.aws_region
}

# ── Lambda ingestion function ────────────────────────────────────────────────
module "lambda" {
  source            = "./modules/lambda"
  function_name     = "${var.s3_bucket_prefix}-stock-ingest"
  raw_bucket_name   = module.s3.raw_bucket_name
  raw_bucket_arn    = module.s3.raw_bucket_arn
  tickers           = var.tickers
  aws_region        = var.aws_region
  tfstate_bucket    = "${var.s3_bucket_prefix}-tfstate"
}

# ── EventBridge daily schedule ───────────────────────────────────────────────
module "eventbridge" {
  source              = "./modules/eventbridge"
  lambda_function_arn = module.lambda.function_arn
  lambda_function_name = module.lambda.function_name
  schedule_expression = "cron(0 0 * * ? *)"  # Daily at midnight UTC
}

# ── Databricks resources (cluster policy, job, notebooks, SQL warehouse) ─────
module "databricks" {
  source            = "./modules/databricks"
  raw_bucket_name   = module.s3.raw_bucket_name
  silver_bucket_name = module.s3.silver_bucket_name
  gold_bucket_name  = module.s3.gold_bucket_name
  databricks_iam_role_arn = module.s3.databricks_iam_role_arn
}
