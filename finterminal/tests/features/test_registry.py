from finterminal.data.duckdb_store import connect
from finterminal.features.registry import (
    FeatureSpec, V1_FEATURES, COMPUTABLE_NAMES, PLACEHOLDER_NAMES,
)

def test_signal_features_table_exists(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    cols = conn.execute("PRAGMA table_info('signal_features')").fetchall()
    names = {c[1] for c in cols}
    assert names == {
        "signal_id", "feature_name", "feature_value", "is_missing",
        "n_samples", "confidence", "feature_version", "normalized",
    }

def test_signal_features_pk_is_signal_id_and_feature_name(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    conn.execute(
        "INSERT INTO signal_features (signal_id, feature_name, feature_value, is_missing) "
        "VALUES (?, ?, ?, ?)",
        ["s1", "mom_7d", 0.05, False],
    )
    # Duplicate PK must fail
    import duckdb
    try:
        conn.execute(
            "INSERT INTO signal_features (signal_id, feature_name, feature_value, is_missing) "
            "VALUES (?, ?, ?, ?)",
            ["s1", "mom_7d", 0.99, False],
        )
        raised = False
    except duckdb.ConstraintException:
        raised = True
    assert raised

def test_v1_features_has_20_entries():
    assert len(V1_FEATURES) == 20

def test_v1_features_unique_names():
    names = [f.name for f in V1_FEATURES]
    assert len(set(names)) == len(names)

def test_computable_count_is_20_and_placeholders_0():
    assert len(COMPUTABLE_NAMES) == 20
    assert len(PLACEHOLDER_NAMES) == 0

def test_required_feature_names_present():
    expected = {
        "mom_7d", "mom_30d", "vol_20d", "mom_7d_z",
        "nifty_return_50d", "nifty_vol_20d",
        "regime_bull", "regime_bear", "regime_volatile",
        "cluster_momentum_z", "narrative_price_divergence",
        "roe", "leverage", "earnings_growth", "quality_score",
        "sentiment_level", "sentiment_delta", "entropy_sentiment",
        "entropy_change", "feature_health",
    }
    assert {f.name for f in V1_FEATURES} == expected

def test_placeholders_have_compute_none():
    placeholders = {f.name for f in V1_FEATURES if f.compute is None}
    assert placeholders == set(PLACEHOLDER_NAMES)
