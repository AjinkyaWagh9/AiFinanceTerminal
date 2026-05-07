CREATE TABLE IF NOT EXISTS signal_features (
    signal_id     VARCHAR NOT NULL,
    feature_name  VARCHAR NOT NULL,
    feature_value DOUBLE,
    is_missing    BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (signal_id, feature_name)
);

CREATE INDEX IF NOT EXISTS signal_features_name_idx ON signal_features(feature_name);
