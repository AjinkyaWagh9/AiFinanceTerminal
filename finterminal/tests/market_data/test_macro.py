# tests/market_data/test_macro.py
from datetime import date
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.market_data.macro import snapshot_regime

def _seed_nifty(conn, series):
    rows = [{"trade_date": d, "ticker": "_NIFTY50",
             "open": v, "high": v, "low": v, "close": v, "volume": 0}
            for d, v in series]
    upsert_prices_eod(conn, rows, source="nse_indices")

def test_snapshot_regime_pct_50d_uses_50_trading_days_back(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    series = [(date.fromordinal(date(2026,1,1).toordinal()+i), 22000 + i*5)
              for i in range(120)]  # 120 calendar days, monotonic
    _seed_nifty(conn, series)
    snap = snapshot_regime(conn, as_of=date(2026, 4, 29))
    assert snap["regime_nifty_close"] == 22000 + (date(2026,4,29).toordinal()-date(2026,1,1).toordinal())*5
    # 50 calendar days back exists in series; pct should be > 0
    assert snap["regime_nifty_pct_50d"] > 0

def test_snapshot_regime_handles_missing_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    snap = snapshot_regime(conn, as_of=date(2026, 4, 29))
    assert snap["regime_nifty_close"] is None
    assert snap["regime_nifty_pct_50d"] is None
