# 📈 Lakehouse Stock Analytics Platform

A personal investing dashboard backed by a fully IaC-provisioned data lakehouse. Stock data flows daily from Yahoo Finance → AWS Lambda → S3 → Databricks, with all infrastructure managed by Terraform and deployed via GitHub Actions CI/CD.

---

## Architecture

```
Yahoo Finance (yfinance)
        │
        ▼
AWS Lambda                    ← triggered daily by EventBridge (00:00 UTC)
        │
        ▼
S3 — raw layer                ← NDJSON snapshots partitioned by date
        │
        ▼
Databricks (01_ingest)        ← cleans, types, deduplicates → Parquet
        │
        ▼
S3 — silver layer             ← typed Parquet partitioned by date
        │
        ▼
Databricks (02_transform)     ← computes valuation score per ticker
        │
        ▼
S3 — gold layer               ← scored Parquet, ready for analysis
        │
        ▼
Databricks (03_dashboard)     ← valuation heatmap, sector breakdown
```

---

## Valuation Model

Each stock receives a composite score (0–100) across three metrics:

| Metric | Weight | Logic |
|---|---|---|
| P/E vs sector median | 35% | Below sector median → higher score |
| Forward P/E | 35% | Lower forward P/E → higher score |
| PEG ratio | 30% | PEG < 1 undervalued, PEG > 3 overvalued |

**Score bands:**
- 🟢 70–100: Undervalued
- 🟡 40–69: Fair value
- 🔴 0–39: Overvalued

---

## What's Managed by Terraform

| Resource | Provider |
|---|---|
| S3 buckets (raw / silver / gold) + lifecycle policies | `hashicorp/aws` |
| IAM roles with least-privilege access | `hashicorp/aws` |
| Lambda function + CloudWatch log group | `hashicorp/aws` |
| EventBridge daily schedule | `hashicorp/aws` |
| Databricks notebooks (3) | `databricks/databricks` |
| Databricks job with 3 tasks + dependencies | `databricks/databricks` |

> The Databricks Free Edition workspace is created manually once (Free Edition doesn't expose account-level APIs). All resources *inside* the workspace are fully Terraform-managed — a common enterprise bootstrap pattern.

---

## Free Tier Stack

| Service | Usage | Cost |
|---|---|---|
| Databricks Free Edition | Serverless compute | $0 forever |
| AWS S3 | ~1 MB/day of stock data | $0 (5 GB free tier) |
| AWS Lambda | 1 invocation/day | $0 (1M/month free tier) |
| AWS EventBridge | 1 scheduled rule | $0 |
| AWS CloudWatch Logs | Lambda logs | $0 (5 GB free tier) |
| GitHub Actions | CI/CD pipeline | $0 (2,000 min/month free) |
| yfinance | Stock data | $0, no API key required |
| Terraform | IaC | $0, open source |

---

## CI/CD Pipeline

```
PR opened     →  terraform fmt check
              →  terraform validate
              →  terraform plan (comment posted on PR)

Merge to main →  terraform apply (deploys all changes)

Daily 06:00   →  drift-check.yml detects infra divergence from Terraform state
```

---

## Project Structure

```
├── terraform/
│   ├── main.tf                        # Root module
│   ├── variables.tf                   # Input variables
│   ├── outputs.tf                     # S3 bucket names, Lambda ARN, job ID
│   ├── backend.tf                     # S3 remote state
│   └── modules/
│       ├── s3/                        # Buckets + lifecycle + IAM role
│       ├── lambda/                    # Ingestion function + IAM
│       ├── eventbridge/               # Daily schedule rule
│       └── databricks/                # Notebooks, job, SQL warehouse
├── databricks/
│   ├── notebooks/
│   │   ├── 01_ingest.py               # raw → silver
│   │   ├── 02_transform.py            # silver → gold + valuation score
│   │   └── 03_dashboard.py            # summary tables
│   └── schemas/
│       └── gold_schema.sql            # Delta table schema reference
├── ingestion/
│   ├── lambda_function.py             # yfinance → S3 raw layer
│   └── requirements.txt
└── .github/workflows/
    ├── terraform-plan.yml             # PR: plan + comment
    ├── terraform-apply.yml            # Merge: apply
    └── drift-check.yml                # Daily: detect drift
```

---

## Setup

### Prerequisites
- AWS account (free tier)
- Databricks Free Edition account → [sign up](https://www.databricks.com/learn/free-edition)
- Terraform >= 1.0
- AWS CLI
- Docker Desktop (for building the Lambda package)

### 1. Bootstrap (one-time manual steps)

```bash
# Clone the repo
git clone https://github.com/<your-username>/lakehouse-stock-analytics
cd lakehouse-stock-analytics

# Create the Terraform state bucket
aws s3api create-bucket \
  --bucket <your-prefix>-tfstate \
  --region ap-southeast-1 \
  --create-bucket-configuration LocationConstraint=ap-southeast-1

# Update terraform/backend.tf with your bucket name
```

### 2. Create a Databricks Free Edition workspace

1. Sign up at [databricks.com/learn/free-edition](https://www.databricks.com/learn/free-edition)
2. Note your workspace URL (e.g. `https://<id>.cloud.databricks.com`)
3. Generate a Personal Access Token: **Settings → Developer → Access Tokens**

### 3. Build the Lambda package

```bash
# Requires Docker Desktop running
rm -rf ingestion/package
mkdir -p ingestion/package

docker run --rm \
  --platform linux/amd64 \
  -v "$(pwd)/ingestion":/var/task \
  amazonlinux:2023 \
  bash -c "dnf install -y python3.11 python3.11-pip && \
           pip3.11 install yfinance==0.2.54 'numpy==1.26.4' 'pandas==2.1.4' \
           -t /var/task/package/ && echo SUCCESS"

cp ingestion/lambda_function.py ingestion/package/
cd ingestion/package && zip -r ../lambda_package.zip . && cd ../..

# Upload to S3 and deploy
aws s3 cp ingestion/lambda_package.zip s3://<your-prefix>-tfstate/lambda_package.zip
aws lambda update-function-code \
  --function-name <your-prefix>-stock-ingest \
  --s3-bucket <your-prefix>-tfstate \
  --s3-key lambda_package.zip \
  --region ap-southeast-1 --no-cli-pager
```

### 4. Configure GitHub secrets and variables

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key |
| `DATABRICKS_HOST` | Your workspace URL |
| `DATABRICKS_TOKEN` | Your PAT token |
| `TF_VAR_aws_access_key` | Same as AWS_ACCESS_KEY_ID |
| `TF_VAR_aws_secret_key` | Same as AWS_SECRET_ACCESS_KEY |

**Variables** (same page → Variables tab):

| Variable | Value |
|---|---|
| `TF_VAR_AWS_REGION` | `ap-southeast-1` |
| `S3_BUCKET_PREFIX` | Your chosen prefix (e.g. `nicky-lakehouse`) |

### 5. Deploy

```bash
git push origin main  # triggers terraform apply via GitHub Actions
```

---

## Running the Pipeline

**Trigger Lambda manually:**
```bash
aws lambda invoke \
  --function-name <your-prefix>-stock-ingest \
  --region ap-southeast-1 \
  response.json && cat response.json
```

**Run Databricks job manually:**
Databricks workspace → Workflows → `stock-analytics-daily-pipeline` → Run now

**Check drift:**
GitHub → Actions → Drift Detection → Run workflow

---

## Key Design Decisions

**Why boto3 instead of Spark s3a for S3 access?**
Databricks Free Edition serverless doesn't allow setting `spark.conf` properties for S3 credentials. Using `boto3` with explicit credentials bypasses this restriction entirely.

**Why is the Lambda package built with Docker?**
The Lambda runtime runs on Amazon Linux x86_64. Building on an M-series Mac produces ARM binaries that crash on Lambda. Docker with `--platform linux/amd64` cross-compiles correctly.

**Why is the Databricks workspace created manually?**
Databricks Free Edition doesn't expose account-level APIs, so Terraform can't provision the workspace itself. This mirrors real enterprise setups where workspace provisioning is a separate bootstrap step.

**Why is `lifecycle { ignore_changes }` on the Lambda function?**
The Lambda package is too large to store in git and is deployed separately via `aws lambda update-function-code`. The `ignore_changes` block prevents Terraform from overwriting it on each apply.

---

## Tracked Tickers

AAPL · MSFT · GOOGL · AMZN · NVDA · META · TSLA · BRK-B · JPM · V

Configurable via the `tickers` variable in `terraform/variables.tf`.

---

## Security

- All credentials are stored as GitHub Actions secrets and never committed to the repository
- IAM roles follow least-privilege: Lambda can only write to the raw S3 bucket
- S3 buckets have public access blocked
- Terraform state is encrypted at rest in S3
