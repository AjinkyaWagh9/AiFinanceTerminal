# tests/outcomes/test_wiring.py
from datetime import datetime
from unittest.mock import patch
from finterminal.data.duckdb_store import connect


def test_cluster_pipeline_emits_signals_when_flag_on(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOMES_LEDGER_ENABLED", "1")
    conn = connect(str(tmp_path / "t.duckdb"))
    # Drive the news pipeline in test mode with one synthetic cluster carrying delta=+5.
    # Implementation: use the same fixture loader the existing news tests use; if absent,
    # call lineage.match() directly on a small in-memory pair and then invoke the wiring
    # function exposed in news/pipeline.py.
    from finterminal.news.pipeline import _emit_cluster_momentum_signals  # added in Step 3
    _emit_cluster_momentum_signals(conn, [
        {"cluster_id": "c1", "top_tickers": ["TCS"], "story_count": 7,
         "story_count_delta": 5, "first_seen": datetime(2026, 4, 29, 10, 0)},
    ])
    n = conn.execute("SELECT COUNT(*) FROM signals WHERE signal_type='cluster_momentum'").fetchone()[0]
    assert n == 1


def test_emit_signal_failure_does_not_break_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOMES_LEDGER_ENABLED", "1")
    conn = connect(str(tmp_path / "t.duckdb"))
    from finterminal.news.pipeline import _emit_cluster_momentum_signals
    with patch("finterminal.outcomes.ledger.emit_signal",
               side_effect=RuntimeError("boom")):
        _emit_cluster_momentum_signals(conn, [
            {"cluster_id": "c1", "top_tickers": ["TCS"], "story_count": 7,
             "story_count_delta": 5, "first_seen": datetime(2026, 4, 29, 10, 0)},
        ])  # MUST NOT raise


def test_flag_off_skips_emission(tmp_path, monkeypatch):
    monkeypatch.delenv("OUTCOMES_LEDGER_ENABLED", raising=False)
    conn = connect(str(tmp_path / "t.duckdb"))
    from finterminal.news.pipeline import _emit_cluster_momentum_signals
    _emit_cluster_momentum_signals(conn, [
        {"cluster_id": "c1", "top_tickers": ["TCS"], "story_count": 7,
         "story_count_delta": 5, "first_seen": datetime(2026, 4, 29, 10, 0)},
    ])
    n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    assert n == 0
