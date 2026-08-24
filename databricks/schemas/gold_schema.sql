-- Gold layer schema reference
-- Table: stock_analytics.stocks_scored
-- Format: Delta, partitioned by date

CREATE TABLE IF NOT EXISTS stock_analytics.stocks_scored (
    symbol              STRING      COMMENT 'Ticker symbol (e.g. AAPL)',
    shortName           STRING      COMMENT 'Company display name',
    sector              STRING      COMMENT 'GICS sector',
    industry            STRING      COMMENT 'GICS industry',
    currentPrice        DOUBLE      COMMENT 'Latest closing price (USD)',
    marketCap           BIGINT      COMMENT 'Market capitalisation',
    trailingPE          DOUBLE      COMMENT 'Trailing 12-month P/E ratio',
    forwardPE           DOUBLE      COMMENT 'Forward P/E ratio (analyst estimates)',
    pegRatio            DOUBLE      COMMENT 'PEG ratio',
    sector_median_pe    DOUBLE      COMMENT 'Median P/E across all stocks in same sector',
    pe_score            DOUBLE      COMMENT 'P/E component score (0–1)',
    fwd_pe_score        DOUBLE      COMMENT 'Forward P/E component score (0–1)',
    peg_score           DOUBLE      COMMENT 'PEG component score (0–1)',
    valuation_score     DOUBLE      COMMENT 'Composite valuation score (0–100)',
    valuation_band      STRING      COMMENT 'undervalued | fair_value | overvalued',
    dividendYield       DOUBLE      COMMENT 'Annual dividend yield (decimal)',
    fiftyTwoWeekHigh    DOUBLE      COMMENT '52-week high price',
    fiftyTwoWeekLow     DOUBLE      COMMENT '52-week low price',
    date                DATE        COMMENT 'Partition key — data fetch date',
    fetched_at          TIMESTAMP   COMMENT 'UTC timestamp of yfinance fetch',
    scored_at           TIMESTAMP   COMMENT 'UTC timestamp of scoring run'
)
USING DELTA
PARTITIONED BY (date)
COMMENT 'Daily stock valuation scores computed from yfinance metrics';
