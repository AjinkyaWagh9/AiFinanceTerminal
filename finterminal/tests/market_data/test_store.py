# tests/market_data/test_store.py
from datetime import date, datetime
import uuid
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import (
    upsert_prices_eod, last_close_on_or_before,
    log_start, log_finish,
)

def _seed_rows(trade_date):
    return [
        {"trade_date": trade_date, "ticker": "TCS",
         "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000},
        {"trade_date": trade_date, "ticker": "RELIANCE",
         "open": 200.0, "high": 210.0, "low": 195.0, "close": 205.0, "volume": 2000},
    ]

def test_upsert_writes_and_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    rows = _seed_rows(date(2026, 4, 29))
    n1 = upsert_prices_eod(conn, rows, source="nse_bhavcopy")
    n2 = upsert_prices_eod(conn, rows, source="nse_bhavcopy")
    assert n1 == 2 and n2 == 0
    total = conn.execute("SELECT COUNT(*) FROM prices_eod").fetchone()[0]
    assert total == 2

def test_last_close_finds_latest_on_or_before(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [
        {"trade_date": date(2026,4,27),"ticker":"TCS","open":1,"high":1,"low":1,"close":100.0,"volume":0},
        {"trade_date": date(2026,4,29),"ticker":"TCS","open":1,"high":1,"low":1,"close":105.0,"volume":0},
    ], source="nse_bhavcopy")
    assert last_close_on_or_before(conn, "TCS", date(2026, 4, 28)) == 100.0
    assert last_close_on_or_before(conn, "TCS", date(2026, 4, 29)) == 105.0
    assert last_close_on_or_before(conn, "TCS", date(2026, 4, 26)) is None

def test_ingestion_log_lifecycle(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    log_id = log_start(conn, source="nse_bhavcopy", target_date=date(2026, 4, 29))
    log_finish(conn, log_id, status="ok", rows_written=2)
    row = conn.execute("SELECT status, rows_written, finished_at FROM ingestion_log WHERE id=?", [log_id]).fetchone()
    assert row[0] == "ok" and row[1] == 2 and row[2] is not None
