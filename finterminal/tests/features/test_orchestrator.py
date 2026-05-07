# tests/features/test_orchestrator.py
from datetime import date, datetime
import json, uuid
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.outcomes.schema import SignalType
from finterminal.features.registry import COMPUTABLE_NAMES, V1_FEATURES
from finterminal.features.orchestrator import compute_for_signal

def _seed_full(conn):
    # Equity ticker history
    rows = [{"trade_date": date.fromordinal(date(2026,1,1).toordinal()+i),
             "ticker":"TCS","open":0.0,"high":0.0,"low":0.0,
             "close":100.0+i,"volume":0} for i in range(120)]
    upsert_prices_eod(conn, rows, source="test")
    # Nifty history
    rows = [{"trade_date": date.fromordinal(date(2025,1,1).toordinal()+i),
             "ticker":"_NIFTY50","open":0.0,"high":0.0,"low":0.0,
             "close":20000.0+i*2,"volume":0} for i in range(485)]
    upsert_prices_eod(conn, rows, source="test")

def test_compute_for_signal_output_keys_match_registry(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    sig_id = str(uuid.uuid4())
    out = compute_for_signal(
        conn, signal_id=sig_id,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0),
        payload={"story_count_delta": 3.0, "cluster_id": "c1"},
    )
    assert set(out.keys()) == {f.name for f in V1_FEATURES}

def test_compute_for_signal_marks_cluster_z_missing_for_other_signal_types(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    out = compute_for_signal(
        conn, signal_id=str(uuid.uuid4()),
        signal_type=SignalType.SENTIMENT_DELTA, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0), payload={},
    )
    assert out["cluster_momentum_z"]["is_missing"] is True
    assert out["narrative_price_divergence"]["is_missing"] is True

def test_quality_features_present_in_output(tmp_path):
    """All four quality features must be in the output dict, even if is_missing."""
    from finterminal.data.duckdb_store import connect as _connect
    conn = _connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [{
        "trade_date": date(2026, 4, 28), "ticker": "_NIFTY50",
        "open": 22000, "high": 22000, "low": 22000, "close": 22000.0, "volume": 0,
    }], source="nse_indices")
    out = compute_for_signal(
        conn, signal_id="test-q", signal_type=SignalType.CLUSTER_MOMENTUM,
        ticker="TCS", ts_emitted=datetime(2026, 4, 29, 10, 0),
        payload={"cluster_id": "c1"},
    )
    for name in ("roe", "leverage", "earnings_growth", "quality_score"):
        assert name in out, f"{name} missing from orchestrator output"
        assert "value" in out[name] and "is_missing" in out[name]

def test_quality_features_computed_when_fundamentals_seeded(tmp_path):
    """With 3+ tickers fundamentals seeded, quality features should not be missing."""
    from finterminal.data.duckdb_store import connect as _connect, upsert_fundamentals
    conn = _connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [{
        "trade_date": date(2026, 4, 28), "ticker": "_NIFTY50",
        "open": 22000, "high": 22000, "low": 22000, "close": 22000.0, "volume": 0,
    }], source="nse_indices")
    as_of = date(2026, 1, 1)
    as_of_prev = date(2025, 10, 1)
    for ticker, roe, d2e, ni_curr, ni_prev in [
        ("TCS",   0.20, 0.3, 1200.0, 1000.0),
        ("INFY",  0.15, 0.5, 900.0,  800.0),
        ("WIPRO", 0.10, 0.8, 500.0,  450.0),
    ]:
        upsert_fundamentals(conn, {"ticker": ticker, "as_of": as_of,
                                   "roe": roe, "debt_to_equity": d2e,
                                   "net_income_ttm": ni_curr})
        upsert_fundamentals(conn, {"ticker": ticker, "as_of": as_of_prev,
                                   "net_income_ttm": ni_prev})
    out = compute_for_signal(
        conn, signal_id="test-q2", signal_type=SignalType.CLUSTER_MOMENTUM,
        ticker="TCS", ts_emitted=datetime(2026, 4, 29, 10, 0),
        payload={"cluster_id": "c1"},
    )
    assert out["roe"]["is_missing"]            is False
    assert out["leverage"]["is_missing"]       is False
    assert out["earnings_growth"]["is_missing"] is False
    assert out["quality_score"]["is_missing"]   is False

def test_reflexivity_features_present_in_output(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    out = compute_for_signal(
        conn, signal_id="test-r1",
        signal_type=SignalType.SENTIMENT_DELTA, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0), payload={},
    )
    for name in ("sentiment_level", "sentiment_delta",
                 "entropy_sentiment", "entropy_change", "feature_health"):
        assert name in out, f"{name} missing"
        assert "value" in out[name] and "is_missing" in out[name]


def test_no_placeholder_features_remain():
    from finterminal.features.registry import PLACEHOLDER_NAMES
    assert PLACEHOLDER_NAMES == ()


def test_compute_for_signal_returns_20_keys(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    out = compute_for_signal(
        conn, signal_id="test-r2",
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0),
        payload={"story_count_delta": 3.0, "cluster_id": "c1"},
    )
    from finterminal.features.registry import V1_FEATURES
    assert set(out.keys()) == {f.name for f in V1_FEATURES}
    assert len(out) == 20
