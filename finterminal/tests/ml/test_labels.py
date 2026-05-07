"""Tests for ml/labels.py — vol-scaled bull/base/bear labelling.

Conventions:
  - Use connect() from finterminal.data.duckdb_store (tmp_path fixture).
  - Naive timestamps (IST) per migration headers.
  - Nifty ticker is '_NIFTY50' (same as compute_regime.py / outcomes schema).
"""
from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta

import pytest

from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NIFTY = "_NIFTY50"


def _seed_nifty_prices(conn, start_date: date, closes: list[float]) -> None:
    """Seed a run of consecutive daily Nifty closes starting at start_date."""
    rows = [
        {
            "trade_date": start_date + timedelta(days=i),
            "ticker": NIFTY,
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume": 0,
        }
        for i, c in enumerate(closes)
    ]
    upsert_prices_eod(conn, rows, source="test")


def _seed_signal_with_outcome(
    conn,
    signal_id: str,
    ts_emitted: datetime,
    ret_pct_vs_nifty: float,
    horizon_days: int = 30,
    resolved: bool = True,
) -> None:
    """Insert a minimal signal row + a signal_outcomes row.

    If resolved=False, resolved_at is NULL and ret_pct_vs_nifty is not
    meaningful (labelling must exclude such rows).
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO signals
            (signal_id, signal_type, engine, ticker, ts_emitted, payload)
        VALUES (?, 'cluster_momentum', 'reflexivity', 'TCS', ?, '{}')
        """,
        [signal_id, ts_emitted],
    )
    resolved_at = ts_emitted + timedelta(days=horizon_days) if resolved else None
    conn.execute(
        """
        INSERT OR IGNORE INTO signal_outcomes
            (signal_id, horizon_days, ret_pct, ret_pct_vs_nifty, resolved_at)
        VALUES (?, ?, 0.0, ?, ?)
        """,
        [signal_id, horizon_days, ret_pct_vs_nifty, resolved_at],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_frame(tmp_path):
    """No signals, no outcomes → empty DataFrame with the 3 expected columns."""
    from finterminal.ml.labels import label_outcomes

    conn = connect(str(tmp_path / "t.duckdb"))
    df = label_outcomes(conn, horizon_days=30)

    assert list(df.columns) == ["signal_id", "label", "sigma_used"]
    assert len(df) == 0


def test_unresolved_outcomes_excluded(tmp_path):
    """Seed one unresolved (resolved_at IS NULL) and one resolved outcome.

    Only the resolved one should appear in the output.
    """
    from finterminal.ml.labels import label_outcomes

    conn = connect(str(tmp_path / "t.duckdb"))

    # Seed 300 Nifty trading days so σ can be computed for both signals.
    base_date = date(2024, 1, 1)
    closes = [20000.0 * (1.001 ** i) for i in range(300)]
    _seed_nifty_prices(conn, base_date, closes)

    # Signal emitted after 252 Nifty days are available.
    ts_emitted = datetime(2024, 9, 20, 10, 0)  # well past the 252d window
    sid_resolved = str(uuid.uuid4())
    sid_unresolved = str(uuid.uuid4())

    _seed_signal_with_outcome(conn, sid_resolved, ts_emitted, 0.0, resolved=True)
    _seed_signal_with_outcome(conn, sid_unresolved, ts_emitted, 0.0, resolved=False)

    df = label_outcomes(conn, horizon_days=30)

    assert len(df) == 1
    assert df["signal_id"][0] == sid_resolved


def test_sigma_uses_252d_preceding_window(tmp_path):
    """Sigma is computed from the 252 trading days strictly preceding ts_emitted.

    Regime: 300 quiet days (tiny moves), then 200 volatile days (large moves).
    Signal A is emitted at day 310 (252d window = all quiet).
    Signal B is emitted at day 510 (252d window = mostly volatile).
    sigma_b must be larger than sigma_a.
    """
    from finterminal.ml.labels import label_outcomes

    conn = connect(str(tmp_path / "t.duckdb"))

    base_date = date(2022, 1, 1)

    # 300 quiet days: price barely moves (+0.001% daily)
    quiet_closes = [20000.0 * (1.00001 ** i) for i in range(300)]
    # 200 volatile days: price bounces ±3% alternating
    volatile_closes = []
    p = quiet_closes[-1]
    for i in range(200):
        p = p * (1.03 if i % 2 == 0 else 0.97)
        volatile_closes.append(p)

    all_closes = quiet_closes + volatile_closes  # 500 days
    _seed_nifty_prices(conn, base_date, all_closes)

    # Signal A: emitted at day 310 → 252d window = days 58–309 (all quiet)
    # base_date + 310 days ≈ 2022-11-07
    ts_a = datetime(2022, 11, 7, 10, 0)
    sid_a = str(uuid.uuid4())
    _seed_signal_with_outcome(conn, sid_a, ts_a, 0.0, resolved=True)

    # Signal B: emitted at day 500 → 252d window = days 248–499 (mostly volatile)
    # base_date + 500 days ≈ 2023-05-16
    ts_b = datetime(2023, 5, 16, 10, 0)
    sid_b = str(uuid.uuid4())
    _seed_signal_with_outcome(conn, sid_b, ts_b, 0.0, resolved=True)

    df = label_outcomes(conn, horizon_days=30)
    # Both signals must be labelled (enough history for both)
    assert len(df) == 2, f"Expected 2 labelled rows, got {len(df)}"

    sigma_a = df.filter(df["signal_id"] == sid_a)["sigma_used"][0]
    sigma_b = df.filter(df["signal_id"] == sid_b)["sigma_used"][0]

    # Signal B (volatile window) must have meaningfully larger sigma
    assert sigma_b > sigma_a, (
        f"Expected sigma_b ({sigma_b:.6f}) > sigma_a ({sigma_a:.6f})"
    )


def test_bull_label_when_excess_return_above_sigma(tmp_path):
    """ret_pct_vs_nifty = 2 * sigma → label='bull'."""
    from finterminal.ml.labels import label_outcomes

    conn = connect(str(tmp_path / "t.duckdb"))

    base_date = date(2024, 1, 1)
    closes = [20000.0 * (1.001 ** i) for i in range(300)]
    _seed_nifty_prices(conn, base_date, closes)

    # Compute the actual sigma so we can set ret_pct_vs_nifty = 2 * sigma.
    # Use a ts_emitted that has 252d of prior data available.
    ts_emitted = datetime(2024, 9, 20, 10, 0)

    # Quick sigma estimate from the seeded closes (last 252 before ts).
    target_date = ts_emitted.date()
    nifty_rows = conn.execute(
        "SELECT close FROM prices_eod WHERE ticker=? AND trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 253",
        [NIFTY, target_date],
    ).fetchall()
    closes_252 = [r[0] for r in nifty_rows][::-1]  # oldest first
    log_rets = [
        math.log(closes_252[i] / closes_252[i - 1])
        for i in range(1, len(closes_252))
    ]
    import statistics
    sigma = statistics.stdev(log_rets)

    sid = str(uuid.uuid4())
    _seed_signal_with_outcome(conn, sid, ts_emitted, sigma * 2, resolved=True)

    df = label_outcomes(conn, horizon_days=30)
    assert len(df) == 1
    assert df["label"][0] == "bull"


def test_bear_label_when_excess_return_below_negative_sigma(tmp_path):
    """ret_pct_vs_nifty = -2 * sigma → label='bear'."""
    from finterminal.ml.labels import label_outcomes

    conn = connect(str(tmp_path / "t.duckdb"))

    base_date = date(2024, 1, 1)
    closes = [20000.0 * (1.001 ** i) for i in range(300)]
    _seed_nifty_prices(conn, base_date, closes)

    ts_emitted = datetime(2024, 9, 20, 10, 0)
    target_date = ts_emitted.date()
    nifty_rows = conn.execute(
        "SELECT close FROM prices_eod WHERE ticker=? AND trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 253",
        [NIFTY, target_date],
    ).fetchall()
    closes_252 = [r[0] for r in nifty_rows][::-1]
    log_rets = [
        math.log(closes_252[i] / closes_252[i - 1])
        for i in range(1, len(closes_252))
    ]
    import statistics
    sigma = statistics.stdev(log_rets)

    sid = str(uuid.uuid4())
    _seed_signal_with_outcome(conn, sid, ts_emitted, -sigma * 2, resolved=True)

    df = label_outcomes(conn, horizon_days=30)
    assert len(df) == 1
    assert df["label"][0] == "bear"


def test_base_label_when_excess_return_within_band(tmp_path):
    """ret_pct_vs_nifty = 0.5 * sigma → label='base'."""
    from finterminal.ml.labels import label_outcomes

    conn = connect(str(tmp_path / "t.duckdb"))

    base_date = date(2024, 1, 1)
    closes = [20000.0 * (1.001 ** i) for i in range(300)]
    _seed_nifty_prices(conn, base_date, closes)

    ts_emitted = datetime(2024, 9, 20, 10, 0)
    target_date = ts_emitted.date()
    nifty_rows = conn.execute(
        "SELECT close FROM prices_eod WHERE ticker=? AND trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 253",
        [NIFTY, target_date],
    ).fetchall()
    closes_252 = [r[0] for r in nifty_rows][::-1]
    log_rets = [
        math.log(closes_252[i] / closes_252[i - 1])
        for i in range(1, len(closes_252))
    ]
    import statistics
    sigma = statistics.stdev(log_rets)

    sid = str(uuid.uuid4())
    _seed_signal_with_outcome(conn, sid, ts_emitted, sigma * 0.5, resolved=True)

    df = label_outcomes(conn, horizon_days=30)
    assert len(df) == 1
    assert df["label"][0] == "base"


def test_insufficient_nifty_history_excluded(tmp_path):
    """Only 50 Nifty days seeded; signal requires 252d → row excluded.

    Expect empty output since all signals lack sufficient history.
    """
    from finterminal.ml.labels import label_outcomes

    conn = connect(str(tmp_path / "t.duckdb"))

    # Seed only 50 Nifty days.
    base_date = date(2024, 6, 1)
    closes = [20000.0 * (1.001 ** i) for i in range(50)]
    _seed_nifty_prices(conn, base_date, closes)

    # Signal emitted at day 55 — only 50 prior Nifty days available.
    ts_emitted = datetime(2024, 7, 26, 10, 0)
    sid = str(uuid.uuid4())
    _seed_signal_with_outcome(conn, sid, ts_emitted, 0.05, resolved=True)

    df = label_outcomes(conn, horizon_days=30)
    assert len(df) == 0, (
        f"Expected empty output when Nifty history < 252d; got {len(df)} rows"
    )
