# tests/integration/test_features_e2e.py
from datetime import date, datetime, timedelta
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.schema import SignalType
from finterminal.features.registry import V1_FEATURES, PLACEHOLDER_NAMES

def _seed_full(conn):
    # 120 days of TCS prices
    upsert_prices_eod(conn, [{
        "trade_date": date(2026,1,1) + timedelta(days=i),
        "ticker":"TCS","open":0.0,"high":0.0,"low":0.0,
        "close":100.0+i,"volume":0,
    } for i in range(120)], source="test")
    # 485 days of Nifty
    upsert_prices_eod(conn, [{
        "trade_date": date(2025,1,1) + timedelta(days=i),
        "ticker":"_NIFTY50","open":0.0,"high":0.0,"low":0.0,
        "close":20000.0 + i*2,"volume":0,
    } for i in range(485)], source="test")

def test_e2e_signal_emits_full_feature_row(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)

    sid = emit_signal(
        conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0),
        payload={"cluster_id":"c1","story_count_delta":3.0},
    )
    assert sid is not None

    rows = conn.execute(
        "SELECT feature_name, feature_value, is_missing "
        "FROM signal_features WHERE signal_id=? ORDER BY feature_name",
        [sid],
    ).fetchall()
    by_name = {r[0]: (r[1], r[2]) for r in rows}

    # All 18 registered features present
    assert set(by_name.keys()) == {f.name for f in V1_FEATURES}
    # Placeholders missing
    for name in PLACEHOLDER_NAMES:
        assert by_name[name] == (None, True)
    # Computables that have enough seed data
    assert by_name["mom_7d"][1] is False         # 7d history present
    assert by_name["nifty_return_50d"][1] is False
    assert by_name["regime_bull"][1] is False
    # cluster_momentum_z requires ≥30 prior cluster_momentum signals — none seeded
    assert by_name["cluster_momentum_z"][1] is True
