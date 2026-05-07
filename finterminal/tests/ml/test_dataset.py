"""Tests for ml/dataset.py — leakage-free training matrix builder.

Spec §4.2 + §8 + §10.

Conventions:
  - Use connect() from finterminal.data.duckdb_store (tmp_path fixture).
  - Naive timestamps (IST) per migration headers.
  - Seeds minimal but complete signal_features rows via upsert_features.
  - Nifty history seeded where label_outcomes requires it.
"""
from __future__ import annotations

import math
import statistics
import uuid
from datetime import date, datetime, timedelta
from typing import Callable

import pytest

from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.store import upsert_features
from finterminal.features.registry import V1_FEATURES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NIFTY = "_NIFTY50"
FEATURE_VERSION = "v1_test"
HORIZON = 30
ALL_FEATURE_NAMES = [f.name for f in V1_FEATURES]  # 20 names


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_nifty(conn, n_days: int = 300, start: date | None = None) -> None:
    """Seed n_days of Nifty closes so label_outcomes can compute sigma."""
    start = start or date(2023, 1, 1)
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


def _sigma_for_ts(conn, ts_emitted: datetime) -> float:
    """Compute sigma the same way labels.py does, so we can set ret above/below it."""
    target_date = ts_emitted.date()
    rows = conn.execute(
        "SELECT close FROM prices_eod WHERE ticker=? AND trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 253",
        [NIFTY, target_date],
    ).fetchall()
    closes = [r[0] for r in rows][::-1]
    log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    return statistics.stdev(log_rets)


def _seed_signal(
    conn,
    signal_id: str,
    ts_emitted: datetime,
    signal_type: str = "cluster_momentum",
) -> None:
    """Insert a minimal signals row."""
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
    horizon_days: int = HORIZON,
    resolved: bool = True,
) -> None:
    """Insert a signal_outcomes row."""
    resolved_at = ts_emitted + timedelta(days=horizon_days) if resolved else None
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
    feature_version: str = FEATURE_VERSION,
    missing_names: list[str] | None = None,
) -> None:
    """Upsert all 20 V1 features for a signal; any name in missing_names gets is_missing=True."""
    missing_names = missing_names or []
    features = {}
    for spec in V1_FEATURES:
        is_miss = spec.name in missing_names
        features[spec.name] = {
            "value": None if is_miss else 0.5,
            "is_missing": is_miss,
            "feature_version": feature_version,
        }
    upsert_features(conn, signal_id, features)


def _make_conn(tmp_path) -> object:
    return connect(str(tmp_path / "t.duckdb"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_until_ts_cut_excludes_unresolved_horizons(tmp_path):
    """One resolved signal (ts + horizon < until_ts) and one that would peek.

    Only the resolved one must appear in the matrix.
    """
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    # ts_emitted at day 270 (well into the 300 days seeded)
    base_date = date(2023, 1, 1)
    ts_resolved = datetime(2023, 10, 1, 10, 0)    # day ~273
    ts_peeking = datetime(2023, 10, 15, 10, 0)    # day ~287

    # until_ts is set so that:
    #   ts_resolved + HORIZON (30d) = 2023-10-31 <= until_ts  ✓
    #   ts_peeking  + HORIZON (30d) = 2023-11-14 > until_ts   ✗
    until_ts = datetime(2023, 11, 5, 0, 0)

    sigma = _sigma_for_ts(conn, ts_resolved)

    sid_ok = str(uuid.uuid4())
    sid_peek = str(uuid.uuid4())

    _seed_signal(conn, sid_ok, ts_resolved)
    _seed_outcome(conn, sid_ok, ts_resolved, sigma * 2)  # bull
    _seed_full_features(conn, sid_ok)

    _seed_signal(conn, sid_peek, ts_peeking)
    _seed_outcome(conn, sid_peek, ts_peeking, sigma * 2)  # would be bull — but peeking
    _seed_full_features(conn, sid_peek)

    X, y, meta = build_matrix(conn, HORIZON, FEATURE_VERSION, until_ts)

    assert meta.n_rows == 1, f"Expected 1 row (resolved only), got {meta.n_rows}"
    assert sid_ok in meta.signal_ids
    assert sid_peek not in meta.signal_ids


def test_feature_version_filter_excludes_other_versions(tmp_path):
    """Seed two signals with different feature_versions; matrix must only have requested version."""
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    ts_v1 = datetime(2023, 10, 1, 10, 0)
    ts_v2 = datetime(2023, 10, 1, 11, 0)  # different ts to avoid UNIQUE(type,ticker,ts)
    until_ts = datetime(2024, 1, 1)
    sigma = _sigma_for_ts(conn, ts_v1)

    sid_v1 = str(uuid.uuid4())
    sid_v2 = str(uuid.uuid4())

    _seed_signal(conn, sid_v1, ts_v1)
    _seed_outcome(conn, sid_v1, ts_v1, sigma * 2)
    _seed_full_features(conn, sid_v1, feature_version="v1_test")

    _seed_signal(conn, sid_v2, ts_v2)
    _seed_outcome(conn, sid_v2, ts_v2, sigma * 2)
    _seed_full_features(conn, sid_v2, feature_version="v2_other")

    X, y, meta = build_matrix(conn, HORIZON, "v1_test", until_ts)

    assert meta.n_rows == 1
    assert sid_v1 in meta.signal_ids
    assert sid_v2 not in meta.signal_ids


def test_drops_rows_with_any_missing_feature(tmp_path):
    """Signal with one is_missing=True feature must be excluded; n_dropped_for_missing reflects it."""
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    ts_complete = datetime(2023, 10, 1, 10, 0)
    ts_incomplete = datetime(2023, 10, 1, 11, 0)  # different ts to avoid UNIQUE(type,ticker,ts)
    until_ts = datetime(2024, 1, 1)
    sigma = _sigma_for_ts(conn, ts_complete)

    sid_complete = str(uuid.uuid4())
    sid_incomplete = str(uuid.uuid4())

    _seed_signal(conn, sid_complete, ts_complete)
    _seed_outcome(conn, sid_complete, ts_complete, sigma * 2)
    _seed_full_features(conn, sid_complete)

    _seed_signal(conn, sid_incomplete, ts_incomplete)
    _seed_outcome(conn, sid_incomplete, ts_incomplete, sigma * 2)
    _seed_full_features(conn, sid_incomplete, missing_names=["sentiment_level"])  # one missing

    X, y, meta = build_matrix(conn, HORIZON, FEATURE_VERSION, until_ts)

    assert meta.n_rows == 1, f"Incomplete row should be dropped, got {meta.n_rows}"
    assert meta.n_dropped_for_missing >= 1
    assert sid_complete in meta.signal_ids
    assert sid_incomplete not in meta.signal_ids


def test_label_encoding_bull_base_bear_to_2_1_0(tmp_path):
    """Verify y encodes: bull=2, base=1, bear=0."""
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    ts = datetime(2023, 10, 1, 10, 0)
    until_ts = datetime(2024, 1, 1)
    sigma = _sigma_for_ts(conn, ts)

    def seed_one(label_ret, signal_type="cluster_momentum"):
        sid = str(uuid.uuid4())
        _seed_signal(conn, sid, ts, signal_type=signal_type)
        _seed_outcome(conn, sid, ts, label_ret)
        _seed_full_features(conn, sid)
        return sid

    # Slightly different ts to avoid UNIQUE constraint on (signal_type, ticker, ts_emitted)
    ts_bull = datetime(2023, 10, 1, 10, 0)
    ts_base = datetime(2023, 10, 1, 11, 0)
    ts_bear = datetime(2023, 10, 1, 12, 0)

    sid_bull = str(uuid.uuid4())
    sid_base = str(uuid.uuid4())
    sid_bear = str(uuid.uuid4())

    sigma_bull = _sigma_for_ts(conn, ts_bull)

    for sid, ts_i, ret in [
        (sid_bull, ts_bull, sigma_bull * 2),
        (sid_base, ts_base, 0.0),
        (sid_bear, ts_bear, -sigma_bull * 2),
    ]:
        _seed_signal(conn, sid, ts_i)
        _seed_outcome(conn, sid, ts_i, ret)
        _seed_full_features(conn, sid)

    X, y, meta = build_matrix(conn, HORIZON, FEATURE_VERSION, until_ts)

    sid_to_y = dict(zip(meta.signal_ids, y.tolist()))

    assert sid_to_y[sid_bull] == 2, f"bull should map to 2, got {sid_to_y[sid_bull]}"
    assert sid_to_y[sid_base] == 1, f"base should map to 1, got {sid_to_y[sid_base]}"
    assert sid_to_y[sid_bear] == 0, f"bear should map to 0, got {sid_to_y[sid_bear]}"


def test_extra_feature_builder_invoked_and_columns_added(tmp_path):
    """Pass a builder lambda; assert 'my_extra' appears in meta.feature_columns and X."""
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    ts = datetime(2023, 10, 1, 10, 0)
    until_ts = datetime(2024, 1, 1)
    sigma = _sigma_for_ts(conn, ts)

    sid = str(uuid.uuid4())
    _seed_signal(conn, sid, ts)
    _seed_outcome(conn, sid, ts, sigma * 2)
    _seed_full_features(conn, sid)

    call_log: list[str] = []

    def my_builder(c, signal_id: str) -> dict:
        call_log.append(signal_id)
        return {"my_extra": 0.5}

    X, y, meta = build_matrix(
        conn, HORIZON, FEATURE_VERSION, until_ts,
        extra_feature_builders=[my_builder],
    )

    assert "my_extra" in meta.feature_columns, "extra column must be in meta.feature_columns"
    col_idx = meta.feature_columns.index("my_extra")
    assert X[0, col_idx] == pytest.approx(0.5), "extra column value must be 0.5"
    assert len(call_log) > 0, "builder must have been called at least once"


def test_meta_carries_feature_columns_in_x_column_order(tmp_path):
    """meta.feature_columns[i] names column i of X."""
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    ts = datetime(2023, 10, 1, 10, 0)
    until_ts = datetime(2024, 1, 1)
    sigma = _sigma_for_ts(conn, ts)

    sid = str(uuid.uuid4())
    _seed_signal(conn, sid, ts)
    _seed_outcome(conn, sid, ts, sigma * 2)
    _seed_full_features(conn, sid)

    X, y, meta = build_matrix(conn, HORIZON, FEATURE_VERSION, until_ts)

    assert X.shape[1] == len(meta.feature_columns), (
        f"X has {X.shape[1]} cols but meta.feature_columns has {len(meta.feature_columns)}"
    )
    # Spot-check: the column named 'signal_type_id' must exist
    assert "signal_type_id" in meta.feature_columns


def test_empty_when_no_resolved_signals(tmp_path):
    """No seeds → X.shape == (0, n_features) and y.shape == (0,)."""
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    until_ts = datetime(2024, 1, 1)
    X, y, meta = build_matrix(conn, HORIZON, FEATURE_VERSION, until_ts)

    assert X.ndim == 2
    assert y.ndim == 1
    assert X.shape[0] == 0
    assert y.shape[0] == 0
    assert meta.n_rows == 0


def test_signal_type_encoded_as_categorical_int(tmp_path):
    """signal_type_id column must appear in X and be integer-valued."""
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    ts = datetime(2023, 10, 1, 10, 0)
    until_ts = datetime(2024, 1, 1)
    sigma = _sigma_for_ts(conn, ts)

    sid = str(uuid.uuid4())
    _seed_signal(conn, sid, ts, signal_type="cluster_momentum")
    _seed_outcome(conn, sid, ts, sigma * 2)
    _seed_full_features(conn, sid)

    X, y, meta = build_matrix(conn, HORIZON, FEATURE_VERSION, until_ts)

    assert "signal_type_id" in meta.feature_columns
    col_idx = meta.feature_columns.index("signal_type_id")
    # The value must be a non-negative integer when interpreted as float64
    val = X[0, col_idx]
    assert float(val) == int(val), f"signal_type_id must be integer, got {val}"
    assert val >= 0
