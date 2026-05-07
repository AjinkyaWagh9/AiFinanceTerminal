# tests/features/test_compute_regime.py
from datetime import date, datetime
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.compute_regime import (
    compute_nifty_return_50d, compute_nifty_vol_20d,
    compute_regime_bull, compute_regime_bear, compute_regime_volatile,
)

def _seed_nifty(conn, start: date, n: int, base: float, step: float):
    rows = [{
        "trade_date": date.fromordinal(start.toordinal() + i),
        "ticker": "_NIFTY50", "open":0.0,"high":0.0,"low":0.0,
        "close": base + i*step, "volume": 0,
    } for i in range(n)]
    upsert_prices_eod(conn, rows, source="test")

def test_nifty_return_50d_uptrend(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2026, 1, 1), 100, base=20000, step=10)
    val, missing = compute_nifty_return_50d(conn, ts_emitted=datetime(2026, 4, 10, 10, 0))
    assert missing is False and val > 0

def test_nifty_return_50d_missing_when_short_history(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2026, 4, 1), 10, base=20000, step=10)
    val, missing = compute_nifty_return_50d(conn, ts_emitted=datetime(2026, 4, 10, 10, 0))
    assert val is None and missing is True

def test_regime_bull_when_uptrend_and_low_vol(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2025, 5, 1), 280, base=20000, step=2)   # smooth uptrend, low vol
    ts = datetime(2026, 2, 1, 10, 0)
    bull, _   = compute_regime_bull(conn, ts_emitted=ts)
    bear, _   = compute_regime_bear(conn, ts_emitted=ts)
    vol, _    = compute_regime_volatile(conn, ts_emitted=ts)
    assert (bull, bear, vol) == (1.0, 0.0, 0.0)

def test_regime_bear_when_downtrend(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2025, 5, 1), 280, base=22000, step=-3)
    ts = datetime(2026, 2, 1, 10, 0)
    bull, _ = compute_regime_bull(conn, ts_emitted=ts)
    bear, _ = compute_regime_bear(conn, ts_emitted=ts)
    assert (bull, bear) == (0.0, 1.0)

def test_regime_one_hot_sums_to_one(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2025, 5, 1), 280, base=20000, step=2)
    ts = datetime(2026, 2, 1, 10, 0)
    s = sum(c(conn, ts_emitted=ts)[0] for c in
            (compute_regime_bull, compute_regime_bear, compute_regime_volatile))
    assert s == 1.0
