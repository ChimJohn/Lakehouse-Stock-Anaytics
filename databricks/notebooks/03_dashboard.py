# Databricks notebook — 03_dashboard.py
dbutils.widgets.text("gold_bucket", "")
dbutils.widgets.text("aws_access_key", "")
dbutils.widgets.text("aws_secret_key", "")

GOLD_BUCKET    = dbutils.widgets.get("gold_bucket")
AWS_ACCESS_KEY = dbutils.widgets.get("aws_access_key")
AWS_SECRET_KEY = dbutils.widgets.get("aws_secret_key")

spark.conf.set("fs.s3a.access.key", AWS_ACCESS_KEY)
spark.conf.set("fs.s3a.secret.key", AWS_SECRET_KEY)
spark.conf.set("fs.s3a.endpoint", "s3.amazonaws.com")
spark.conf.set("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

GOLD_PATH = f"s3a://{GOLD_BUCKET}/stocks_scored/"

spark.sql("CREATE DATABASE IF NOT EXISTS stock_analytics")

spark.sql(f"""
    CREATE OR REPLACE TABLE stock_analytics.stocks_scored
    USING DELTA
    LOCATION '{GOLD_PATH}'
""")

latest = spark.sql("""
    SELECT symbol, shortName, sector, currentPrice,
           trailingPE, forwardPE, pegRatio,
           valuation_score, valuation_band, date
    FROM stock_analytics.stocks_scored
    WHERE date = (SELECT MAX(date) FROM stock_analytics.stocks_scored)
    ORDER BY valuation_score DESC
""")
display(latest)

band_summary = spark.sql("""
    SELECT valuation_band, COUNT(*) AS count,
           ROUND(AVG(valuation_score), 1) AS avg_score
    FROM stock_analytics.stocks_scored
    WHERE date = (SELECT MAX(date) FROM stock_analytics.stocks_scored)
    GROUP BY valuation_band ORDER BY avg_score DESC
""")
display(band_summary)

print("Dashboard tables ready in stock_analytics database.")
