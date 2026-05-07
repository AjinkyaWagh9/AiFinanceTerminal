from datetime import date, datetime
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.freshness import (
    last_prices_date, is_prices_data_fresh, is_nifty_data_fresh,
)
from finterminal.data.duckdb_store import upsert_fundamentals
from finterminal.features.freshness import (
    last_fundamentals_date, is_fundamentals_data_fresh,
)

def _seed(conn, ticker: str, last_date: date):
    upsert_prices_eod(conn, [{
        "trade_date": last_date, "ticker": ticker,
        "open":0.0, "high":0.0, "low":0.0, "close":100.0, "volume":0,
    }], source="test")

def test_last_prices_date_returns_none_when_no_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert last_prices_date(conn, "TCS", as_of=date(2026, 4, 30)) is None

def test_last_prices_date_ignores_future_rows(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 4, 28))
    _seed(conn, "TCS", date(2026, 5, 5))   # future relative to as_of
    assert last_prices_date(conn, "TCS", as_of=date(2026, 4, 30)) == date(2026, 4, 28)

def test_is_prices_data_fresh_within_threshold(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 4, 28))
    assert is_prices_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is True

def test_is_prices_data_fresh_stale(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 4, 20))   # 10 days before ts_emitted
    assert is_prices_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is False

def test_is_prices_data_fresh_no_data_at_all(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert is_prices_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is False

def test_is_nifty_data_fresh_uses_nifty_ticker(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "_NIFTY50", date(2026, 4, 28))
    assert is_nifty_data_fresh(
        conn, ts_emitted=datetime(2026, 4, 30, 10, 0)) is True
    # Stale Nifty
    conn2 = connect(str(tmp_path / "t2.duckdb"))
    _seed(conn2, "_NIFTY50", date(2026, 4, 20))
    assert is_nifty_data_fresh(
        conn2, ts_emitted=datetime(2026, 4, 30, 10, 0)) is False


def _seed_fundamentals(conn, ticker: str, as_of: date, roe: float = 0.15):
    upsert_fundamentals(conn, {
        "ticker": ticker, "as_of": as_of,
        "roe": roe, "debt_to_equity": 1.0,
        "net_income_ttm": 1000.0,
    })

def test_last_fundamentals_date_returns_none_when_no_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert last_fundamentals_date(conn, "TCS", as_of=date(2026, 4, 30)) is None

def test_last_fundamentals_date_ignores_future_rows(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_fundamentals(conn, "TCS", date(2026, 1, 1))
    _seed_fundamentals(conn, "TCS", date(2026, 7, 1))  # future relative to as_of
    assert last_fundamentals_date(conn, "TCS", as_of=date(2026, 4, 30)) == date(2026, 1, 1)

def test_is_fundamentals_data_fresh_within_threshold(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_fundamentals(conn, "TCS", date(2026, 2, 1))  # 88 days before ts_emitted
    assert is_fundamentals_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is True

def test_is_fundamentals_data_fresh_stale(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_fundamentals(conn, "TCS", date(2025, 12, 1))  # > 120 days before ts_emitted
    assert is_fundamentals_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is False

def test_is_fundamentals_data_fresh_no_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert is_fundamentals_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is False
