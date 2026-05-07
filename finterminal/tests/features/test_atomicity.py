# tests/features/test_atomicity.py
from datetime import datetime, date
from unittest.mock import patch
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.schema import SignalType

def _seed_nifty(conn):
    upsert_prices_eod(conn, [{
        "trade_date": date(2026,4,28),"ticker":"_NIFTY50",
        "open":22000,"high":22000,"low":22000,"close":22000.0,"volume":0,
    }], source="nse_indices")

def test_emit_signal_writes_features(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0),
        payload={"story_count_delta": 5.0, "cluster_id": "c1"},
    )
    n = conn.execute(
        "SELECT COUNT(*) FROM signal_features WHERE signal_id=?", [sid]
    ).fetchone()[0]
    assert n == 20   # 20 computable (15 base + 5 reflexivity, all real after #4)

def test_emit_signal_rolls_back_when_features_throw(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    with patch("finterminal.outcomes.ledger.compute_for_signal",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            emit_signal(conn,
                signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
                ts_emitted=datetime(2026, 4, 29, 10, 0),
                payload={"cluster_id": "c1"},
            )
    n_signals  = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    n_outcomes = conn.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()[0]
    n_features = conn.execute("SELECT COUNT(*) FROM signal_features").fetchone()[0]
    assert (n_signals, n_outcomes, n_features) == (0, 0, 0)


def test_emit_signal_rolls_back_when_upsert_features_throws(tmp_path):
    # Covers the path where compute succeeds but the store layer fails.
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    with patch("finterminal.features.store.upsert_features",
               side_effect=RuntimeError("store-boom")):
        with pytest.raises(RuntimeError):
            emit_signal(conn,
                signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
                ts_emitted=datetime(2026, 4, 29, 10, 0),
                payload={"cluster_id": "c1"},
            )
    n_signals  = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    n_outcomes = conn.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()[0]
    n_features = conn.execute("SELECT COUNT(*) FROM signal_features").fetchone()[0]
    assert (n_signals, n_outcomes, n_features) == (0, 0, 0)


def test_compute_for_signal_stub_forwards_to_real_orchestrator(tmp_path):
    # Pin the stub-forward contract: the module-level stub in outcomes.ledger
    # must lazy-load and return the orchestrator's full 18-key dict.
    from finterminal.outcomes.ledger import compute_for_signal
    from finterminal.features.registry import V1_FEATURES
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    out = compute_for_signal(
        conn, signal_id="test-sid",
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0), payload={"cluster_id": "c1"},
    )
    assert set(out.keys()) == {f.name for f in V1_FEATURES}
