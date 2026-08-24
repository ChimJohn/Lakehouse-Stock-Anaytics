variable "lambda_function_arn" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

variable "schedule_expression" {
  type    = string
  default = "cron(0 0 * * ? *)"
}
