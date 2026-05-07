# tests/outcomes/test_queries.py
from datetime import datetime, date
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.backfill import resolve_pending
from finterminal.outcomes.queries import predictive_power, engine_summary
from finterminal.outcomes.schema import SignalType, Engine
from finterminal.market_data.store import upsert_prices_eod

def _seed(conn, ret_tcs_pct, ret_nifty_pct):
    upsert_prices_eod(conn, [
        {"trade_date": date(2026,4,22),"ticker":"TCS","open":1,"high":1,"low":1,"close":100.0,"volume":0},
        {"trade_date": date(2026,4,29),"ticker":"TCS","open":1,"high":1,"low":1,"close":100.0*(1+ret_tcs_pct),"volume":0},
        {"trade_date": date(2026,4,22),"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":22000.0,"volume":0},
        {"trade_date": date(2026,4,29),"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":22000.0*(1+ret_nifty_pct),"volume":0},
    ], source="nse_bhavcopy")

def test_predictive_power_returns_shape(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, ret_tcs_pct=0.10, ret_nifty_pct=0.01)
    emit_signal(conn, signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
                ts_emitted=datetime(2026, 4, 22, 10, 0))
    resolve_pending(conn, today=date(2026, 5, 30))
    res = predictive_power(conn, signal_type=SignalType.CLUSTER_MOMENTUM, horizon=7)
    assert set(res.keys()) >= {"n", "mean_ret", "mean_alpha"}
    assert res["n"] == 1
    assert res["mean_ret"] == pytest.approx(0.10, rel=1e-9)
    assert res["mean_alpha"] == pytest.approx(0.09, rel=1e-9)

def test_engine_summary_aggregates(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, ret_tcs_pct=0.05, ret_nifty_pct=0.0)
    emit_signal(conn, signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
                ts_emitted=datetime(2026, 4, 22, 10, 0))
    resolve_pending(conn, today=date(2026, 5, 30))
    res = engine_summary(conn, engine=Engine.REFLEXIVITY, horizon=7)
    assert res["n"] >= 1
