# Databricks notebook — 02_transform.py
# Reads silver Parquet from S3, computes valuation scores, writes to gold layer.
# Uses boto3 + pandas (compatible with Databricks Free Edition serverless)

dbutils.widgets.text("silver_bucket", "")
dbutils.widgets.text("gold_bucket", "")
dbutils.widgets.text("aws_access_key", "")
dbutils.widgets.text("aws_secret_key", "")
dbutils.widgets.text("aws_region", "ap-southeast-1")

SILVER_BUCKET  = dbutils.widgets.get("silver_bucket")
GOLD_BUCKET    = dbutils.widgets.get("gold_bucket")
AWS_ACCESS_KEY = dbutils.widgets.get("aws_access_key")
AWS_SECRET_KEY = dbutils.widgets.get("aws_secret_key")
AWS_REGION     = dbutils.widgets.get("aws_region")

import boto3
import pandas as pd
import re
from io import BytesIO
from datetime import datetime, timezone

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

# ── Read all silver Parquet files ─────────────────────────────────────────────
paginator = s3.get_paginator("list_objects_v2")
pages = paginator.paginate(Bucket=SILVER_BUCKET, Prefix="stocks/")

dfs = []
for page in pages:
    for obj in page.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".parquet"):
            continue
        response = s3.get_object(Bucket=SILVER_BUCKET, Key=key)
        df_part = pd.read_parquet(BytesIO(response["Body"].read()))
        dfs.append(df_part)

assert len(dfs) > 0, "No silver Parquet files found"
df = pd.concat(dfs, ignore_index=True)

latest_date = df["date"].max()
print(f"Processing date: {latest_date}")
df = df[df["date"] == latest_date].copy()

# ── Valuation scoring ─────────────────────────────────────────────────────────
# Sector median P/E
sector_median_pe = df.groupby("sector")["trailingPE"].median()
df["sector_median_pe"] = df["sector"].map(sector_median_pe)

# P/E score
df["pe_ratio"] = df.apply(
    lambda r: r["sector_median_pe"] / r["trailingPE"]
    if pd.notna(r["sector_median_pe"]) and pd.notna(r["trailingPE"]) and r["trailingPE"] != 0
    else None, axis=1
)
df["pe_score"] = df["pe_ratio"].apply(
    lambda x: max(0.0, min(1.0, x)) if pd.notna(x) else 0.5
)

# Forward P/E score
df["fwd_pe_score"] = df["forwardPE"].apply(
    lambda x: max(0.0, min(1.0, (50.0 - x) / 45.0)) if pd.notna(x) else 0.5
)

# PEG score
df["peg_score"] = df["pegRatio"].apply(
    lambda x: max(0.0, min(1.0, (3.0 - x) / 2.0)) if pd.notna(x) else 0.5
)

# Composite score
df["valuation_score"] = round(
    (df["pe_score"] * 0.35 + df["fwd_pe_score"] * 0.35 + df["peg_score"] * 0.30) * 100, 1
)
df["valuation_band"] = df["valuation_score"].apply(
    lambda s: "undervalued" if s >= 70 else ("fair_value" if s >= 40 else "overvalued")
)
df["scored_at"] = datetime.now(timezone.utc).isoformat()

print(f"Gold layer: {len(df)} rows")
print(df[["symbol", "valuation_score", "valuation_band"]].sort_values("valuation_score", ascending=False).to_string())

# ── Write gold Parquet ────────────────────────────────────────────────────────
buffer = BytesIO()
df.to_parquet(buffer, index=False)
buffer.seek(0)
gold_key = f"stocks_scored/date={latest_date}/data.parquet"
s3.put_object(Bucket=GOLD_BUCKET, Key=gold_key, Body=buffer.getvalue())
print(f"Written to s3://{GOLD_BUCKET}/{gold_key}")
