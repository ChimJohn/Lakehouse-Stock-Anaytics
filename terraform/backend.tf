# Remote state stored in S3 — create this bucket manually before running terraform init
# aws s3api create-bucket --bucket <your-prefix>-tfstate --region ap-southeast-1 \
#   --create-bucket-configuration LocationConstraint=ap-southeast-1

terraform {
  backend "s3" {
    bucket = "REPLACE_WITH_YOUR_PREFIX-tfstate"
    key    = "lakehouse-stock-analytics/terraform.tfstate"
    region = "ap-southeast-1"
  }
}
