-- Sub-project #1: outcomes ledger + price store + ingestion log.
-- Conventions match 003: VARCHAR, IF NOT EXISTS, naive TIMESTAMP (IST), no FK constraints.

CREATE TABLE IF NOT EXISTS signals (
    signal_id     VARCHAR PRIMARY KEY,
    signal_type   VARCHAR NOT NULL,
    engine        VARCHAR NOT NULL,
    ticker        VARCHAR NOT NULL,
    ts_emitted    TIMESTAMP NOT NULL,
    payload       JSON,
    confidence    DOUBLE,
    why           VARCHAR,
    source_ref    VARCHAR,
    regime_nifty_close       DOUBLE,
    regime_nifty_pct_50d     DOUBLE,
    regime_india_vix         DOUBLE,
    regime_inr_usd           DOUBLE,
    regime_brent_usd         DOUBLE,
    regime_india_10y_yield   DOUBLE,
    UNIQUE (signal_type, ticker, ts_emitted)
);

CREATE INDEX IF NOT EXISTS signals_ticker_ts_idx ON signals(ticker, ts_emitted);
CREATE INDEX IF NOT EXISTS signals_engine_ts_idx ON signals(engine, ts_emitted);
CREATE INDEX IF NOT EXISTS signals_type_ts_idx   ON signals(signal_type, ts_emitted);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_id        VARCHAR NOT NULL,
    horizon_days     INTEGER NOT NULL,
    ret_pct          DOUBLE,
    ret_pct_vs_nifty DOUBLE,
    resolved_at      TIMESTAMP,
    PRIMARY KEY (signal_id, horizon_days)
);

CREATE INDEX IF NOT EXISTS signal_outcomes_unresolved_idx
    ON signal_outcomes(resolved_at);

CREATE TABLE IF NOT EXISTS prices_eod (
    trade_date  DATE    NOT NULL,
    ticker      VARCHAR NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE  NOT NULL,
    volume      BIGINT,
    source      VARCHAR NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS prices_eod_date_idx ON prices_eod(trade_date);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id            VARCHAR PRIMARY KEY,
    source        VARCHAR NOT NULL,
    target_date   DATE    NOT NULL,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    status        VARCHAR NOT NULL,
    rows_written  INTEGER,
    http_code     INTEGER,
    note          VARCHAR
);

CREATE INDEX IF NOT EXISTS ingestion_log_source_date_idx
    ON ingestion_log(source, target_date);
