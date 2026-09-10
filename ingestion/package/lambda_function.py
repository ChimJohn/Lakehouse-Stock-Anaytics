"""
Stock ingestion Lambda
Fetches stock data from Financial Modeling Prep (FMP) API,
computes valuation scores, writes to S3, and sends Telegram report.

FMP free tier: 250 requests/day. Uses batch quote endpoint to
minimize calls (all tickers in a single request where possible).
"""

import json
import os
import logging
from datetime import datetime, timezone
import urllib.request
import urllib.parse

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

FMP_BASE = "https://financialmodelingprep.com/api/v3"


def fmp_get(path: str, api_key: str, params: dict = None) -> list:
    params = params or {}
    params["apikey"] = api_key
    url = f"{FMP_BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "lakehouse-stock-analytics/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_all_tickers(tickers: list, api_key: str) -> list:
    """Fetch quote + ratios for all tickers using batched FMP calls."""
    symbols = ",".join(tickers)

    # /quote supports comma-separated symbols in a single call
    try:
        quotes = fmp_get(f"quote/{symbols}", api_key)
    except Exception as e:
        logger.error(f"Batch quote fetch failed: {e}")
        quotes = []

    quote_by_symbol = {q["symbol"]: q for q in quotes if isinstance(q, dict) and "symbol" in q}

    # /ratios-ttm and /profile need per-symbol calls on the free tier;
    # profile gives sector, ratios-ttm gives PEG. Fetch both per ticker.
    records = []
    for symbol in tickers:
        q = quote_by_symbol.get(symbol)
        if not q:
            records.append({"symbol": symbol, "error": "No quote data",
                             "fetched_at": datetime.now(timezone.utc).isoformat()})
            continue

        sector = None
        peg_ratio = None
        try:
            profile = fmp_get(f"profile/{symbol}", api_key)
            if profile and isinstance(profile, list):
                sector = profile[0].get("sector")
        except Exception as e:
            logger.error(f"Profile fetch failed for {symbol}: {e}")

        try:
            ratios = fmp_get(f"ratios-ttm/{symbol}", api_key)
            if ratios and isinstance(ratios, list):
                peg_ratio = ratios[0].get("pegRatioTTM")
        except Exception as e:
            logger.error(f"Ratios fetch failed for {symbol}: {e}")

        records.append({
            "symbol":           symbol,
            "shortName":        q.get("name") or symbol,
            "sector":           sector,
            "industry":         None,
            "currentPrice":     q.get("price"),
            "marketCap":        q.get("marketCap"),
            "trailingPE":       q.get("pe"),
            "forwardPE":        None,  # not on free tier; derive fallback below
            "pegRatio":         peg_ratio,
            "trailingEps":      q.get("eps"),
            "forwardEps":       None,
            "priceToBook":      None,
            "dividendYield":    None,
            "fiftyTwoWeekHigh": q.get("yearHigh"),
            "fiftyTwoWeekLow":  q.get("yearLow"),
            "currency":         "USD",
            "fetched_at":       datetime.now(timezone.utc).isoformat(),
        })

    return records


def score_ticker(record: dict, sector_medians: dict) -> dict:
    sector    = record.get("sector")
    median_pe = sector_medians.get(sector)

    trailing_pe = record.get("trailingPE")
    if median_pe and trailing_pe and trailing_pe > 0:
        pe_score = max(0.0, min(1.0, median_pe / trailing_pe))
    else:
        pe_score = 0.5

    # No forward P/E on free tier — fall back to trailing P/E signal only
    fwd_pe = record.get("forwardPE") or record.get("trailingPE")
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
        pe  = f"{r['trailingPE']:.1f}" if r.get("trailingPE") else "N/A"
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

    records = fetch_all_tickers(tickers, fmp_key)

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