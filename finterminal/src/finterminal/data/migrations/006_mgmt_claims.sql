-- Sub-project #3: management claims ledger.
-- Records discrete claims made by management in earnings calls / press releases / news.
-- outcome_verified is populated when claim horizon passes (sub-project #6 fills this).
-- Leakage rule: any feature derived from this table must use an as_of cutoff and
-- exclude claims that resolved after as_of - horizon_days.
CREATE TABLE IF NOT EXISTS mgmt_claims (
    claim_id         VARCHAR PRIMARY KEY,
    ticker           VARCHAR NOT NULL,
    claimed_at       TIMESTAMP NOT NULL,
    claim_text       VARCHAR NOT NULL,
    horizon_days     INTEGER NOT NULL,
    outcome_date     DATE,
    outcome_verified BOOLEAN,
    source_ref       VARCHAR
);

CREATE INDEX IF NOT EXISTS mgmt_claims_ticker_idx       ON mgmt_claims(ticker);
CREATE INDEX IF NOT EXISTS mgmt_claims_outcome_date_idx ON mgmt_claims(outcome_date);
