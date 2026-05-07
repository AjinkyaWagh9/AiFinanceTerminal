# tests/outcomes/test_backfill.py
from datetime import datetime, date, timedelta
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.backfill import resolve_pending
from finterminal.outcomes.schema import SignalType, MACRO_TICKER
from finterminal.market_data.store import upsert_prices_eod

def _seed(conn, tcs_then, tcs_thN, nifty_then, nifty_thN, ts_then, ts_thN):
    upsert_prices_eod(conn, [
        {"trade_date": ts_then,"ticker":"TCS","open":1,"high":1,"low":1,"close":tcs_then,"volume":0},
        {"trade_date": ts_thN,"ticker":"TCS","open":1,"high":1,"low":1,"close":tcs_thN,"volume":0},
        {"trade_date": ts_then,"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":nifty_then,"volume":0},
        {"trade_date": ts_thN,"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":nifty_thN,"volume":0},
    ], source="nse_bhavcopy")

def test_resolve_pending_computes_ret_and_alpha(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    ts_then, ts_thN = date(2026, 4, 22), date(2026, 4, 29)  # 7 days
    _seed(conn, tcs_then=100.0, tcs_thN=110.0,        # TCS +10%
                nifty_then=22000.0, nifty_thN=22220.0, # Nifty +1%
                ts_then=ts_then, ts_thN=ts_thN)
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 22, 10, 0),
    )
    n = resolve_pending(conn, today=date(2026, 5, 30))
    assert n >= 1
    row = conn.execute(
        "SELECT ret_pct, ret_pct_vs_nifty FROM signal_outcomes "
        "WHERE signal_id=? AND horizon_days=7", [sid]
    ).fetchone()
    assert row[0] == pytest.approx(0.10, rel=1e-9)
    assert row[1] == pytest.approx(0.10 - 0.01, rel=1e-9)

def test_resolve_pending_skips_when_prices_missing(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [
        {"trade_date": date(2026,4,22),"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":22000.0,"volume":0},
    ], source="nse_indices")
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 22, 10, 0),
    )
    resolve_pending(conn, today=date(2026, 5, 30))
    row = conn.execute(
        "SELECT ret_pct, resolved_at FROM signal_outcomes "
        "WHERE signal_id=? AND horizon_days=7", [sid]
    ).fetchone()
    assert row[0] is None and row[1] is None

def test_macro_ticker_resolves_against_nifty(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, tcs_then=100.0, tcs_thN=110.0, nifty_then=22000.0, nifty_thN=22220.0,
          ts_then=date(2026,4,22), ts_thN=date(2026,4,29))
    sid = emit_signal(conn,
        signal_type=SignalType.REGIME_SHIFT, ticker=MACRO_TICKER,
        ts_emitted=datetime(2026, 4, 22, 10, 0),
    )
    resolve_pending(conn, today=date(2026, 5, 30))
    row = conn.execute(
        "SELECT ret_pct, ret_pct_vs_nifty FROM signal_outcomes "
        "WHERE signal_id=? AND horizon_days=7", [sid]
    ).fetchone()
    assert row[0] == pytest.approx(0.01, rel=1e-9)         # nifty's own ret
    assert row[1] == pytest.approx(0.0, abs=1e-12)         # alpha is zero
