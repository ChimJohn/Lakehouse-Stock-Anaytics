# Databricks notebook — 02_transform.py
dbutils.widgets.text("raw_bucket", "")
dbutils.widgets.text("silver_bucket", "")
dbutils.widgets.text("gold_bucket", "")
dbutils.widgets.text("aws_access_key", "")
dbutils.widgets.text("aws_secret_key", "")

SILVER_BUCKET  = dbutils.widgets.get("silver_bucket")
GOLD_BUCKET    = dbutils.widgets.get("gold_bucket")
RAW_BUCKET     = dbutils.widgets.get("raw_bucket")
AWS_ACCESS_KEY = dbutils.widgets.get("aws_access_key")
AWS_SECRET_KEY = dbutils.widgets.get("aws_secret_key")

spark.conf.set("fs.s3a.access.key", AWS_ACCESS_KEY)
spark.conf.set("fs.s3a.secret.key", AWS_SECRET_KEY)
spark.conf.set("fs.s3a.endpoint", "s3.amazonaws.com")
spark.conf.set("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

SILVER_PATH = f"s3a://{SILVER_BUCKET}/stocks/"
GOLD_PATH   = f"s3a://{GOLD_BUCKET}/stocks_scored/"

from pyspark.sql import functions as F, Window

silver_df = spark.read.parquet(SILVER_PATH)
latest_date = silver_df.agg(F.max("date")).collect()[0][0]
print(f"Processing date: {latest_date}")

df = silver_df.filter(F.col("date") == latest_date)

sector_window = Window.partitionBy("sector")
df = df.withColumn("sector_median_pe",
    F.percentile_approx("trailingPE", 0.5).over(sector_window))

df = df.withColumn("pe_ratio",
    F.when(F.col("sector_median_pe") > 0,
        F.col("sector_median_pe") / F.col("trailingPE")).otherwise(None)
).withColumn("pe_score",
    F.when(F.col("pe_ratio").isNotNull(),
        F.greatest(F.lit(0.0), F.least(F.lit(1.0), F.col("pe_ratio")))).otherwise(0.5)
).withColumn("fwd_pe_score",
    F.when(F.col("forwardPE").isNotNull(),
        F.greatest(F.lit(0.0), F.least(F.lit(1.0),
            (F.lit(50.0) - F.col("forwardPE")) / F.lit(45.0)))).otherwise(0.5)
).withColumn("peg_score",
    F.when(F.col("pegRatio").isNotNull(),
        F.greatest(F.lit(0.0), F.least(F.lit(1.0),
            (F.lit(3.0) - F.col("pegRatio")) / F.lit(2.0)))).otherwise(0.5)
).withColumn("valuation_score",
    F.round(
        (F.col("pe_score") * 0.35 + F.col("fwd_pe_score") * 0.35 + F.col("peg_score") * 0.30) * 100, 1)
).withColumn("valuation_band",
    F.when(F.col("valuation_score") >= 70, "undervalued")
     .when(F.col("valuation_score") >= 40, "fair_value")
     .otherwise("overvalued")
).withColumn("scored_at", F.current_timestamp())

gold_df = df.select(
    "symbol", "shortName", "sector", "industry",
    "currentPrice", "marketCap",
    "trailingPE", "forwardPE", "pegRatio",
    "sector_median_pe", "pe_score", "fwd_pe_score", "peg_score",
    "valuation_score", "valuation_band",
    "dividendYield", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "date", "fetched_at", "scored_at"
)

print(f"Gold layer: {gold_df.count()} rows")

(gold_df.write.format("delta")
    .mode("overwrite")
    .option("replaceWhere", f"date = '{latest_date}'")
    .partitionBy("date")
    .save(GOLD_PATH))

print(f"Written to {GOLD_PATH}")
display(gold_df.orderBy(F.col("valuation_score").desc()))
