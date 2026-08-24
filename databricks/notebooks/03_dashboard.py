# Databricks notebook — 03_dashboard.py
# Creates Delta tables in the default metastore for Databricks SQL dashboards.
# Run after 02_transform.py each day.

dbutils.widgets.text("gold_bucket", "")
GOLD_BUCKET = dbutils.widgets.get("gold_bucket")
GOLD_PATH   = f"s3a://{GOLD_BUCKET}/stocks_scored/"

from pyspark.sql import functions as F

# Register as a SQL table (survives between sessions in Free Edition)
spark.sql("CREATE DATABASE IF NOT EXISTS stock_analytics")

spark.read.format("delta").load(GOLD_PATH).createOrReplaceTempView("stocks_gold_tmp")

spark.sql("""
    CREATE OR REPLACE TABLE stock_analytics.stocks_scored
    USING DELTA
    LOCATION '{path}'
""".format(path=GOLD_PATH))

# ── Summary views ────────────────────────────────────────────────────────────

# 1. Latest valuation snapshot
latest = spark.sql("""
    SELECT symbol, shortName, sector, currentPrice,
           trailingPE, forwardPE, pegRatio,
           valuation_score, valuation_band, date
    FROM stock_analytics.stocks_scored
    WHERE date = (SELECT MAX(date) FROM stock_analytics.stocks_scored)
    ORDER BY valuation_score DESC
""")
display(latest)

# 2. Band summary
band_summary = spark.sql("""
    SELECT valuation_band,
           COUNT(*) AS count,
           ROUND(AVG(valuation_score), 1) AS avg_score,
           COLLECT_LIST(symbol) AS tickers
    FROM stock_analytics.stocks_scored
    WHERE date = (SELECT MAX(date) FROM stock_analytics.stocks_scored)
    GROUP BY valuation_band
    ORDER BY avg_score DESC
""")
display(band_summary)

# 3. Sector comparison
sector_summary = spark.sql("""
    SELECT sector,
           COUNT(*) AS num_stocks,
           ROUND(AVG(trailingPE), 1) AS avg_pe,
           ROUND(AVG(forwardPE), 1) AS avg_fwd_pe,
           ROUND(AVG(valuation_score), 1) AS avg_score
    FROM stock_analytics.stocks_scored
    WHERE date = (SELECT MAX(date) FROM stock_analytics.stocks_scored)
    GROUP BY sector
    ORDER BY avg_score DESC
""")
display(sector_summary)

print("Dashboard tables ready in stock_analytics database.")
print("Open Databricks SQL → Dashboards to build visualisations on stock_analytics.stocks_scored")
