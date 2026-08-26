# Databricks notebook — 01_ingest.py
# Reads raw NDJSON from S3 raw layer, cleans and types it, writes Parquet to silver layer.

dbutils.widgets.text("raw_bucket", "")
dbutils.widgets.text("iam_role_arn", "")
dbutils.widgets.text("aws_access_key", "")
dbutils.widgets.text("aws_secret_key", "")

RAW_BUCKET      = dbutils.widgets.get("raw_bucket")
AWS_ACCESS_KEY  = dbutils.widgets.get("aws_access_key")
AWS_SECRET_KEY  = dbutils.widgets.get("aws_secret_key")

# Configure S3 access via AWS keys
spark.conf.set("fs.s3a.access.key", AWS_ACCESS_KEY)
spark.conf.set("fs.s3a.secret.key", AWS_SECRET_KEY)
spark.conf.set("fs.s3a.endpoint", "s3.amazonaws.com")
spark.conf.set("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, LongType, TimestampType
)

RAW_PATH    = f"s3a://{RAW_BUCKET}/stocks/"
SILVER_PATH = RAW_PATH.replace("raw", "silver") + "stocks/"

# ── Schema ────────────────────────────────────────────────────────────────────
schema = StructType([
    StructField("symbol",           StringType(), True),
    StructField("shortName",        StringType(), True),
    StructField("sector",           StringType(), True),
    StructField("industry",         StringType(), True),
    StructField("currentPrice",     DoubleType(), True),
    StructField("marketCap",        LongType(),   True),
    StructField("trailingPE",       DoubleType(), True),
    StructField("forwardPE",        DoubleType(), True),
    StructField("pegRatio",         DoubleType(), True),
    StructField("trailingEps",      DoubleType(), True),
    StructField("forwardEps",       DoubleType(), True),
    StructField("priceToBook",      DoubleType(), True),
    StructField("dividendYield",    DoubleType(), True),
    StructField("fiftyTwoWeekHigh", DoubleType(), True),
    StructField("fiftyTwoWeekLow",  DoubleType(), True),
    StructField("currency",         StringType(), True),
    StructField("fetched_at",       StringType(), True),
    StructField("error",            StringType(), True),
])

# ── Read raw NDJSON ───────────────────────────────────────────────────────────
raw_df = (
    spark.read
    .schema(schema)
    .json(RAW_PATH)
    .withColumn("date", F.regexp_extract(F.input_file_name(), r"date=(\d{4}-\d{2}-\d{2})", 1))
    .withColumn("fetched_at", F.to_timestamp("fetched_at"))
)

# ── Clean and deduplicate ─────────────────────────────────────────────────────
silver_df = (
    raw_df
    .filter(F.col("error").isNull())
    .drop("error")
    .dropDuplicates(["symbol", "date"])
    .filter(F.col("symbol").isNotNull())
)

row_count = silver_df.count()
print(f"Silver layer: {row_count} rows")
assert row_count > 0, "Silver layer is empty — check raw data"

# ── Write Parquet partitioned by date ─────────────────────────────────────────
(
    silver_df
    .write
    .mode("overwrite")
    .partitionBy("date")
    .parquet(SILVER_PATH)
)

print(f"Written to {SILVER_PATH}")
