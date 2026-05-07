"""Data agent: deterministic, parallelized fetches + DuckDB upserts + dossier construction."""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timezone

import pytest

from finterminal.agents.base import AgentContext
from finterminal.agents.data import DataAgent
from finterminal.data.duckdb_store import get_conn


@pytest.fixture
def conn():
    """Fresh DuckDB per test."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DUCKDB_PATH"] = f"{tmp}/test.duckdb"
        c = get_conn()
        yield c
        c.close()


def _stub_quote_ok(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc),
        "last_price": 2945.50,
        "change_pct": 1.2,
        "volume": 4_200_000,
        "market_cap": 2.0e13,
        "provider": "stub",
    }


def _stub_fund_ok(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).date(),
        "pe_ttm": 23.4,
        "eps_ttm": None,
        "roe": 0.091,
        "roce": None,
        "debt_to_equity": 0.45,
        "revenue_ttm": None,
        "net_income_ttm": None,
        "provider": "stub",
    }


def _stub_news_ok(ticker: str, limit: int = 10) -> list[dict]:
    return [
        {"id": "n1", "ticker": ticker, "source": "Moneycontrol",
         "headline": "Q4 profit up 8%", "url": "u1",
         "published_at": "2026-04-26", "body": "..."},
        {"id": "n2", "ticker": ticker, "source": "Livemint",
         "headline": "Jio user adds slow", "url": "u2",
         "published_at": "2026-04-25", "body": "..."},
    ]


def _stub_quote_raise(ticker: str) -> dict:
    raise RuntimeError(f"quote fetch failed for {ticker}")


def _stub_fund_raise(ticker: str) -> dict:
    raise RuntimeError(f"fundamentals fetch failed for {ticker}")


def _stub_news_raise(ticker: str, limit: int = 10) -> list[dict]:
    raise RuntimeError(f"news fetch failed for {ticker}")


def test_data_agent_happy_path(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_ok,
    )
    ctx = AgentContext(ticker="RELIANCE.NS", conn=conn)
    result = asyncio.run(agent.run(ctx))

    assert result.ok is True
    assert result.payload is not None
    p = result.payload
    assert p["quote"]["last_price"] == 2945.50
    assert p["fundamentals"]["pe_ttm"] == 23.4
    assert len(p["news"]) == 2
    assert "[src: quote.last_price]" in p["source_dossier"]
    assert "## Quote" in p["context_block"]
    assert "[src: fundamentals.pe_ttm]" in p["source_dossier"]


def test_data_agent_persists_to_duckdb(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_ok,
    )
    ctx = AgentContext(ticker="RELIANCE.NS", conn=conn)
    asyncio.run(agent.run(ctx))

    rows = conn.execute("SELECT count(*) FROM quotes").fetchone()
    assert rows[0] >= 1
    rows = conn.execute("SELECT count(*) FROM fundamentals").fetchone()
    assert rows[0] >= 1
    rows = conn.execute("SELECT count(*) FROM news").fetchone()
    assert rows[0] == 2


def test_data_agent_quote_failure_returns_not_ok(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_raise,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_ok,
    )
    ctx = AgentContext(ticker="X.NS", conn=conn)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "quote" in (result.error or "").lower()


def test_data_agent_fund_failure_proceeds_with_none(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_raise,
        fetch_news=_stub_news_ok,
    )
    ctx = AgentContext(ticker="RELIANCE.NS", conn=conn)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is True
    assert result.payload["fundamentals"] is None


def test_data_agent_news_failure_proceeds_empty(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_raise,
    )
    ctx = AgentContext(ticker="RELIANCE.NS", conn=conn)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is True
    assert result.payload["news"] == []


def test_data_agent_is_not_llm(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_ok,
    )
    assert agent.is_llm is False
    assert agent.name == "data"
