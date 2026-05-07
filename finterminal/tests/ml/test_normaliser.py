"""Tests for ml/normaliser.py — z-norm with leakage-safe write-back.

Spec §4.3 + §8 + §10.

Tests are written before the implementation (TDD order). They use
minimal synthetic data — no need for the full dataset pipeline.
"""
from __future__ import annotations

import numpy as np
import pytest

from finterminal.data.duckdb_store import connect
from finterminal.features.store import upsert_features


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FEATURE_VERSION = "v_norm_test"


def _make_conn(tmp_path):
    return connect(str(tmp_path / "n.duckdb"))


def _seed_signal_features(
    conn,
    signal_ids: list[str],
    feature_names: list[str],
    feature_version: str = FEATURE_VERSION,
) -> None:
    """Seed signal_features rows (normalized=FALSE by default)."""
    for sid in signal_ids:
        features = {
            name: {
                "value": 1.0,
                "is_missing": False,
                "feature_version": feature_version,
                "normalized": False,
            }
            for name in feature_names
        }
        upsert_features(conn, sid, features)


def _make_meta(
    signal_ids: list[str],
    feature_columns: list[str],
    feature_version: str = FEATURE_VERSION,
):
    """Build a minimal MatrixMeta without invoking the full dataset pipeline."""
    from finterminal.ml.dataset import MatrixMeta
    from datetime import datetime

    return MatrixMeta(
        signal_ids=list(signal_ids),
        feature_columns=list(feature_columns),
        feature_version=feature_version,
        horizon_days=30,
        until_ts=datetime(2025, 1, 1),
        n_rows=len(signal_ids),
        n_dropped_for_missing=0,
    )


def _make_X(n_rows: int, n_cols: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n_rows, n_cols))


def _get_normalized_flag(conn, signal_id: str, feature_name: str, feature_version: str) -> bool:
    row = conn.execute(
        "SELECT normalized FROM signal_features "
        "WHERE signal_id=? AND feature_name=? AND feature_version=?",
        [signal_id, feature_name, feature_version],
    ).fetchone()
    if row is None:
        raise ValueError(f"Row not found: {signal_id}/{feature_name}/{feature_version}")
    return bool(row[0])


# ---------------------------------------------------------------------------
# Pure math tests (no DB needed for these)
# ---------------------------------------------------------------------------


def test_fit_transform_columns_have_zero_mean_unit_std():
    """After fit_transform, X_z columns have mean ≈ 0 and std ≈ 1 (within 1e-6)."""
    import duckdb
    from finterminal.ml.normaliser import fit_transform

    # Use an in-memory connection with no signal_features table touched
    # (meta.signal_ids is empty → write-back touches nothing)
    conn = duckdb.connect(":memory:")
    # Create stub table so UPDATE doesn't fail
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_features (
            signal_id VARCHAR, feature_name VARCHAR,
            feature_version VARCHAR, normalized BOOLEAN DEFAULT FALSE,
            feature_value DOUBLE, is_missing BOOLEAN DEFAULT FALSE,
            n_samples INTEGER, confidence DOUBLE
        )
    """)

    feat_cols = ["f0", "f1", "f2", "f3"]
    X = _make_X(50, 4, seed=7)
    meta = _make_meta([], feat_cols)  # empty signal_ids → no DB rows

    X_z, scaler = fit_transform(conn, X, meta)

    for i, col in enumerate(feat_cols):
        col_mean = float(np.mean(X_z[:, i]))
        col_std = float(np.std(X_z[:, i], ddof=0))
        assert abs(col_mean) < 1e-6, f"col {col} mean not ~0: {col_mean}"
        assert abs(col_std - 1.0) < 1e-6, f"col {col} std not ~1: {col_std}"


def test_zero_variance_column_does_not_explode():
    """A column with stdev=0 must return 0s (clamped), no NaN/Inf."""
    import duckdb
    from finterminal.ml.normaliser import fit_transform

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_features (
            signal_id VARCHAR, feature_name VARCHAR,
            feature_version VARCHAR, normalized BOOLEAN DEFAULT FALSE,
            feature_value DOUBLE, is_missing BOOLEAN DEFAULT FALSE,
            n_samples INTEGER, confidence DOUBLE
        )
    """)

    # First column is constant (std=0), second varies
    X = np.ones((20, 2), dtype=np.float64)
    X[:, 1] = np.arange(20, dtype=np.float64)

    feat_cols = ["const_feat", "varying_feat"]
    meta = _make_meta([], feat_cols)

    X_z, scaler = fit_transform(conn, X, meta)

    # Constant column should be all zeros (0 - mean) / clamped_std
    assert np.all(X_z[:, 0] == 0.0), "constant column should normalize to zeros"
    assert not np.any(np.isnan(X_z)), "no NaNs after clamped normalisation"
    assert not np.any(np.isinf(X_z)), "no Infs after clamped normalisation"
    assert scaler.stds[0] == pytest.approx(1e-9), "clamped std should be 1e-9"


def test_transform_with_stored_scaler_matches_fit_transform_output():
    """transform(X, scaler) should produce the same X_z as fit_transform returned."""
    import duckdb
    from finterminal.ml.normaliser import fit_transform, transform

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_features (
            signal_id VARCHAR, feature_name VARCHAR,
            feature_version VARCHAR, normalized BOOLEAN DEFAULT FALSE,
            feature_value DOUBLE, is_missing BOOLEAN DEFAULT FALSE,
            n_samples INTEGER, confidence DOUBLE
        )
    """)

    feat_cols = ["a", "b", "c"]
    X = _make_X(30, 3, seed=99)
    meta = _make_meta([], feat_cols)

    X_z_fit, scaler = fit_transform(conn, X, meta)
    X_z_transform = transform(X, scaler)

    np.testing.assert_array_almost_equal(X_z_fit, X_z_transform, decimal=12)


def test_transform_rejects_wrong_n_features():
    """transform() must raise ValueError if X.shape[1] != len(scaler.feature_columns)."""
    import duckdb
    from finterminal.ml.normaliser import fit_transform, transform

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_features (
            signal_id VARCHAR, feature_name VARCHAR,
            feature_version VARCHAR, normalized BOOLEAN DEFAULT FALSE,
            feature_value DOUBLE, is_missing BOOLEAN DEFAULT FALSE,
            n_samples INTEGER, confidence DOUBLE
        )
    """)

    feat_cols = ["x", "y", "z"]
    X = _make_X(10, 3, seed=1)
    meta = _make_meta([], feat_cols)
    _, scaler = fit_transform(conn, X, meta)

    # Pass matrix with wrong number of columns
    X_wrong = _make_X(5, 5, seed=2)
    with pytest.raises(ValueError, match="[Ff]eature"):
        transform(X_wrong, scaler)


# ---------------------------------------------------------------------------
# Leakage-guard tests (require real DB)
# ---------------------------------------------------------------------------


def test_writeback_flips_normalized_only_for_matrix_signal_ids(tmp_path):
    """THE LEAKAGE GUARD TEST.

    Seed signal_features for A, B, C. Pass meta with signal_ids=[A, B] only.
    After fit_transform: A and B rows → normalized=TRUE; C rows → normalized=FALSE.
    """
    from finterminal.ml.normaliser import fit_transform

    conn = _make_conn(tmp_path)
    feat_cols = ["feat_x", "feat_y"]
    signal_ids_all = ["sig_A", "sig_B", "sig_C"]
    _seed_signal_features(conn, signal_ids_all, feat_cols)

    meta = _make_meta(["sig_A", "sig_B"], feat_cols)
    X = _make_X(2, 2)
    fit_transform(conn, X, meta)

    # A and B must be TRUE
    for sid in ("sig_A", "sig_B"):
        for fname in feat_cols:
            flag = _get_normalized_flag(conn, sid, fname, FEATURE_VERSION)
            assert flag is True, f"{sid}/{fname} should be normalized=TRUE"

    # C must remain FALSE
    for fname in feat_cols:
        flag = _get_normalized_flag(conn, "sig_C", fname, FEATURE_VERSION)
        assert flag is False, f"sig_C/{fname} should remain normalized=FALSE (leakage guard)"


def test_writeback_only_touches_features_in_meta_columns(tmp_path):
    """Only features named in meta.feature_columns get flipped; others stay FALSE."""
    from finterminal.ml.normaliser import fit_transform

    conn = _make_conn(tmp_path)
    all_feat_names = [f"feat_{i}" for i in range(6)]
    meta_feat_names = all_feat_names[:3]   # only first 3
    other_feat_names = all_feat_names[3:]  # last 3 untouched

    signal_ids = ["sid_p", "sid_q"]
    _seed_signal_features(conn, signal_ids, all_feat_names)

    meta = _make_meta(signal_ids, meta_feat_names)
    X = _make_X(2, 3)
    fit_transform(conn, X, meta)

    for sid in signal_ids:
        for fname in meta_feat_names:
            flag = _get_normalized_flag(conn, sid, fname, FEATURE_VERSION)
            assert flag is True, f"{sid}/{fname} (in meta) should be TRUE"
        for fname in other_feat_names:
            flag = _get_normalized_flag(conn, sid, fname, FEATURE_VERSION)
            assert flag is False, f"{sid}/{fname} (not in meta) should stay FALSE"


def test_rerunning_on_disjoint_cut_does_not_alter_prior_cut_rows(tmp_path):
    """Run fit_transform on [A,B] then on [C,D].

    After both: A,B still TRUE; C,D TRUE; no rollbacks.
    """
    from finterminal.ml.normaliser import fit_transform

    conn = _make_conn(tmp_path)
    feat_cols = ["f1", "f2"]
    all_sids = ["cut1_A", "cut1_B", "cut2_C", "cut2_D"]
    _seed_signal_features(conn, all_sids, feat_cols)

    # Cut 1: fit on A, B
    meta1 = _make_meta(["cut1_A", "cut1_B"], feat_cols)
    X1 = _make_X(2, 2, seed=10)
    fit_transform(conn, X1, meta1)

    # Cut 2 (disjoint): fit on C, D
    meta2 = _make_meta(["cut2_C", "cut2_D"], feat_cols)
    X2 = _make_X(2, 2, seed=20)
    fit_transform(conn, X2, meta2)

    # A and B should still be TRUE (not rolled back by cut 2)
    for sid in ("cut1_A", "cut1_B"):
        for fname in feat_cols:
            flag = _get_normalized_flag(conn, sid, fname, FEATURE_VERSION)
            assert flag is True, f"{sid}/{fname} should still be TRUE after cut2"

    # C and D should now be TRUE
    for sid in ("cut2_C", "cut2_D"):
        for fname in feat_cols:
            flag = _get_normalized_flag(conn, sid, fname, FEATURE_VERSION)
            assert flag is True, f"{sid}/{fname} should be TRUE after cut2"


def test_writeback_respects_feature_version_filter(tmp_path):
    """The feature_version clause in the WHERE must be honoured.

    Two signals seeded with different feature_versions (v1 vs v2).
    meta.signal_ids includes BOTH signals but meta.feature_version='v1'.
    Only the v1-versioned rows should be flipped; v2 rows stay FALSE.

    Because signal_features PK is (signal_id, feature_name), each signal
    has exactly one row per feature_name — the version is stored as a column.
    We use two distinct signals (sid_v1, sid_v2) seeded with different
    feature_version values; the UPDATE WHERE feature_version='v1' must
    touch only sid_v1's row.
    """
    from finterminal.ml.normaliser import fit_transform

    conn = _make_conn(tmp_path)
    feat_cols = ["score"]
    sid_v1 = "ver_sig_v1"
    sid_v2 = "ver_sig_v2"

    # sid_v1 seeded with feature_version='v1'
    _seed_signal_features(conn, [sid_v1], feat_cols, feature_version="v1")
    # sid_v2 seeded with feature_version='v2'
    _seed_signal_features(conn, [sid_v2], feat_cols, feature_version="v2")

    # meta includes BOTH signals but requests version 'v1'
    meta = _make_meta([sid_v1, sid_v2], feat_cols, feature_version="v1")
    X = _make_X(2, 1)
    fit_transform(conn, X, meta)

    flag_v1 = _get_normalized_flag(conn, sid_v1, "score", "v1")
    flag_v2 = _get_normalized_flag(conn, sid_v2, "score", "v2")

    assert flag_v1 is True, "v1 row should be normalized=TRUE"
    assert flag_v2 is False, "v2 row should remain normalized=FALSE (version filter)"
