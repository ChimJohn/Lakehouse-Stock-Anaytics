# Databricks notebook — 02_transform.py
# Reads silver Parquet, computes valuation scores, writes Delta to gold layer.
#
# Valuation Score (0–100):
#   P/E vs sector median  35%
#   Forward P/E           35%
#   PEG ratio             30%
#
# Score bands:
#   70–100  🟢 Undervalued
#   40–69   🟡 Fair value
#   0–39    🔴 Overvalued

dbutils.widgets.text("raw_bucket", "")
dbutils.widgets.text("silver_bucket", "")
dbutils.widgets.text("gold_bucket", "")

SILVER_BUCKET = dbutils.widgets.get("silver_bucket")
GOLD_BUCKET   = dbutils.widgets.get("gold_bucket")
RAW_BUCKET    = dbutils.widgets.get("raw_bucket")

SILVER_PATH = f"s3a://{SILVER_BUCKET}/stocks/"
GOLD_PATH   = f"s3a://{GOLD_BUCKET}/stocks_scored/"

from pyspark.sql import functions as F, Window

# ── Read latest silver partition ─────────────────────────────────────────────
silver_df = spark.read.parquet(SILVER_PATH)

latest_date = silver_df.agg(F.max("date")).collect()[0][0]
print(f"Processing date: {latest_date}")

df = silver_df.filter(F.col("date") == latest_date)

# ── Sector median P/E ────────────────────────────────────────────────────────
sector_window = Window.partitionBy("sector")

df = df.withColumn(
    "sector_median_pe",
    F.percentile_approx("trailingPE", 0.5).over(sector_window)
)

# ── Component scores (lower metric = better value = higher score) ─────────────

# P/E score: compare ticker P/E to sector median
# If P/E < sector median → undervalued → higher score
df = df.withColumn(
    "pe_ratio",
    F.when(F.col("sector_median_pe") > 0,
        F.col("sector_median_pe") / F.col("trailingPE")
    ).otherwise(None)
).withColumn(
    "pe_score",
    F.when(F.col("pe_ratio").isNotNull(),
        F.greatest(F.lit(0.0), F.least(F.lit(1.0), F.col("pe_ratio")))
    ).otherwise(0.5)  # neutral when data missing
)

# Forward P/E score: lower forward P/E → better → higher score
# Normalised: 0 = fwd_pe > 50, 1 = fwd_pe < 5
df = df.withColumn(
    "fwd_pe_score",
    F.when(F.col("forwardPE").isNotNull(),
        F.greatest(F.lit(0.0),
            F.least(F.lit(1.0),
                (F.lit(50.0) - F.col("forwardPE")) / F.lit(45.0)
            )
        )
    ).otherwise(0.5)
)

# PEG score: PEG < 1 considered undervalued, PEG > 3 overvalued
df = df.withColumn(
    "peg_score",
    F.when(F.col("pegRatio").isNotNull(),
        F.greatest(F.lit(0.0),
            F.least(F.lit(1.0),
                (F.lit(3.0) - F.col("pegRatio")) / F.lit(2.0)
            )
        )
    ).otherwise(0.5)
)

# ── Composite score ──────────────────────────────────────────────────────────
df = df.withColumn(
    "valuation_score",
    F.round(
        (F.col("pe_score") * 0.35 + F.col("fwd_pe_score") * 0.35 + F.col("peg_score") * 0.30) * 100,
        1
    )
).withColumn(
    "valuation_band",
    F.when(F.col("valuation_score") >= 70, "undervalued")
     .when(F.col("valuation_score") >= 40, "fair_value")
     .otherwise("overvalued")
).withColumn(
    "scored_at",
    F.current_timestamp()
)

gold_df = df.select(
    "symbol", "shortName", "sector", "industry",
    "currentPrice", "marketCap",
    "trailingPE", "forwardPE", "pegRatio",
    "sector_median_pe", "pe_score", "fwd_pe_score", "peg_score",
    "valuation_score", "valuation_band",
    "dividendYield", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "date", "fetched_at", "scored_at"
)

row_count = gold_df.count()
print(f"Gold layer: {row_count} rows")

# ── Write Delta (upsert by symbol + date) ────────────────────────────────────
(
    gold_df
    .write
    .format("delta")
    .mode("overwrite")
    .option("replaceWhere", f"date = '{latest_date}'")
    .partitionBy("date")
    .save(GOLD_PATH)
)

print(f"Written to {GOLD_PATH}")
display(gold_df.orderBy(F.col("valuation_score").desc()))
