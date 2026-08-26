variable "function_name" {
  type = string
}

variable "raw_bucket_name" {
  type = string
}

variable "raw_bucket_arn" {
  type = string
}

variable "tickers" {
  type = list(string)
}

variable "aws_region" {
  type = string
}

variable "tfstate_bucket" {
  type        = string
  description = "S3 bucket where lambda_package.zip is stored"
}
