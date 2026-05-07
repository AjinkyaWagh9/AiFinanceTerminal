from finterminal.data.duckdb_store import connect
from finterminal.features.store import upsert_features

def test_upsert_writes_value_and_missing_rows(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {
        "mom_7d":    {"value": 0.05, "is_missing": False},
        "vol_20d":   {"value": None, "is_missing": True},
    })
    rows = conn.execute(
        "SELECT feature_name, feature_value, is_missing "
        "FROM signal_features WHERE signal_id=? ORDER BY feature_name",
        ["sig1"],
    ).fetchall()
    assert rows == [("mom_7d", 0.05, False), ("vol_20d", None, True)]

def test_upsert_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {"mom_7d": {"value": 0.05, "is_missing": False}})
    upsert_features(conn, "sig1", {"mom_7d": {"value": 0.07, "is_missing": False}})
    rows = conn.execute(
        "SELECT feature_value FROM signal_features WHERE signal_id=?",
        ["sig1"],
    ).fetchall()
    assert rows == [(0.07,)]   # second write wins (overwrite semantics)


def test_upsert_stores_n_samples_confidence_version(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.25, "is_missing": False,
                            "n_samples": 8, "confidence": 0.8,
                            "feature_version": "reflexivity_v1_vader_decay_0.5",
                            "normalized": False},
    })
    row = conn.execute(
        "SELECT feature_value, is_missing, n_samples, confidence, feature_version, normalized "
        "FROM signal_features WHERE signal_id='sig1' AND feature_name='sentiment_level'",
    ).fetchone()
    assert row == (0.25, False, 8, 0.8, "reflexivity_v1_vader_decay_0.5", False)


def test_upsert_stores_none_for_non_reflexivity_features(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {
        "mom_7d": {"value": 0.05, "is_missing": False},
    })
    row = conn.execute(
        "SELECT n_samples, confidence, feature_version FROM signal_features "
        "WHERE signal_id='sig1' AND feature_name='mom_7d'",
    ).fetchone()
    assert row == (None, None, None)


def test_upsert_freeze_same_version_does_not_overwrite(tmp_path):
    """Same (signal_id, feature_name, feature_version) → upsert is no-op.
    Protects historical truth from accidental recompute."""
    conn = connect(str(tmp_path / "t.duckdb"))
    v = "reflexivity_v1_vader_decay_0.5"
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.25, "is_missing": False,
                            "n_samples": 5, "confidence": 0.5,
                            "feature_version": v},
    })
    # Attempt to overwrite with same version, different value
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.99, "is_missing": False,
                            "n_samples": 99, "confidence": 1.0,
                            "feature_version": v},
    })
    row = conn.execute(
        "SELECT feature_value, n_samples FROM signal_features "
        "WHERE signal_id='sig1' AND feature_name='sentiment_level'",
    ).fetchone()
    assert row == (0.25, 5), "freeze violated: same-version write must not overwrite"


def test_upsert_different_version_overwrites(tmp_path):
    """Different feature_version → overwrite allowed. That's how we evolve VADER → FinBERT."""
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.25, "is_missing": False,
                            "n_samples": 5, "confidence": 0.5,
                            "feature_version": "reflexivity_v1_vader_decay_0.5"},
    })
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.42, "is_missing": False,
                            "n_samples": 7, "confidence": 0.7,
                            "feature_version": "reflexivity_v2_finbert"},
    })
    row = conn.execute(
        "SELECT feature_value, n_samples, feature_version FROM signal_features "
        "WHERE signal_id='sig1' AND feature_name='sentiment_level'",
    ).fetchone()
    assert row == (0.42, 7, "reflexivity_v2_finbert")
