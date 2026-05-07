# tests/outcomes/test_ledger.py
from datetime import datetime, date, timezone
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.schema import SignalType, HORIZONS_DAYS
from finterminal.market_data.store import upsert_prices_eod

def _seed_nifty(conn):
    upsert_prices_eod(conn, [{
        "trade_date": date(2026,4,28),"ticker":"_NIFTY50",
        "open":22000,"high":22000,"low":22000,"close":22000.0,"volume":0,
    }], source="nse_indices")

def test_emit_signal_writes_signal_plus_5_outcome_stubs(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0),
        payload={"cluster_id": "c1", "story_count_delta": 5},
        confidence=0.5, why="grew 5", source_ref="c1",
    )
    assert sid is not None
    n_signals = conn.execute("SELECT COUNT(*) FROM signals WHERE signal_id=?", [sid]).fetchone()[0]
    n_out     = conn.execute("SELECT COUNT(*) FROM signal_outcomes WHERE signal_id=?", [sid]).fetchone()[0]
    assert n_signals == 1 and n_out == len(HORIZONS_DAYS)

def test_emit_signal_idempotent_on_duplicate(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    kw = dict(signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
              ts_emitted=datetime(2026, 4, 29, 10, 0),
              payload={"cluster_id": "c1"}, confidence=0.5, why="x", source_ref="c1")
    sid1 = emit_signal(conn, **kw)
    sid2 = emit_signal(conn, **kw)
    assert sid1 is not None and sid2 is None
    n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    assert n == 1

def test_emit_signal_rejects_unknown_signal_type(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    with pytest.raises((ValueError, KeyError)):
        emit_signal(conn, signal_type="not_a_real_type", ticker="TCS",
                    ts_emitted=datetime(2026, 4, 29, 10, 0))

def test_emit_signal_snapshots_regime(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0),
    )
    nifty = conn.execute(
        "SELECT regime_nifty_close FROM signals WHERE signal_id=?", [sid]
    ).fetchone()[0]
    assert nifty == 22000.0


def test_emit_signal_normalizes_tzaware_to_ist_naive(tmp_path):
    # 2026-04-29 23:00 UTC == 2026-04-30 04:30 IST. Stored ts_emitted must be
    # the IST wall-clock, and regime must be snapshot on the IST date so the
    # row's regime matches its stored timestamp.
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [{
        "trade_date": date(2026, 4, 29), "ticker": "_NIFTY50",
        "open": 22000, "high": 22000, "low": 22000, "close": 22000.0, "volume": 0,
    }], source="nse_indices")
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 23, 0, tzinfo=timezone.utc),
    )
    row = conn.execute(
        "SELECT ts_emitted, regime_nifty_close FROM signals WHERE signal_id=?",
        [sid],
    ).fetchone()
    assert row[0] == datetime(2026, 4, 30, 4, 30)  # IST wall-clock, naive
    assert row[1] == 22000.0  # regime snapshot used 2026-04-29 (last close ≤ IST date)


def test_emit_signal_dedups_across_naive_and_tzaware_inputs(tmp_path):
    # Same instant expressed two ways (naive IST vs UTC tz-aware) must dedup.
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    naive_ist = datetime(2026, 4, 30, 4, 30)
    tzaware_utc = datetime(2026, 4, 29, 23, 0, tzinfo=timezone.utc)
    sid1 = emit_signal(conn, signal_type=SignalType.CLUSTER_MOMENTUM,
                       ticker="TCS", ts_emitted=naive_ist)
    sid2 = emit_signal(conn, signal_type=SignalType.CLUSTER_MOMENTUM,
                       ticker="TCS", ts_emitted=tzaware_utc)
    assert sid1 is not None and sid2 is None
