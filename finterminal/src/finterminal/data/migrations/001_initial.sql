CREATE TABLE IF NOT EXISTS quotes (
    ticker         VARCHAR NOT NULL,
    as_of         TIMESTAMP NOT NULL,
    last_price     DOUBLE,
    change_pct     DOUBLE,
    volume         BIGINT,
    market_cap     DOUBLE,
    PRIMARY KEY (ticker, as_of)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker         VARCHAR NOT NULL,
    as_of         DATE NOT NULL,
    pe_ttm         DOUBLE,
    eps_ttm        DOUBLE,
    roe            DOUBLE,
    roce           DOUBLE,
    debt_to_equity DOUBLE,
    revenue_ttm    DOUBLE,
    net_income_ttm DOUBLE,
    PRIMARY KEY (ticker, as_of)
);

CREATE TABLE IF NOT EXISTS news (
    id             VARCHAR PRIMARY KEY,
    ticker         VARCHAR,
    source         VARCHAR,
    headline       VARCHAR,
    url            VARCHAR,
    published_at   TIMESTAMP,
    body           VARCHAR
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker         VARCHAR PRIMARY KEY,
    added_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes          VARCHAR
);

CREATE TABLE IF NOT EXISTS analyses (
    id             VARCHAR PRIMARY KEY,
    ticker         VARCHAR,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    bull_case      VARCHAR,
    bear_case      VARCHAR,
    confidence     DOUBLE,
    sources_json   VARCHAR
);
