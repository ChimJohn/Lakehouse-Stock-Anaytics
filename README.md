# 📈 Lakehouse Stock Analytics Platform

A personal investing dashboard backed by a fully IaC-provisioned data lakehouse.
Stock data flows from Yahoo Finance → AWS (S3 + Lambda) → Databricks Delta Lake,
with all AWS resources and Databricks internals managed by Terraform and deployed via GitHub Actions CI/CD.

## Architecture

```
Yahoo Finance (yfinance)
        │
        ▼
AWS Lambda (scheduled daily via EventBridge)
        │
        ▼
S3 Bucket ── raw/        ← JSON snapshots from yfinance
             silver/     ← cleaned, typed Parquet
             gold/       ← valuation-scored Delta tables
        │
        ▼
Databricks Free Edition
  ├── Notebook: 01_ingest.py    (raw → silver)
  ├── Notebook: 02_transform.py (silver → gold + valuation score)
  ├── Notebook: 03_dashboard.py (Databricks SQL dashboard)
  └── Job: daily_pipeline       (orchestrates notebooks)
        │
        ▼
Databricks SQL Dashboard
  └── Valuation heatmap, P/E trend, sector breakdown
```

## What's Managed by Terraform

| Resource | Provider |
|---|---|
| S3 buckets (raw/silver/gold) + lifecycle policies | `hashicorp/aws` |
| IAM role + policy for Lambda (least-privilege S3 write) | `hashicorp/aws` |
| IAM role + policy for Databricks (S3 read) | `hashicorp/aws` |
| Lambda function + EventBridge daily schedule | `hashicorp/aws` |
| CloudWatch log group for Lambda | `hashicorp/aws` |
| Databricks cluster policy | `databricks/databricks` |
| Databricks job (daily pipeline) | `databricks/databricks` |
| Databricks notebook imports | `databricks/databricks` |
| Databricks SQL warehouse | `databricks/databricks` |

> **Note:** The Databricks Free Edition workspace itself is created manually once
> (Free Edition doesn't expose account-level APIs). All resources *inside* the
> workspace are fully Terraform-managed — which mirrors real enterprise patterns
> where workspace provisioning is a separate bootstrap step.

## Free Tier Breakdown

| Service | Usage | Cost |
|---|---|---|
| Databricks Free Edition | Serverless compute, 1 SQL warehouse | $0 forever |
| AWS S3 | ~1 MB/day of stock data | $0 (5 GB free) |
| AWS Lambda | 1 invocation/day | $0 (1M/month free) |
| AWS EventBridge | 1 rule | $0 |
| AWS CloudWatch Logs | Minimal | $0 (5 GB free) |
| GitHub Actions | <5 min/day | $0 (2,000 min/month free) |
| yfinance | Unlimited | $0 |
| Terraform | Open source | $0 |

## Setup

### Prerequisites
- AWS account (free tier)
- Databricks Free Edition account → [sign up](https://www.databricks.com/learn/free-edition)
- Terraform >= 1.0
- Python 3.11+

### 1. Bootstrap (one-time manual steps)

```bash
# Clone the repo
git clone https://github.com/<your-username>/lakehouse-stock-analytics
cd lakehouse-stock-analytics

# Create a Databricks Free Edition workspace at databricks.com
# Note your workspace URL: https://<workspace-id>.azuredatabricks.net

# Generate a Databricks Personal Access Token
# Settings → Developer → Access Tokens → Generate new token

# Copy and fill in your variables
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

### 2. Provision AWS infrastructure

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 3. Configure GitHub Actions secrets

In your GitHub repo → Settings → Secrets → Actions, add:

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | Your AWS IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | Your AWS IAM user secret key |
| `DATABRICKS_HOST` | Your workspace URL |
| `DATABRICKS_TOKEN` | Your PAT token |
| `TF_VAR_aws_region` | e.g. `ap-southeast-1` |
| `TF_VAR_s3_bucket_prefix` | e.g. `nicky-lakehouse` |

### 4. Push to main to trigger deployment

GitHub Actions will run `terraform apply` and deploy the Databricks notebooks and job automatically.

## CI/CD Pipeline

```
PR opened     → terraform fmt check → terraform validate → terraform plan (comment on PR)
Merge to main → terraform apply → deploy Databricks notebooks + job definition
Daily 00:00   → drift-check.yml: compare live state to Terraform state, alert on divergence
```

## Valuation Scoring Model

Each stock gets a composite score (0–100) based on:

| Metric | Weight |
|---|---|
| P/E ratio vs sector median | 35% |
| Forward P/E ratio | 35% |
| PEG ratio | 30% |

Score → colour band:
- 🟢 70–100: Undervalued
- 🟡 40–69: Fair value
- 🔴 0–39: Overvalued

## Project Structure

```
├── terraform/
│   ├── main.tf                    # Root module, wires everything together
│   ├── variables.tf               # Input variables
│   ├── outputs.tf                 # S3 bucket names, Lambda ARN, etc.
│   ├── terraform.tfvars.example   # Template — copy to terraform.tfvars
│   ├── backend.tf                 # S3 remote state backend
│   └── modules/
│       ├── s3/                    # Buckets + lifecycle policies
│       ├── lambda/                # Ingestion function + IAM role
│       ├── eventbridge/           # Daily schedule rule
│       └── databricks/            # Cluster policy, job, notebooks, SQL warehouse
├── databricks/
│   ├── notebooks/
│   │   ├── 01_ingest.py           # raw → silver (clean + type)
│   │   ├── 02_transform.py        # silver → gold (valuation score)
│   │   └── 03_dashboard.py        # SQL dashboard queries
│   ├── jobs/
│   │   └── daily_pipeline.json    # Job definition (used by Terraform)
│   └── schemas/
│       └── gold_schema.sql        # Delta table schema reference
├── ingestion/
│   └── lambda_function.py         # yfinance → S3 raw layer
└── .github/
    └── workflows/
        ├── terraform-plan.yml     # PR: plan + comment
        ├── terraform-apply.yml    # Merge to main: apply
        └── drift-check.yml        # Daily: detect infra drift
```
