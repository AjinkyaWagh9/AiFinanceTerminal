-- Sub-project #5: ML pipeline v1.
-- Symmetric with signal_outcomes; one row per (signal, horizon, model_version).
-- Multiple model_versions per (signal, horizon) is intentional — lets v1 and
-- v2 predictions live side-by-side for apples-to-apples model comparison.
CREATE TABLE IF NOT EXISTS signal_predictions (
  signal_id        VARCHAR NOT NULL,
  horizon_days     INTEGER NOT NULL,
  p_bull           DOUBLE  NOT NULL,
  p_base           DOUBLE  NOT NULL,
  p_bear           DOUBLE  NOT NULL,
  predicted_class  VARCHAR NOT NULL,        -- 'bull' | 'base' | 'bear' | 'cold_start'
  conformal_set    VARCHAR,                  -- comma-joined; e.g. 'bull,base'
  shap_top         JSON,                     -- [["feature", 0.13], ...] top-5 by |abs|
  model_version    VARCHAR NOT NULL,
  feature_version  VARCHAR NOT NULL,
  predicted_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (signal_id, horizon_days, model_version)
);
CREATE INDEX IF NOT EXISTS signal_predictions_ts_idx
  ON signal_predictions(predicted_at);
CREATE INDEX IF NOT EXISTS signal_predictions_lookup_idx
  ON signal_predictions(signal_id, horizon_days);
