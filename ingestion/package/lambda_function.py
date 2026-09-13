"""
Stock ingestion Lambda
Fetches stock data from Financial Modeling Prep (FMP) stable API,
computes valuation scores, writes to S3, and sends Telegram report.

FMP free tier: 250 requests/day.
Per ticker: quote (price/name/market cap) + profile (sector) +
ratios-ttm (P/E, PEG) = 3 calls/ticker. 44 tickers = 132 calls/day.
"""

import json
import os
import logging
import time
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import urllib.error

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

FMP_BASE = "https://financialmodelingprep.com/stable"


def fmp_get(path: str, symbol: str, api_key: str, retries: int = 2) -> list:
    params = urllib.parse.urlencode({"symbol": symbol, "apikey": api_key})
    url = f"{FMP_BASE}/{path}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "lakehouse-stock-analytics/1.0"})

    last_error = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 402 and attempt < retries:
                # Some FMP free-tier 402s are transient per-symbol — retry once
                logger.info(f"402 on {path}/{symbol}, retrying ({attempt + 1}/{retries})")
                time.sleep(2)
                continue
            raise
    raise last_error


def fetch_ticker(symbol: str, api_key: str) -> dict:
    try:
        quote_data = fmp_get("quote", symbol, api_key)
        if not quote_data or not isinstance(quote_data, list):
            raise ValueError("Empty quote response")
        q = quote_data[0]
    except Exception as e:
        logger.error(f"Quote fetch failed for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e), "fetched_at": datetime.now(timezone.utc).isoformat()}

    sector = None
    try:
        profile = fmp_get("profile", symbol, api_key)
        if profile and isinstance(profile, list):
            sector = profile[0].get("sector")
    except Exception as e:
        logger.error(f"Profile fetch failed for {symbol}: {e}")

    trailing_pe = None
    peg_ratio   = None
    try:
        ratios = fmp_get("ratios-ttm", symbol, api_key)
        if ratios and isinstance(ratios, list):
            r0 = ratios[0]
            trailing_pe = r0.get("priceToEarningsRatioTTM") or r0.get("peRatioTTM")
            peg_val = r0.get("priceToEarningsGrowthRatioTTM") or r0.get("pegRatioTTM")
            # Discard nonsensical PEG values (negative or absurd) — usually from
            # negative or near-zero earnings growth, not a real valuation signal
            if peg_val is not None and 0 < peg_val < 10:
                peg_ratio = peg_val
    except Exception as e:
        logger.error(f"Ratios fetch failed for {symbol}: {e}")

    return {
        "symbol":           symbol,
        "shortName":        q.get("name") or symbol,
        "sector":           sector,
        "industry":         None,
        "currentPrice":     q.get("price"),
        "marketCap":        q.get("marketCap"),
        "trailingPE":       trailing_pe,
        "forwardPE":        None,
        "pegRatio":         peg_ratio,
        "trailingEps":      None,
        "forwardEps":       None,
        "priceToBook":      None,
        "dividendYield":    None,
        "fiftyTwoWeekHigh": q.get("yearHigh"),
        "fiftyTwoWeekLow":  q.get("yearLow"),
        "currency":         "USD",
        "fetched_at":       datetime.now(timezone.utc).isoformat(),
    }


def score_ticker(record: dict, sector_medians: dict) -> dict:
    sector    = record.get("sector")
    median_pe = sector_medians.get(sector)

    trailing_pe = record.get("trailingPE")
    # Negative P/E means negative earnings — not a "cheap" signal, treat as neutral
    if median_pe and trailing_pe and trailing_pe > 0:
        pe_score = max(0.0, min(1.0, median_pe / trailing_pe))
    else:
        pe_score = 0.5

    fwd_pe = record.get("forwardPE") or (record.get("trailingPE") if record.get("trailingPE", 0) > 0 else None)
    fwd_pe_score = max(0.0, min(1.0, (50.0 - fwd_pe) / 45.0)) if fwd_pe is not None else 0.5

    peg = record.get("pegRatio")
    peg_score = max(0.0, min(1.0, (3.0 - peg) / 2.0)) if peg is not None else 0.5

    valuation_score = round((pe_score * 0.45 + fwd_pe_score * 0.25 + peg_score * 0.30) * 100, 1)

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
        tpe = r.get("trailingPE")
        pe  = f"{tpe:.1f}" if tpe is not None and tpe > 0 else ("neg" if tpe is not None else "N/A")
        peg = f"{r['pegRatio']:.2f}"   if r.get("pegRatio")   else "N/A"
        return (f"  <b>{r['symbol']:<6}</b> Score:{r['valuation_score']:>5} | "
                f"P/E:{pe:>6} | PEG:{peg:>5}")

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
    fmp_key  = os.environ["FMP_API_KEY"]
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(f"Fetching {len(tickers)} tickers via FMP for {run_date}")

    records = []
    for symbol in tickers:
        records.append(fetch_ticker(symbol, fmp_key))
        time.sleep(0.3)

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