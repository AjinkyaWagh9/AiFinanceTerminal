"""Tests for NewsTrendAgent — Protocol conformance + happy/error paths."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from finterminal.agents.base import Agent, AgentContext, AgentResult
from finterminal.agents.news_trend import NewsTrendAgent
from finterminal.news.pipeline import PipelineResult
from datetime import date


def _fake_pipeline(conn) -> PipelineResult:
    return PipelineResult(as_of=date.today(), n_stories=10, n_clusters=3, n_lineage_links=2, runtime_s=1.2)


def _failing_pipeline(conn):
    raise RuntimeError("feed timeout")


def test_news_trend_agent_implements_protocol():
    agent = NewsTrendAgent(pipeline=_fake_pipeline)
    assert isinstance(agent, Agent)


def test_agent_name_and_is_llm():
    agent = NewsTrendAgent(pipeline=_fake_pipeline)
    assert agent.name == "news_trend"
    assert agent.is_llm is False


def test_agent_run_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from finterminal.data.duckdb_store import get_conn
    conn = get_conn()
    ctx = AgentContext(ticker="RELIANCE", conn=conn)
    agent = NewsTrendAgent(pipeline=_fake_pipeline)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is True
    assert result.payload["n_clusters"] == 3
    conn.close()


def test_agent_run_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from finterminal.data.duckdb_store import get_conn
    conn = get_conn()
    ctx = AgentContext(ticker="RELIANCE", conn=conn)
    agent = NewsTrendAgent(pipeline=_failing_pipeline)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "feed timeout" in (result.error or "")
    conn.close()


def test_analyze_flow_registry_still_3_agents():
    """Ensure analyze_flow.py is not accidentally importing NewsTrendAgent."""
    import inspect
    import finterminal.agents.analyze_flow as af
    src = inspect.getsource(af)
    assert "news_trend" not in src
