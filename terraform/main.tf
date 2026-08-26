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

provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}

module "s3" {
  source        = "./modules/s3"
  bucket_prefix = var.s3_bucket_prefix
  aws_region    = var.aws_region
}

module "lambda" {
  source          = "./modules/lambda"
  function_name   = "${var.s3_bucket_prefix}-stock-ingest"
  raw_bucket_name = module.s3.raw_bucket_name
  raw_bucket_arn  = module.s3.raw_bucket_arn
  tickers         = var.tickers
  aws_region      = var.aws_region
  tfstate_bucket  = "${var.s3_bucket_prefix}-tfstate"
}

module "eventbridge" {
  source               = "./modules/eventbridge"
  lambda_function_arn  = module.lambda.function_arn
  lambda_function_name = module.lambda.function_name
  schedule_expression  = "cron(0 0 * * ? *)"
}

module "databricks" {
  source                  = "./modules/databricks"
  raw_bucket_name         = module.s3.raw_bucket_name
  silver_bucket_name      = module.s3.silver_bucket_name
  gold_bucket_name        = module.s3.gold_bucket_name
  databricks_iam_role_arn = module.s3.databricks_iam_role_arn
  aws_access_key          = var.aws_access_key
  aws_secret_key          = var.aws_secret_key
  aws_region              = var.aws_region
}
