-- Phase 2 / 4a: persist Critic output + cache the full Analyst payload.
-- Additive only. Existing rows in `analyses` get NULL for payload_json.

CREATE TABLE IF NOT EXISTS critiques (
    id              VARCHAR PRIMARY KEY,
    analysis_id     VARCHAR NOT NULL,
    verdict         VARCHAR,
    issues_md       VARCHAR,
    missing_md      VARCHAR,
    confidence_adj  DOUBLE,
    raw_text        VARCHAR,
    model           VARCHAR,
    tokens_in       BIGINT,
    tokens_out      BIGINT,
    degraded        BOOLEAN DEFAULT FALSE,
    error           VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_critiques_analysis ON critiques(analysis_id);

ALTER TABLE analyses ADD COLUMN payload_json VARCHAR;
