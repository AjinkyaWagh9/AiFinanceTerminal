"""Schema migration + persistence helpers for /analyze 4a."""
from __future__ import annotations

import os
import tempfile

import pytest

from finterminal.data.duckdb_store import (
    get_conn,
    record_analysis,
    record_critique,
    recent_analysis,
)


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DUCKDB_PATH"] = f"{tmp}/test.duckdb"
        c = get_conn()
        yield c
        c.close()


def test_critiques_table_exists(conn):
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    assert "critiques" in tables


def test_analyses_payload_json_column_exists(conn):
    cols = [r[0] for r in conn.execute("DESCRIBE analyses").fetchall()]
    assert "payload_json" in cols


def test_record_analysis_accepts_optional_payload(conn):
    aid = record_analysis(
        conn,
        ticker="RELIANCE.NS",
        bull_case="bull",
        bear_case="bear",
        confidence=0.6,
        sources={"model": "test"},
        payload={"variant_perception": "vp", "conviction": "Watch Long"},
    )
    assert isinstance(aid, str)
    rows = conn.execute(
        "SELECT payload_json FROM analyses WHERE id = ?", [aid]
    ).fetchall()
    assert len(rows) == 1
    assert "Watch Long" in rows[0][0]


def test_record_analysis_payload_optional(conn):
    """Existing call sites that don't pass payload still work (None stored)."""
    aid = record_analysis(
        conn, ticker="X.NS", bull_case="b", bear_case="r", confidence=0.5
    )
    row = conn.execute(
        "SELECT payload_json FROM analyses WHERE id = ?", [aid]
    ).fetchone()
    assert row[0] is None


def test_record_critique_inserts_row(conn):
    aid = record_analysis(
        conn, ticker="RELIANCE.NS", bull_case="b", bear_case="r", confidence=0.6
    )
    cid = record_critique(
        conn,
        analysis_id=aid,
        verdict="REVISE",
        issues_md="- one issue",
        missing_md="- pledge",
        confidence_adj=0.5,
        raw_text="full text",
        model="claude-sonnet-4-6",
        tokens_in=1200,
        tokens_out=380,
        degraded=False,
        error=None,
    )
    assert isinstance(cid, str)
    row = conn.execute(
        "SELECT verdict, confidence_adj, degraded, error FROM critiques WHERE id = ?",
        [cid],
    ).fetchone()
    assert row[0] == "REVISE"
    assert row[1] == 0.5
    assert row[2] is False
    assert row[3] is None


def test_record_critique_can_be_degraded(conn):
    aid = record_analysis(
        conn, ticker="X.NS", bull_case="b", bear_case="r", confidence=0.4
    )
    cid = record_critique(
        conn, analysis_id=aid, verdict=None, issues_md="", missing_md="",
        confidence_adj=None, raw_text="", model=None,
        tokens_in=0, tokens_out=0, degraded=True, error="timeout after 30s",
    )
    row = conn.execute(
        "SELECT degraded, error FROM critiques WHERE id = ?", [cid]
    ).fetchone()
    assert row[0] is True
    assert row[1] == "timeout after 30s"


def test_recent_analysis_returns_none_when_empty(conn):
    assert recent_analysis(conn, "GHOST.NS", ttl_s=300) is None


def test_recent_analysis_returns_within_ttl(conn):
    aid = record_analysis(
        conn,
        ticker="RELIANCE.NS",
        bull_case="bull",
        bear_case="bear",
        confidence=0.6,
        sources={"model": "test"},
        payload={"variant_perception": "vp", "conviction": "Watch Long"},
    )
    record_critique(
        conn, analysis_id=aid, verdict="ACCEPT", issues_md="",
        missing_md="", confidence_adj=0.6, raw_text="x",
        model="m", tokens_in=10, tokens_out=10, degraded=False, error=None,
    )
    out = recent_analysis(conn, "RELIANCE.NS", ttl_s=300)
    assert out is not None
    assert out["analysis_id"] == aid
    assert out["analyst_payload"]["conviction"] == "Watch Long"
    assert out["critic_payload"]["verdict"] == "ACCEPT"


def test_recent_analysis_stale_returns_none(conn):
    record_analysis(conn, ticker="OLD.NS", bull_case="b", bear_case="r", confidence=0.5)
    # Negative TTL → everything is stale.
    assert recent_analysis(conn, "OLD.NS", ttl_s=-1) is None
