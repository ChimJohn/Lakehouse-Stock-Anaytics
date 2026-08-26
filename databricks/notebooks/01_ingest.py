# Databricks notebook — 01_ingest.py
# Reads raw NDJSON from S3, cleans and types, writes Parquet to silver layer.
# Uses boto3 for S3 access (compatible with Databricks Free Edition serverless)

dbutils.widgets.text("raw_bucket", "")
dbutils.widgets.text("silver_bucket", "")
dbutils.widgets.text("aws_access_key", "")
dbutils.widgets.text("aws_secret_key", "")
dbutils.widgets.text("aws_region", "ap-southeast-1")

RAW_BUCKET     = dbutils.widgets.get("raw_bucket")
SILVER_BUCKET  = dbutils.widgets.get("silver_bucket")
AWS_ACCESS_KEY = dbutils.widgets.get("aws_access_key")
AWS_SECRET_KEY = dbutils.widgets.get("aws_secret_key")
AWS_REGION     = dbutils.widgets.get("aws_region")

import boto3
import pandas as pd
import json
from io import StringIO
from datetime import datetime, timezone

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

# ── List all date partitions in raw bucket ────────────────────────────────────
paginator = s3.get_paginator("list_objects_v2")
pages = paginator.paginate(Bucket=RAW_BUCKET, Prefix="stocks/")

all_records = []
dates_found = []

for page in pages:
    for obj in page.get("Contents", []):
        key = obj["Key"]
        if not key.endswith("snapshot.json"):
            continue
        # Extract date from path stocks/date=YYYY-MM-DD/snapshot.json
        import re
        match = re.search(r"date=(\d{4}-\d{2}-\d{2})", key)
        if not match:
            continue
        date_str = match.group(1)
        dates_found.append(date_str)

        response = s3.get_object(Bucket=RAW_BUCKET, Key=key)
        content = response["Body"].read().decode("utf-8")
        for line in content.strip().split("\n"):
            if line:
                record = json.loads(line)
                record["date"] = date_str
                all_records.append(record)

print(f"Found {len(dates_found)} date partitions, {len(all_records)} raw records")
assert len(all_records) > 0, "No raw records found"

# ── Convert to pandas, clean ──────────────────────────────────────────────────
df = pd.DataFrame(all_records)

numeric_cols = ["currentPrice", "marketCap", "trailingPE", "forwardPE", "pegRatio",
                "trailingEps", "forwardEps", "priceToBook", "dividendYield",
                "fiftyTwoWeekHigh", "fiftyTwoWeekLow"]

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

if "fetched_at" in df.columns:
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True, errors="coerce")

# Drop error rows
if "error" in df.columns:
    df = df[df["error"].isna()].drop(columns=["error"])

df = df.dropDuplicates = df.drop_duplicates(subset=["symbol", "date"])
df = df[df["symbol"].notna()]

print(f"Silver layer: {len(df)} rows across {df['date'].nunique()} dates")
assert len(df) > 0, "Silver DataFrame is empty"

# ── Write Parquet to silver bucket, partitioned by date ───────────────────────
from io import BytesIO

for date_val, group in df.groupby("date"):
    buffer = BytesIO()
    group.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3_key = f"stocks/date={date_val}/data.parquet"
    s3.put_object(Bucket=SILVER_BUCKET, Key=s3_key, Body=buffer.getvalue())
    print(f"Written {len(group)} rows to s3://{SILVER_BUCKET}/{s3_key}")

print("Ingest complete.")
