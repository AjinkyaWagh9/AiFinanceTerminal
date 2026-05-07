# tests/features/test_compute_news.py
from datetime import date, datetime, timedelta
import json, uuid
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.features.compute_news import (
    compute_cluster_momentum_z, compute_narrative_price_divergence,
)
from finterminal.outcomes.schema import SignalType, SIGNAL_REGISTRY

def _seed_prior_cluster_signal(conn, ticker, ts, story_count_delta):
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO signals (signal_id, signal_type, engine, ticker, ts_emitted, payload) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [sid, SignalType.CLUSTER_MOMENTUM.value,
         SIGNAL_REGISTRY[SignalType.CLUSTER_MOMENTUM].value,
         ticker, ts, json.dumps({"story_count_delta": story_count_delta})],
    )
    return sid

def test_cluster_momentum_z_missing_when_few_priors(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    val, missing = compute_cluster_momentum_z(
        conn, signal_type=SignalType.CLUSTER_MOMENTUM,
        ticker="TCS", ts_emitted=datetime(2026, 4, 30, 10, 0),
        payload={"story_count_delta": 5},
    )
    assert val is None and missing is True

def test_cluster_momentum_z_happy_path(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    base = datetime(2026, 4, 30, 10, 0)
    # 35 prior signals with story_count_delta uniform in [0..34], mean=17, std≈10.246
    for i in range(35):
        _seed_prior_cluster_signal(conn, "TCS", base - timedelta(days=i+1), float(i))
    val, missing = compute_cluster_momentum_z(
        conn, signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=base, payload={"story_count_delta": 30.0},
    )
    assert missing is False
    assert val == pytest.approx((30 - 17) / 10.246, rel=1e-2)

def test_cluster_momentum_z_placeholder_for_other_signal_types(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    val, missing = compute_cluster_momentum_z(
        conn, signal_type=SignalType.SENTIMENT_DELTA, ticker="TCS",
        ts_emitted=datetime(2026, 4, 30, 10, 0), payload={},
    )
    assert val is None and missing is True

def test_narrative_price_divergence_subtracts_z_of_both(tmp_path):
    val, missing = compute_narrative_price_divergence(
        cluster_momentum_z=2.0, mom_7d_z=0.5,
    )
    assert missing is False and val == pytest.approx(1.5)

def test_narrative_price_divergence_missing_when_either_input_missing(tmp_path):
    val, missing = compute_narrative_price_divergence(cluster_momentum_z=None, mom_7d_z=0.5)
    assert val is None and missing is True
    val, missing = compute_narrative_price_divergence(cluster_momentum_z=2.0, mom_7d_z=None)
    assert val is None and missing is True
