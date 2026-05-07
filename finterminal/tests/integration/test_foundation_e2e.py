# tests/integration/test_foundation_e2e.py
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.market_data.ingestion import refresh_prices
from finterminal.market_data._http import Http404
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.backfill import resolve_pending
from finterminal.outcomes.queries import predictive_power
from finterminal.outcomes.schema import SignalType

FIX = Path(__file__).parents[1] / "fixtures" / "market_data"

def _fixture_fetch(url: str) -> bytes:
    if "cm29APR2026" in url:
        return (FIX / "cm29APR2026bhav.csv.zip").read_bytes()
    if "29042026" in url:
        return (FIX / "ind_close_all_29042026.csv").read_bytes()
    raise Http404(url)

def test_full_pipeline_emit_then_resolve_then_query(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOMES_LEDGER_ENABLED", "1")
    conn = connect(str(tmp_path / "t.duckdb"))

    # 1. Pipeline A: ingest one day of fixture prices.
    with patch("finterminal.market_data.ingestion._http.fetch", side_effect=_fixture_fetch):
        refresh_prices(conn, start=date(2026, 4, 29), end=date(2026, 4, 29))

    # 2. Synthesize a t+7 row to make the 7d horizon resolvable.
    conn.execute(
        """INSERT INTO prices_eod (trade_date, ticker, close, source, created_at)
           VALUES (?, 'TCS', 3700.0, 'test', ?), (?, '_NIFTY50', 22600.0, 'test', ?)""",
        [date(2026, 5, 6), datetime.now(), date(2026, 5, 6), datetime.now()],
    )

    # 3. Pipeline B: emit a signal at t and resolve at t+30.
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0),
    )
    assert sid is not None
    n = resolve_pending(conn, today=date(2026, 5, 30))
    assert n >= 1

    # 4. Query.
    res = predictive_power(conn, signal_type=SignalType.CLUSTER_MOMENTUM, horizon=7)
    assert res["n"] >= 1
    assert res["mean_ret"] is not None
    assert res["mean_alpha"] is not None
