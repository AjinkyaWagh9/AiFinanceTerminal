"""Tests for ml/predictor.py — cold-start, stale-model guard, SHAP, writeback.

Spec §4.5 + §4.6 + §7 + §8 + §10.

TDD order: import/interface assertions first, then full round-trip tests.
"""
from __future__ import annotations

import json
import os
import pickle
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.store import upsert_features
from finterminal.features.registry import V1_FEATURES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NIFTY = "_NIFTY50"
ALL_FEATURE_NAMES = [f.name for f in V1_FEATURES]
HORIZONS = [7, 30, 90]

# ---------------------------------------------------------------------------
# Helpers (mirrors test_trainer.py helpers)
# ---------------------------------------------------------------------------


def _make_conn(tmp_path: Path):
    return connect(str(tmp_path / "t.duckdb"))


def _seed_nifty(conn, n_days: int = 500, start: date | None = None) -> None:
    start = start or date(2022, 1, 1)
    rows = [
        {
            "trade_date": start + timedelta(days=i),
            "ticker": NIFTY,
            "open": 20000.0,
            "high": 20000.0,
            "low": 20000.0,
            "close": 20000.0 * (1.001 ** i),
            "volume": 0,
        }
        for i in range(n_days)
    ]
    upsert_prices_eod(conn, rows, source="test")


def _seed_signal(
    conn,
    signal_id: str,
    ts_emitted: datetime,
    signal_type: str = "cluster_momentum",
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO signals
            (signal_id, signal_type, engine, ticker, ts_emitted, payload)
        VALUES (?, ?, 'test', 'TCS', ?, '{}')
        """,
        [signal_id, signal_type, ts_emitted],
    )


def _seed_outcome(
    conn,
    signal_id: str,
    ts_emitted: datetime,
    ret_pct_vs_nifty: float,
    horizon_days: int,
) -> None:
    resolved_at = ts_emitted + timedelta(days=horizon_days)
    conn.execute(
        """
        INSERT OR IGNORE INTO signal_outcomes
            (signal_id, horizon_days, ret_pct, ret_pct_vs_nifty, resolved_at)
        VALUES (?, ?, 0.0, ?, ?)
        """,
        [signal_id, horizon_days, ret_pct_vs_nifty, resolved_at],
    )


def _seed_full_features(
    conn,
    signal_id: str,
    feature_version: str,
) -> None:
    features = {
        spec.name: {
            "value": 0.5,
            "is_missing": False,
            "feature_version": feature_version,
        }
        for spec in V1_FEATURES
    }
    upsert_features(conn, signal_id, features)


def _seed_training_data(
    conn,
    horizon_days: int,
    n: int,
    feature_version: str,
    start_ts: datetime | None = None,
) -> None:
    """Seed n resolved signals with features and outcomes for training."""
    rng = np.random.default_rng(seed=42)
    start_ts = start_ts or datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    sigma_proxy = 0.001

    for i in range(n):
        sid = str(uuid.uuid4())
        ts = start_ts + timedelta(days=i)
        cycle = i % 3
        if cycle == 0:
            ret = sigma_proxy * 10
        elif cycle == 1:
            ret = 0.0
        else:
            ret = -sigma_proxy * 10
        ret += float(rng.uniform(-sigma_proxy * 0.1, sigma_proxy * 0.1))

        _seed_signal(conn, sid, ts)
        _seed_outcome(conn, sid, ts, ret, horizon_days=horizon_days)
        _seed_full_features(conn, sid, feature_version=feature_version)


def _train_model(conn, tmp_path: Path, feature_version: str, n: int = 150) -> str:
    """Train a model for h=7 only (fast). Returns model_version."""
    from finterminal.ml.trainer import train_all

    _seed_nifty(conn)
    _seed_training_data(conn, horizon_days=7, n=n, feature_version=feature_version)

    now_utc = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    artifacts_root = tmp_path / "artifacts"
    current_symlink = tmp_path / "current"

    bundle = train_all(
        conn=conn,
        horizons=[7],
        feature_version=feature_version,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        now=now_utc,
    )
    return bundle.model_version


def _seed_predict_signal(conn, feature_version: str) -> str:
    """Seed a single signal (no outcome needed) for predict() tests."""
    sid = str(uuid.uuid4())
    ts = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    _seed_signal(conn, sid, ts)
    _seed_full_features(conn, sid, feature_version=feature_version)
    return sid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_predict_returns_cold_start_cells_when_no_current_symlink(tmp_path):
    """When current symlink is absent, predict() returns 3 cold-start cells."""
    from finterminal.ml.predictor import predict

    conn = _make_conn(tmp_path)
    fake_symlink = tmp_path / "current"
    assert not fake_symlink.exists()

    cells = predict(conn, str(uuid.uuid4()), current_symlink=fake_symlink)

    assert isinstance(cells, list), "predict must return a list"
    assert len(cells) == 3, f"Expected 3 cells (one per horizon), got {len(cells)}"

    for cell in cells:
        assert cell["model_version"] == "cold_start", (
            f"Expected model_version='cold_start', got {cell['model_version']!r}"
        )
        assert cell["predicted_class"] == "cold_start"
        assert cell["p_bull"] == pytest.approx(1 / 3)
        assert cell["p_base"] == pytest.approx(1 / 3)
        assert cell["p_bear"] == pytest.approx(1 / 3)
        assert sorted(cell["conformal_set"]) == ["base", "bear", "bull"]
        assert cell["shap_top"] == []

    # Check all 3 horizons are present
    horizons_returned = {c["horizon_days"] for c in cells}
    assert horizons_returned == {7, 30, 90}


def test_predict_returns_cold_start_when_feature_version_mismatches(tmp_path):
    """When manifest.feature_version differs from FEATURE_VERSION, all cells cold-start."""
    from finterminal.ml.predictor import predict
    from finterminal.features.compute_reflexivity import FEATURE_VERSION as LIVE_VERSION

    conn = _make_conn(tmp_path)
    bogus_fv = "bogus_v0"
    assert bogus_fv != LIVE_VERSION, "bogus_fv must differ from live FEATURE_VERSION"

    _train_model(conn, tmp_path, feature_version=bogus_fv, n=150)

    sid = _seed_predict_signal(conn, feature_version=LIVE_VERSION)
    current_symlink = tmp_path / "current"
    assert current_symlink.exists(), "symlink must be created by train_model"

    cells = predict(conn, sid, current_symlink=current_symlink)

    assert isinstance(cells, list)
    assert len(cells) == 3
    for cell in cells:
        assert cell["model_version"] == "cold_start", (
            f"Expected cold_start due to feature_version mismatch, got {cell['model_version']!r}"
        )


def test_predict_returns_3_probs_summing_to_one(tmp_path):
    """For a real model, predict() returns probs that sum to 1 within float tolerance."""
    from finterminal.ml.predictor import predict
    from finterminal.features.compute_reflexivity import FEATURE_VERSION

    conn = _make_conn(tmp_path)
    _train_model(conn, tmp_path, feature_version=FEATURE_VERSION, n=150)

    sid = _seed_predict_signal(conn, feature_version=FEATURE_VERSION)
    current_symlink = tmp_path / "current"

    cells = predict(conn, sid, current_symlink=current_symlink)

    # At least the h=7 cell should be non-cold-start
    real_cells = [c for c in cells if c["model_version"] != "cold_start"]
    assert real_cells, "Expected at least one non-cold-start cell for h=7"

    for cell in real_cells:
        total = cell["p_bull"] + cell["p_base"] + cell["p_bear"]
        assert abs(total - 1.0) < 1e-9, (
            f"h={cell['horizon_days']}: probs sum to {total}, expected 1.0"
        )


def test_predict_includes_shap_top_5_with_signed_values(tmp_path):
    """Predict returns shap_top with ≤5 entries of (str, float) and at least one non-zero."""
    from finterminal.ml.predictor import predict
    from finterminal.features.compute_reflexivity import FEATURE_VERSION

    conn = _make_conn(tmp_path)
    _train_model(conn, tmp_path, feature_version=FEATURE_VERSION, n=150)

    sid = _seed_predict_signal(conn, feature_version=FEATURE_VERSION)
    current_symlink = tmp_path / "current"

    cells = predict(conn, sid, current_symlink=current_symlink)

    real_cells = [c for c in cells if c["model_version"] != "cold_start"]
    assert real_cells, "Need at least one real prediction to test SHAP"

    for cell in real_cells:
        shap_top = cell["shap_top"]
        assert isinstance(shap_top, list), "shap_top must be a list"
        assert len(shap_top) <= 5, f"shap_top must have ≤5 entries, got {len(shap_top)}"
        for entry in shap_top:
            assert len(entry) == 2, f"Each shap entry must be [name, value], got {entry!r}"
            assert isinstance(entry[0], str), f"Feature name must be str, got {type(entry[0])}"
            assert isinstance(entry[1], float), f"SHAP value must be float, got {type(entry[1])}"
        if shap_top:
            any_nonzero = any(v != 0.0 for _, v in shap_top)
            assert any_nonzero, "Expected at least one non-zero SHAP value"


def test_predict_returns_cold_start_for_horizon_below_threshold(tmp_path):
    """When model file for a horizon is absent (cold-start skip in trainer),
    predict() returns cold-start for that horizon while other horizons are real."""
    from finterminal.ml.predictor import predict
    from finterminal.features.compute_reflexivity import FEATURE_VERSION
    from finterminal.ml.trainer import train_all

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)
    n = 150

    # Seed data for h=7 only (enough rows) — h=30, h=90 get no rows → cold-start
    _seed_training_data(conn, horizon_days=7, n=n, feature_version=FEATURE_VERSION)

    now_utc = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    artifacts_root = tmp_path / "artifacts"
    current_symlink = tmp_path / "current"

    # Train all 3 horizons but only 7d has ≥100 rows
    train_all(
        conn=conn,
        horizons=[7, 30, 90],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        now=now_utc,
    )

    sid = _seed_predict_signal(conn, feature_version=FEATURE_VERSION)
    cells = predict(conn, sid, current_symlink=current_symlink)

    by_horizon = {c["horizon_days"]: c for c in cells}

    # h=7 should be a real prediction
    assert by_horizon[7]["model_version"] != "cold_start", (
        "h=7 should have a real model (≥100 rows were seeded)"
    )
    # h=30 and h=90 should be cold-start (no model file)
    assert by_horizon[30]["model_version"] == "cold_start", (
        "h=30 should be cold_start (no model file)"
    )
    assert by_horizon[90]["model_version"] == "cold_start", (
        "h=90 should be cold_start (no model file)"
    )


def test_batch_backfill_writes_rows_to_signal_predictions(tmp_path):
    """batch_backfill writes N*3 rows into signal_predictions."""
    from finterminal.ml.predictor import batch_backfill
    from finterminal.features.compute_reflexivity import FEATURE_VERSION

    conn = _make_conn(tmp_path)
    _train_model(conn, tmp_path, feature_version=FEATURE_VERSION, n=150)

    n_signals = 3
    base_ts = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    for i in range(n_signals):
        _seed_predict_signal(conn, feature_version=FEATURE_VERSION)

    current_symlink = tmp_path / "current"
    since_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

    rows_written = batch_backfill(conn, since_ts, current_symlink=current_symlink)

    assert rows_written > 0, "Expected rows to be written"

    total_in_db = conn.execute("SELECT COUNT(*) FROM signal_predictions").fetchone()[0]
    assert total_in_db == rows_written, (
        f"DB has {total_in_db} rows but backfill reported {rows_written}"
    )


def test_batch_backfill_skips_already_predicted_signals(tmp_path):
    """Second call to batch_backfill with same since_ts returns 0 new rows."""
    from finterminal.ml.predictor import batch_backfill
    from finterminal.features.compute_reflexivity import FEATURE_VERSION

    conn = _make_conn(tmp_path)
    _train_model(conn, tmp_path, feature_version=FEATURE_VERSION, n=150)

    for _ in range(2):
        _seed_predict_signal(conn, feature_version=FEATURE_VERSION)

    current_symlink = tmp_path / "current"
    since_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

    first_count = batch_backfill(conn, since_ts, current_symlink=current_symlink)
    assert first_count > 0

    second_count = batch_backfill(conn, since_ts, current_symlink=current_symlink)
    assert second_count == 0, (
        f"Second backfill should write 0 rows (PK guard), but wrote {second_count}"
    )


def test_predict_serializes_conformal_set_as_comma_joined_sorted(tmp_path):
    """batch_backfill → signal_predictions.conformal_set is sorted-comma-joined."""
    from finterminal.ml.predictor import batch_backfill
    from finterminal.features.compute_reflexivity import FEATURE_VERSION

    conn = _make_conn(tmp_path)
    _train_model(conn, tmp_path, feature_version=FEATURE_VERSION, n=150)

    _seed_predict_signal(conn, feature_version=FEATURE_VERSION)

    current_symlink = tmp_path / "current"
    since_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    batch_backfill(conn, since_ts, current_symlink=current_symlink)

    rows = conn.execute(
        "SELECT conformal_set FROM signal_predictions"
    ).fetchall()

    assert rows, "No rows in signal_predictions"
    for (cs,) in rows:
        assert cs is not None, "conformal_set must not be NULL"
        parts = cs.split(",")
        # Must be sorted
        assert parts == sorted(parts), (
            f"conformal_set '{cs}' is not sorted; expected comma-joined sorted order"
        )
        # Every part must be a valid class name or a superset
        valid = {"bear", "base", "bull"}
        for p in parts:
            assert p in valid, f"Unknown class in conformal_set: {p!r}"
