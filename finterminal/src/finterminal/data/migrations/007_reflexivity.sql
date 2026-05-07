-- Sub-project #4: Reflexivity Engine v1.
-- Quality + evolution columns on signal_features.
--   n_samples / confidence : ML layer (#5) weights features by data quality.
--   feature_version        : per-row stamp; required for safe model upgrade
--                             (e.g. VADER -> FinBERT) and for backtest replay.
--   normalized             : z-norm activation flag; always FALSE in v1.
--                             Activator lives in #5 once 30-signal history is built.
-- NULL is intentional for non-reflexivity rows; price/regime features have
-- no meaningful sample count.
ALTER TABLE signal_features ADD COLUMN n_samples INTEGER;
ALTER TABLE signal_features ADD COLUMN confidence DOUBLE;
ALTER TABLE signal_features ADD COLUMN feature_version VARCHAR;
ALTER TABLE signal_features ADD COLUMN normalized BOOLEAN DEFAULT FALSE;
