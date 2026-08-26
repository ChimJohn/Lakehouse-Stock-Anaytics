# Databricks notebook — 03_dashboard.py
# Reads gold Parquet from S3 and displays valuation dashboard.
# Uses boto3 + pandas (compatible with Databricks Free Edition serverless)

dbutils.widgets.text("gold_bucket", "")
dbutils.widgets.text("aws_access_key", "")
dbutils.widgets.text("aws_secret_key", "")
dbutils.widgets.text("aws_region", "ap-southeast-1")

GOLD_BUCKET    = dbutils.widgets.get("gold_bucket")
AWS_ACCESS_KEY = dbutils.widgets.get("aws_access_key")
AWS_SECRET_KEY = dbutils.widgets.get("aws_secret_key")
AWS_REGION     = dbutils.widgets.get("aws_region")

import boto3
import pandas as pd
from io import BytesIO

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

# ── Read all gold Parquet files ───────────────────────────────────────────────
paginator = s3.get_paginator("list_objects_v2")
pages = paginator.paginate(Bucket=GOLD_BUCKET, Prefix="stocks_scored/")

dfs = []
for page in pages:
    for obj in page.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".parquet"):
            continue
        response = s3.get_object(Bucket=GOLD_BUCKET, Key=key)
        dfs.append(pd.read_parquet(BytesIO(response["Body"].read())))

assert len(dfs) > 0, "No gold data found"
df = pd.concat(dfs, ignore_index=True)
latest_date = df["date"].max()
latest = df[df["date"] == latest_date].copy()

# ── Dashboard 1: Latest valuation snapshot ────────────────────────────────────
print(f"\n=== Valuation Snapshot: {latest_date} ===")
snapshot = latest[["symbol", "shortName", "sector", "currentPrice",
                    "trailingPE", "forwardPE", "pegRatio",
                    "valuation_score", "valuation_band"]].sort_values("valuation_score", ascending=False)
display(snapshot)

# ── Dashboard 2: Band summary ────────────────────────────────────────────────
print("\n=== Valuation Band Summary ===")
band_summary = latest.groupby("valuation_band").agg(
    count=("symbol", "count"),
    avg_score=("valuation_score", "mean"),
    tickers=("symbol", lambda x: ", ".join(sorted(x)))
).round(1).reset_index()
display(band_summary)

# ── Dashboard 3: Sector comparison ───────────────────────────────────────────
print("\n=== Sector Comparison ===")
sector_summary = latest.groupby("sector").agg(
    num_stocks=("symbol", "count"),
    avg_pe=("trailingPE", "mean"),
    avg_fwd_pe=("forwardPE", "mean"),
    avg_score=("valuation_score", "mean")
).round(1).reset_index().sort_values("avg_score", ascending=False)
display(sector_summary)

print("\nDashboard complete.")
