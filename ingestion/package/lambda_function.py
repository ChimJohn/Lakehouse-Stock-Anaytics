"""
Stock ingestion Lambda
Pulls P/E, Forward P/E, PEG, price, and sector data from yfinance,
writes a daily JSON snapshot to S3 raw layer,
and sends a valuation report to Telegram.

Environment variables:
  RAW_BUCKET          - S3 bucket name for raw layer
  TICKERS             - comma-separated list of ticker symbols
  TELEGRAM_BOT_TOKEN  - Telegram bot token
  TELEGRAM_CHAT_ID    - Telegram chat ID
"""

import json
import os
import logging
import time
from datetime import datetime, timezone

import boto3
import yfinance as yf

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

FIELDS = [
    "symbol", "shortName", "sector", "industry",
    "currentPrice", "marketCap",
    "trailingPE", "forwardPE", "pegRatio",
    "trailingEps", "forwardEps", "priceToBook",
    "dividendYield", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "currency",
]


def fetch_ticker(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info
        record = {"symbol": symbol, "fetched_at": datetime.now(timezone.utc).isoformat()}
        for field in FIELDS:
            record[field] = info.get(field)
        return record
    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return {"symbol": symbol, "error": str(e), "fetched_at": datetime.now(timezone.utc).isoformat()}


def score_ticker(record: dict, sector_medians: dict) -> dict:
    """Compute valuation score for a single ticker."""
    sector = record.get("sector")
    median_pe = sector_medians.get(sector)

    # P/E score
    trailing_pe = record.get("trailingPE")
    if median_pe and trailing_pe and trailing_pe > 0:
        pe_ratio = median_pe / trailing_pe
        pe_score = max(0.0, min(1.0, pe_ratio))
    else:
        pe_score = 0.5

    # Forward P/E score
    fwd_pe = record.get("forwardPE")
    if fwd_pe is not None:
        fwd_pe_score = max(0.0, min(1.0, (50.0 - fwd_pe) / 45.0))
    else:
        fwd_pe_score = 0.5

    # PEG score
    peg = record.get("pegRatio")
    if peg is not None:
        peg_score = max(0.0, min(1.0, (3.0 - peg) / 2.0))
    else:
        peg_score = 0.5

    valuation_score = round((pe_score * 0.35 + fwd_pe_score * 0.35 + peg_score * 0.30) * 100, 1)

    if valuation_score >= 70:
        band = "undervalued"
    elif valuation_score >= 40:
        band = "fair_value"
    else:
        band = "overvalued"

    return {**record, "valuation_score": valuation_score, "valuation_band": band}


def send_telegram(token: str, chat_id: str, message: str):
    """Send a message to Telegram."""
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        logger.info("Telegram message sent")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def format_telegram_message(scored: list, run_date: str) -> str:
    undervalued = [r for r in scored if r["valuation_band"] == "undervalued"]
    fair_value  = [r for r in scored if r["valuation_band"] == "fair_value"]
    overvalued  = [r for r in scored if r["valuation_band"] == "overvalued"]

    def fmt_row(r):
        pe  = f"{r['trailingPE']:.1f}" if r.get("trailingPE") else "N/A"
        fpe = f"{r['forwardPE']:.1f}"  if r.get("forwardPE")  else "N/A"
        peg = f"{r['pegRatio']:.2f}"   if r.get("pegRatio")   else "N/A"
        return (f"  <b>{r['symbol']:<6}</b> Score: {r['valuation_score']:>5} | "
                f"P/E: {pe:>6} | Fwd P/E: {fpe:>6} | PEG: {peg:>5}")

    lines = [f"📈 <b>Stock Valuation Report — {run_date}</b>\n"]

    if undervalued:
        lines.append(f"🟢 <b>UNDERVALUED ({len(undervalued)})</b>")
        for r in sorted(undervalued, key=lambda x: -x["valuation_score"]):
            lines.append(fmt_row(r))
        lines.append("")

    if fair_value:
        lines.append(f"🟡 <b>FAIR VALUE ({len(fair_value)})</b>")
        for r in sorted(fair_value, key=lambda x: -x["valuation_score"]):
            lines.append(fmt_row(r))
        lines.append("")

    if overvalued:
        lines.append(f"🔴 <b>OVERVALUED ({len(overvalued)})</b>")
        for r in sorted(overvalued, key=lambda x: -x["valuation_score"]):
            lines.append(fmt_row(r))
        lines.append("")

    lines.append(f"<i>Fetched {len(scored)} tickers · {run_date} 04:15 ET</i>")
    return "\n".join(lines)


def handler(event, context):
    bucket   = os.environ["RAW_BUCKET"]
    tickers  = [t.strip() for t in os.environ["TICKERS"].split(",")]
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(f"Fetching {len(tickers)} tickers for {run_date}")

    # Fetch in batches of 10 with a short delay to avoid rate limiting
    records = []
    for i in range(0, len(tickers), 10):
        batch = tickers[i:i+10]
        for symbol in batch:
            records.append(fetch_ticker(symbol))
        if i + 10 < len(tickers):
            time.sleep(5)

    # Compute sector medians for scoring
    from collections import defaultdict
    sector_pes = defaultdict(list)
    for r in records:
        if r.get("sector") and r.get("trailingPE") and not r.get("error"):
            sector_pes[r["sector"]].append(r["trailingPE"])
    sector_medians = {
        sector: sorted(vals)[len(vals) // 2]
        for sector, vals in sector_pes.items()
    }

    # Score all tickers
    success = [r for r in records if "error" not in r]
    scored  = [score_ticker(r, sector_medians) for r in success]

    # Write raw NDJSON to S3
    key  = f"stocks/date={run_date}/snapshot.json"
    body = "\n".join(json.dumps(r) for r in records)
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"),
                  ContentType="application/x-ndjson")
    logger.info(f"Wrote {len(success)}/{len(records)} records to s3://{bucket}/{key}")

    # Send Telegram report
    if tg_token and tg_chat and scored:
        # Telegram has a 4096 char limit per message — split if needed
        message = format_telegram_message(scored, run_date)
        if len(message) <= 4096:
            send_telegram(tg_token, tg_chat, message)
        else:
            # Split into undervalued + fair/overvalued
            uv = [r for r in scored if r["valuation_band"] == "undervalued"]
            rest = [r for r in scored if r["valuation_band"] != "undervalued"]
            send_telegram(tg_token, tg_chat,
                format_telegram_message(uv + rest[:20], run_date + " (1/2)"))
            send_telegram(tg_token, tg_chat,
                format_telegram_message(rest[20:], run_date + " (2/2)"))

    return {
        "statusCode": 200,
        "date": run_date,
        "tickers_fetched": len(success),
        "tickers_failed": len(records) - len(success),
        "s3_key": key,
    }
