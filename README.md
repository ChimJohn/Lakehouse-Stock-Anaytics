# 📈 Lakehouse Stock Analytics Platform

A personal investing dashboard backed by a fully IaC-provisioned data lakehouse. Stock data flows every weekday from Financial Modeling Prep → AWS Lambda → S3 → Databricks, with valuation scores pushed to Telegram 15 minutes after US pre-market opens. All infrastructure is managed by Terraform and deployed via GitHub Actions CI/CD.

---

## Architecture

```
Financial Modeling Prep API
        │
        ▼
AWS Lambda                    ← triggered Mon–Fri at 4:15 AM ET (4:15 PM SGT)
        │                        15 minutes after US pre-market opens
        ├── scores all tickers
        ├── writes raw NDJSON to S3
        └── sends valuation report to Telegram
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

## Telegram Report

Every weekday at 4:15 PM SGT, a formatted valuation report is sent to a Telegram channel:

```
📈 Stock Valuation — 2026-09-13

🟢 UNDERVALUED (10)
  JPM    Score: 94.3 | P/E:  15.3 | PEG: 0.80
  GS     Score: 94.1 | P/E:  15.7 | PEG: 0.37
  GOOGL  Score: 93.5 | P/E:  16.7 | PEG: 0.15
  ...

🟡 FAIR VALUE (4)
  AAPL   Score: 67.5 | P/E:  37.9 | PEG: 1.16
  INTC   Score: 65.0 | P/E:   neg | PEG: 0.00
  ...

🔴 OVERVALUED (1)
  AMD    Score: 38.7 | P/E: 131.0 | PEG: 1.06

16 tickers · 2026-09-13 04:15 ET
```

---

## Valuation Model

Each stock receives a composite score (0–100) across three metrics:

| Metric | Weight | Logic |
|---|---|---|
| P/E vs sector median | 45% | Below sector median → higher score |
| Forward P/E (fallback: trailing P/E) | 25% | Lower P/E → higher score |
| PEG ratio | 30% | PEG < 1 undervalued, PEG > 3 overvalued |

**Score bands:**
- 🟢 70–100: Undervalued
- 🟡 40–69: Fair value
- 🔴 0–39: Overvalued

**Data quality guards:**
- Negative or absurd PEG ratios (e.g. from negative earnings growth) are discarded and treated as neutral rather than skewing the score
- Negative trailing P/E (negative earnings) is displayed as "neg" and never treated as a "cheap" signal — it falls back to a neutral score component instead
- Transient FMP `402` errors are retried once before being treated as a genuine failure

---

## Tracked Universe (16 tickers)

| Sector | Tickers |
|---|---|
| Technology | AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD, INTC |
| Financials | JPM, GS, V |
| Healthcare | JNJ, UNH |
| Energy | CVX |
| International ADRs | TSM |

> Five tickers (ORCL, QCOM, BLK, MA, ASML) were dropped after consistently returning `HTTP 402 Payment Required` on FMP's free-tier `/stable/quote` endpoint — confirmed as a permanent per-symbol restriction, not a rate-limit or transient issue, after retry logic still failed on every attempt across multiple days.

---

## What's Managed by Terraform

| Resource | Provider |
|---|---|
| S3 buckets (raw / silver / gold) + lifecycle policies | `hashicorp/aws` |
| IAM roles with least-privilege access | `hashicorp/aws` |
| Lambda function + CloudWatch log group | `hashicorp/aws` |
| EventBridge weekday schedule (Mon–Fri 08:15 UTC) | `hashicorp/aws` |
| Databricks notebooks (3) | `databricks/databricks` |
| Databricks job with 3 tasks + dependencies | `databricks/databricks` |

> The Databricks Free Edition workspace is created manually once (Free Edition doesn't expose account-level APIs). All resources *inside* the workspace are fully Terraform-managed — a common enterprise bootstrap pattern.

---

## Free Tier Stack

| Service | Usage | Cost |
|---|---|---|
| Databricks Free Edition | Serverless compute | $0 forever |
| AWS S3 | ~1.5 MB/day of stock data | $0 (5 GB free tier) |
| AWS Lambda | 1 invocation/weekday | $0 (1M/month free tier) |
| AWS EventBridge | 1 scheduled rule | $0 |
| AWS CloudWatch Logs | Lambda logs | $0 (5 GB free tier) |
| GitHub Actions | CI/CD pipeline | $0 (2,000 min/month free) |
| Financial Modeling Prep | ~48 calls/day (3 per ticker × 16) | $0 (250 calls/day free tier) |
| Telegram Bot API | Valuation alerts | $0 |
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
│       ├── lambda/                    # Ingestion function + IAM + Telegram
│       ├── eventbridge/               # Weekday schedule rule
│       └── databricks/                # Notebooks, job, SQL warehouse
├── databricks/
│   ├── notebooks/
│   │   ├── 01_ingest.py               # raw → silver
│   │   ├── 02_transform.py            # silver → gold + valuation score
│   │   └── 03_dashboard.py            # summary tables
│   └── schemas/
│       └── gold_schema.sql            # Delta table schema reference
├── ingestion/
│   ├── lambda_function.py             # FMP API → S3 + Telegram
│   └── placeholder.zip                # Bootstrap placeholder for Terraform
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
- Financial Modeling Prep API key → [sign up](https://financialmodelingprep.com/developer/docs)
- Telegram bot → create via [@BotFather](https://t.me/BotFather)
- Terraform >= 1.0
- AWS CLI

### 1. Bootstrap (one-time manual steps)

```bash
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

### 3. Get a Financial Modeling Prep API key

1. Sign up at [financialmodelingprep.com/developer/docs](https://financialmodelingprep.com/developer/docs)
2. Copy your API key from the dashboard
3. Free tier gives 250 requests/day — this project uses ~48/day (16 tickers × 3 calls)
4. Note: some individual symbols return `402 Payment Required` on the free tier regardless of quota remaining — this appears to be a permanent per-symbol restriction on certain stocks (see Tracked Universe above)

### 4. Create a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token
4. Add your bot to a group or channel and get the chat ID from `https://api.telegram.org/bot<TOKEN>/getUpdates`

### 5. Build and deploy the Lambda package

```bash
mkdir -p ingestion/package
cp ingestion/lambda_function.py ingestion/package/
cd ingestion/package && zip -r ../lambda_package.zip . && cd ../..

aws s3 cp ingestion/lambda_package.zip s3://<your-prefix>-tfstate/lambda_package.zip
aws lambda update-function-code \
  --function-name <your-prefix>-stock-ingest \
  --s3-bucket <your-prefix>-tfstate \
  --s3-key lambda_package.zip \
  --region ap-southeast-1 --no-cli-pager
```

> The Lambda has no external dependencies — it uses only Python's built-in `urllib` and the AWS-provided `boto3`, so no dependency bundling is needed.

### 6. Configure GitHub secrets and variables

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key |
| `DATABRICKS_HOST` | Your workspace URL |
| `DATABRICKS_TOKEN` | Your PAT token |
| `TF_VAR_aws_access_key` | Same as AWS_ACCESS_KEY_ID |
| `TF_VAR_aws_secret_key` | Same as AWS_SECRET_ACCESS_KEY |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/group ID |
| `FMP_API_KEY` | Your Financial Modeling Prep API key |

**Variables** (same page → Variables tab):

| Variable | Value |
|---|---|
| `TF_VAR_AWS_REGION` | `ap-southeast-1` |
| `S3_BUCKET_PREFIX` | Your chosen prefix (e.g. `nicky-lakehouse`) |

### 7. Deploy

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
  --cli-read-timeout 400 \
  response.json && cat response.json
```

**Run Databricks job manually:**
Databricks workspace → Workflows → `stock-analytics-daily-pipeline` → Run now

**Check drift:**
GitHub → Actions → Drift Detection → Run workflow

---

## Key Design Decisions

**Why Financial Modeling Prep instead of yfinance?**
Initial builds used `yfinance`, which scrapes Yahoo Finance directly. AWS Lambda's IP range in `ap-southeast-1` is blanket-blocked by Yahoo (returns HTTP 429 on every request, regardless of delay between calls) because too many AWS customers run scrapers from the same shared IP pool. Financial Modeling Prep is a proper API service with an API key, avoiding this entirely.

**Why 3 API calls per ticker?**
FMP's `/stable/quote` endpoint dropped the `pe` field in its newer API version — it only returns price, volume, and market cap. P/E and PEG must be pulled from the separate `/stable/ratios-ttm` endpoint, and sector comes from `/stable/profile`. This is a real constraint of the current free-tier API surface, not a design choice.

**Why do some tickers return 402 permanently?**
Five tickers (ORCL, QCOM, BLK, MA, ASML) consistently return `402 Payment Required` on the free tier's `/stable/quote` endpoint, every single run, regardless of remaining daily quota. Retry logic with backoff was added and confirmed this is not transient — the same symbols fail deterministically every time. Likely explanation: FMP gates specific high-demand or foreign-listed symbols behind a paid plan even while quota-metered endpoints remain "free." These tickers were dropped from the tracked universe rather than worked around.

**Why is the Lambda package dependency-free?**
Switching to FMP's REST API means no more `yfinance`, `numpy`, or `pandas` — the whole Lambda is under 3.5 KB, built with only `urllib` and `boto3` (already available in the Lambda runtime). This eliminates the entire cross-compilation headache of building Linux-compatible binaries on an Apple Silicon Mac.

**Why is the Databricks workspace created manually?**
Databricks Free Edition doesn't expose account-level APIs, so Terraform can't provision the workspace itself. This mirrors real enterprise setups where workspace provisioning is a separate bootstrap step.

**Why is `lifecycle { ignore_changes }` on the Lambda function?**
The Lambda package is deployed separately via `aws lambda update-function-code` rather than through Terraform, so `ignore_changes` prevents Terraform from overwriting manual deploys on each apply.

**Why weekdays only?**
US markets are closed on weekends, so pre-market data wouldn't change. The EventBridge cron `cron(15 8 ? * MON-FRI *)` skips Saturday and Sunday automatically.

---

## Known Limitations

- **No forward P/E**: FMP's free tier doesn't expose forward-looking analyst estimates, so the model falls back to trailing P/E for that scoring component
- **PEG data gaps**: Some tickers (e.g. UNH, JNJ, META, TSLA) don't return a PEG ratio from FMP's free tier — these are scored as neutral (0.5) on that component rather than penalized
- **Permanently restricted symbols**: ORCL, QCOM, BLK, MA, and ASML cannot be fetched on the free tier and are excluded from the tracked universe
- **16-ticker universe**: Deliberately small to stay well within FMP's 250 calls/day free quota with room for manual testing

---

## Security

- All credentials are stored as GitHub Actions secrets and never committed to the repository
- IAM roles follow least-privilege: Lambda can only write to the raw S3 bucket
- S3 buckets have public access blocked
- Terraform state is encrypted at rest in S3
- API keys (Telegram, FMP) are stored as GitHub secrets and passed to Lambda as environment variables