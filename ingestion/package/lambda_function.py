"""
Stock ingestion Lambda
Fetches stock data from Yahoo Finance directly via requests,
computes valuation scores, writes to S3, and sends Telegram report.

Uses a long per-ticker delay to avoid AWS IP-range rate limiting from Yahoo.
"""

import json
import os
import logging
import time
from datetime import datetime, timezone
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

DELAY_SECONDS = 15  # per-ticker delay to avoid IP-range rate limiting


def fetch_ticker(symbol: str) -> dict:
    url = (
        f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
        f"?modules=summaryDetail%2CdefaultKeyStatistics%2CassetProfile%2CfinancialData%2CpriceInfo"
    )
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        result = data.get("quoteSummary", {}).get("result", [])
        if not result:
            raise ValueError("Empty result")

        r = result[0]
        summary   = r.get("summaryDetail", {})
        key_stats = r.get("defaultKeyStatistics", {})
        profile   = r.get("assetProfile", {})
        fin_data  = r.get("financialData", {})

        def val(d, k):
            v = d.get(k)
            if isinstance(v, dict):
                return v.get("raw")
            return v

        record = {
            "symbol":           symbol,
            "shortName":        val(r.get("price", {}), "shortName") or symbol,
            "sector":           profile.get("sector"),
            "industry":         profile.get("industry"),
            "currentPrice":     val(fin_data, "currentPrice") or val(summary, "regularMarketPrice"),
            "marketCap":        val(summary, "marketCap"),
            "trailingPE":       val(summary, "trailingPE"),
            "forwardPE":        val(summary, "forwardPE"),
            "pegRatio":         val(key_stats, "pegRatio"),
            "trailingEps":      val(key_stats, "trailingEps"),
            "forwardEps":       val(key_stats, "forwardEps"),
            "priceToBook":      val(key_stats, "priceToBook"),
            "dividendYield":    val(summary, "dividendYield"),
            "fiftyTwoWeekHigh": val(summary, "fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow":  val(summary, "fiftyTwoWeekLow"),
            "currency":         val(summary, "currency"),
            "fetched_at":       datetime.now(timezone.utc).isoformat(),
        }
        return record

    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return {"symbol": symbol, "error": str(e), "fetched_at": datetime.now(timezone.utc).isoformat()}


def score_ticker(record: dict, sector_medians: dict) -> dict:
    sector    = record.get("sector")
    median_pe = sector_medians.get(sector)

    trailing_pe = record.get("trailingPE")
    if median_pe and trailing_pe and trailing_pe > 0:
        pe_score = max(0.0, min(1.0, median_pe / trailing_pe))
    else:
        pe_score = 0.5

    fwd_pe = record.get("forwardPE")
    fwd_pe_score = max(0.0, min(1.0, (50.0 - fwd_pe) / 45.0)) if fwd_pe is not None else 0.5

    peg = record.get("pegRatio")
    peg_score = max(0.0, min(1.0, (3.0 - peg) / 2.0)) if peg is not None else 0.5

    valuation_score = round((pe_score * 0.35 + fwd_pe_score * 0.35 + peg_score * 0.30) * 100, 1)

    if valuation_score >= 70:
        band = "undervalued"
    elif valuation_score >= 40:
        band = "fair_value"
    else:
        band = "overvalued"

    return {**record, "valuation_score": valuation_score, "valuation_band": band}


def send_telegram(token: str, chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        logger.info("Telegram message sent")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def format_telegram_message(scored: list, run_date: str) -> str:
    undervalued = sorted([r for r in scored if r["valuation_band"] == "undervalued"],
                         key=lambda x: -x["valuation_score"])
    fair_value  = sorted([r for r in scored if r["valuation_band"] == "fair_value"],
                         key=lambda x: -x["valuation_score"])
    overvalued  = sorted([r for r in scored if r["valuation_band"] == "overvalued"],
                         key=lambda x: -x["valuation_score"])

    def fmt_row(r):
        pe  = f"{r['trailingPE']:.1f}" if r.get("trailingPE") else "N/A"
        fpe = f"{r['forwardPE']:.1f}"  if r.get("forwardPE")  else "N/A"
        peg = f"{r['pegRatio']:.2f}"   if r.get("pegRatio")   else "N/A"
        return (f"  <b>{r['symbol']:<6}</b> Score:{r['valuation_score']:>5} | "
                f"P/E:{pe:>6} | Fwd:{fpe:>6} | PEG:{peg:>5}")

    lines = [f"📈 <b>Stock Valuation — {run_date}</b>\n"]

    if undervalued:
        lines.append(f"🟢 <b>UNDERVALUED ({len(undervalued)})</b>")
        lines.extend(fmt_row(r) for r in undervalued)
        lines.append("")

    if fair_value:
        lines.append(f"🟡 <b>FAIR VALUE ({len(fair_value)})</b>")
        lines.extend(fmt_row(r) for r in fair_value)
        lines.append("")

    if overvalued:
        lines.append(f"🔴 <b>OVERVALUED ({len(overvalued)})</b>")
        lines.extend(fmt_row(r) for r in overvalued)
        lines.append("")

    lines.append(f"<i>{len(scored)} tickers · {run_date} 04:15 ET</i>")
    return "\n".join(lines)


def handler(event, context):
    bucket   = os.environ["RAW_BUCKET"]
    tickers  = [t.strip() for t in os.environ["TICKERS"].split(",")]
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(f"Fetching {len(tickers)} tickers for {run_date}, {DELAY_SECONDS}s apart")

    records = []
    for idx, symbol in enumerate(tickers):
        records.append(fetch_ticker(symbol))
        if idx < len(tickers) - 1:
            time.sleep(DELAY_SECONDS)

    from collections import defaultdict
    sector_pes = defaultdict(list)
    for r in records:
        if r.get("sector") and r.get("trailingPE") and not r.get("error"):
            sector_pes[r["sector"]].append(r["trailingPE"])
    sector_medians = {
        sector: sorted(vals)[len(vals) // 2]
        for sector, vals in sector_pes.items()
    }

    success = [r for r in records if "error" not in r]
    scored  = [score_ticker(r, sector_medians) for r in success]

    key  = f"stocks/date={run_date}/snapshot.json"
    body = "\n".join(json.dumps(r) for r in records)
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"),
                  ContentType="application/x-ndjson")
    logger.info(f"Wrote {len(success)}/{len(records)} records to s3://{bucket}/{key}")

    if tg_token and tg_chat and scored:
        message = format_telegram_message(scored, run_date)
        if len(message) <= 4096:
            send_telegram(tg_token, tg_chat, message)
        else:
            half = len(scored) // 2
            send_telegram(tg_token, tg_chat,
                format_telegram_message(scored[:half], run_date + " (1/2)"))
            send_telegram(tg_token, tg_chat,
                format_telegram_message(scored[half:], run_date + " (2/2)"))

    return {
        "statusCode": 200,
        "date": run_date,
        "tickers_fetched": len(success),
        "tickers_failed": len(records) - len(success),
        "s3_key": key,
    }