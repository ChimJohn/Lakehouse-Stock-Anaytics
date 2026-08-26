variable "raw_bucket_name" {
  type = string
}

variable "silver_bucket_name" {
  type = string
}

variable "gold_bucket_name" {
  type = string
}

variable "databricks_iam_role_arn" {
  type = string
}

variable "aws_access_key" {
  type      = string
  sensitive = true
}

variable "aws_secret_key" {
  type      = string
  sensitive = true
}
