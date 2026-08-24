"""
Stock ingestion Lambda
Pulls P/E, Forward P/E, PEG, price, and sector data from yfinance
and writes a daily JSON snapshot to the S3 raw layer.

Environment variables:
  RAW_BUCKET  - S3 bucket name for raw layer
  TICKERS     - comma-separated list of ticker symbols
"""

import json
import os
import logging
from datetime import datetime, timezone

import boto3
import yfinance as yf

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

FIELDS = [
    "symbol",
    "shortName",
    "sector",
    "industry",
    "currentPrice",
    "marketCap",
    "trailingPE",       # P/E ratio
    "forwardPE",        # Forward P/E
    "pegRatio",         # PEG ratio
    "trailingEps",
    "forwardEps",
    "priceToBook",
    "dividendYield",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    "currency",
]


def fetch_ticker(symbol: str) -> dict:
    """Fetch key metrics for a single ticker."""
    try:
        info = yf.Ticker(symbol).info
        record = {"symbol": symbol, "fetched_at": datetime.now(timezone.utc).isoformat()}
        for field in FIELDS:
            record[field] = info.get(field)
        return record
    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return {"symbol": symbol, "error": str(e), "fetched_at": datetime.now(timezone.utc).isoformat()}


def handler(event, context):
    bucket = os.environ["RAW_BUCKET"]
    tickers = [t.strip() for t in os.environ["TICKERS"].split(",")]
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(f"Fetching {len(tickers)} tickers for {run_date}")

    records = [fetch_ticker(t) for t in tickers]

    # Partition by date so Databricks can read incrementally
    key = f"stocks/date={run_date}/snapshot.json"
    body = "\n".join(json.dumps(r) for r in records)  # newline-delimited JSON

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/x-ndjson",
    )

    success = sum(1 for r in records if "error" not in r)
    logger.info(f"Wrote {success}/{len(records)} records to s3://{bucket}/{key}")

    return {
        "statusCode": 200,
        "date": run_date,
        "tickers_fetched": success,
        "tickers_failed": len(records) - success,
        "s3_key": key,
    }
