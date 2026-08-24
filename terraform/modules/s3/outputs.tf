output "raw_bucket_name" {
  value = aws_s3_bucket.layers["raw"].bucket
}

output "silver_bucket_name" {
  value = aws_s3_bucket.layers["silver"].bucket
}

output "gold_bucket_name" {
  value = aws_s3_bucket.layers["gold"].bucket
}

output "raw_bucket_arn" {
  value = aws_s3_bucket.layers["raw"].arn
}

output "databricks_iam_role_arn" {
  value = aws_iam_role.databricks_s3_access.arn
}
