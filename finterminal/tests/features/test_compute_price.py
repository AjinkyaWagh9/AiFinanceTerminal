# tests/features/test_compute_price.py
from datetime import date, datetime
import math
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.compute_price import (
    compute_mom_7d, compute_mom_30d, compute_vol_20d, compute_mom_7d_z,
)

def _seed_linear_prices(conn, ticker: str, start: date, n: int, base: float, step: float):
    rows = [{
        "trade_date": date.fromordinal(start.toordinal() + i),
        "ticker": ticker, "open": 0.0, "high": 0.0, "low": 0.0,
        "close": base + i * step, "volume": 0,
    } for i in range(n)]
    upsert_prices_eod(conn, rows, source="test")

def test_mom_7d_happy_path(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 4, 1), 30, base=100.0, step=1.0)
    val, missing = compute_mom_7d(conn, ticker="TCS",
                                  ts_emitted=datetime(2026, 4, 30, 10, 0))
    # Last close on or before 2026-04-30 = 100 + 29*1 = 129; 7d earlier 122
    assert missing is False
    assert val == pytest.approx(129/122 - 1, rel=1e-9)

def test_mom_7d_missing_when_insufficient_history(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 4, 28), 3, base=100.0, step=1.0)
    val, missing = compute_mom_7d(conn, ticker="TCS",
                                  ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val is None and missing is True

def test_vol_20d_zero_variance_returns_zero(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 3, 1), 30, base=100.0, step=0.0)
    val, missing = compute_vol_20d(conn, ticker="TCS",
                                   ts_emitted=datetime(2026, 4, 1, 10, 0))
    assert missing is False and val == 0.0

def test_no_leakage_future_prices_ignored(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 4, 1), 30, base=100.0, step=1.0)
    # Add a price 7 days in the FUTURE relative to ts_emitted — must not affect mom_7d
    upsert_prices_eod(conn, [{
        "trade_date": date(2026, 5, 7), "ticker": "TCS",
        "open":0.0, "high":0.0, "low":0.0, "close": 999.0, "volume":0,
    }], source="test")
    val, missing = compute_mom_7d(conn, ticker="TCS",
                                  ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val == pytest.approx(129/122 - 1, rel=1e-9)

def test_d12_stale_prices_force_is_missing(tmp_path):
    # Last close is 10 days before ts_emitted — exceeds MAX_PRICE_STALENESS_DAYS=5.
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 3, 1), 30, base=100.0, step=1.0)
    # Most recent close is 2026-03-30; ts_emitted is 2026-04-30 → 31 days stale.
    val, missing = compute_mom_7d(conn, ticker="TCS",
                                  ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val is None and missing is True
    val, missing = compute_mom_30d(conn, ticker="TCS",
                                   ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val is None and missing is True
    val, missing = compute_vol_20d(conn, ticker="TCS",
                                   ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val is None and missing is True
