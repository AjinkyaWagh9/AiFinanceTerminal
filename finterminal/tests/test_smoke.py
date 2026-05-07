"""Phase 1 smoke tests. Verifies imports + LLM abstraction loads correctly."""

from __future__ import annotations

import os

import pytest


def test_package_imports():
    import finterminal

    assert finterminal.__version__ == "0.1.0"


def test_llm_abstraction_loads():
    from finterminal.llm import build_router

    router = build_router()
    assert router is not None


def test_analyst_resolves_to_a_provider():
    """The Analyst's primary must resolve to *some* registered model.

    Whether the actual provider instantiates depends on which API key is set.
    """
    from finterminal.llm import ProviderError, build_router

    router = build_router()
    registry = router._registry  # type: ignore[attr-defined]

    cfg = router._agents.get("analyst")  # type: ignore[attr-defined]
    primary_name = cfg["primary"]
    assert any(m.name == primary_name for m in registry.all()), (
        f"analyst.primary={primary_name} is not in models.yaml"
    )

    try:
        provider = router.for_agent("analyst")
        assert provider.metadata.name == primary_name
    except ProviderError as exc:
        assert "API_KEY" in str(exc)


def test_unknown_agent_errors_clearly():
    from finterminal.llm import AgentNotConfigured, build_router

    router = build_router()
    with pytest.raises(AgentNotConfigured):
        router.for_agent("nonexistent_agent")


def test_openai_provider_registered():
    """gpt-5-mini resolves through the registry; missing key raises clear error."""
    from finterminal.llm import ProviderError, build_router

    router = build_router()
    registry = router._registry  # type: ignore[attr-defined]

    assert any(m.name == "gpt-5-mini" for m in registry.all())
    assert any(m.name == "gpt-5-nano" for m in registry.all())

    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
            registry.get("gpt-5-mini")
    finally:
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved


def test_xai_uses_openai_compat_under_the_hood():
    """Grok is OpenAI-API-compatible — should resolve via the same provider class."""
    from finterminal.llm import ProviderError, build_router
    from finterminal.llm.providers.openai_compat import OpenAICompatProvider

    router = build_router()
    registry = router._registry  # type: ignore[attr-defined]

    saved = os.environ.pop("GROK_API_KEY", None)
    try:
        with pytest.raises(ProviderError, match="GROK_API_KEY"):
            registry.get("grok-3-mini")
    finally:
        if saved is not None:
            os.environ["GROK_API_KEY"] = saved

    # Sanity check: the provider class wired for the `xai` key is the OpenAI-compat one.
    from finterminal.llm.providers import PROVIDERS

    assert PROVIDERS["xai"] is OpenAICompatProvider
    assert PROVIDERS["openai"] is OpenAICompatProvider


def test_duckdb_migration_runs():
    """Opens a fresh DB and confirms tables were created."""
    import tempfile

    from finterminal.data.duckdb_store import get_conn

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DUCKDB_PATH"] = f"{tmp}/test.duckdb"
        conn = get_conn()
        tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
        assert {"quotes", "fundamentals", "news", "watchlist", "analyses"}.issubset(tables)


def test_nse_normalize():
    from finterminal.data.nse import normalize_ticker

    # Defaults: bare symbol → NSE (Indian-first)
    assert normalize_ticker("RELIANCE") == "RELIANCE.NS"
    assert normalize_ticker("RELIANCE.NS") == "RELIANCE.NS"
    assert normalize_ticker("hdfc", "BSE") == "HDFC.BO"

    # Explicit exchange prefix
    assert normalize_ticker("US:AAPL") == "AAPL"
    assert normalize_ticker("us:tsla") == "TSLA"
    assert normalize_ticker("NSE:HDFC") == "HDFC.NS"
    assert normalize_ticker("BSE:RELIANCE") == "RELIANCE.BO"
    # Idempotent on suffix even with prefix
    assert normalize_ticker("NSE:RELIANCE.NS") == "RELIANCE.NS"


def test_analysis_parser_extracts_all_sections():
    from finterminal.agents.analyst import parse_analysis

    sample = """## Bull Case
- Margin expansion likely [src: fundamentals.roe]
- Revenue trend up [src: fundamentals.revenue_ttm]

## Bear Case
- High D/E vs peers [src: fundamentals.debt_to_equity]
- Recent block deal pressure [src: news[2]]

## Confidence
0.55

## Assumptions
- Crude stays in range
- No regulatory surprise

## What Would Change My Mind
- Promoter pledge increase
- ROE drop below 8%
"""
    result = parse_analysis(sample)
    assert "Margin expansion" in result["bull_case"]
    assert "block deal" in result["bear_case"]
    assert result["confidence"] == 0.55
    assert "Crude" in result["assumptions"]
    assert "Promoter pledge" in result["what_would_change"]


def test_analysis_parser_handles_missing_sections():
    from finterminal.agents.analyst import parse_analysis

    result = parse_analysis("## Bull Case\n- one bullet only\n")
    assert "one bullet only" in result["bull_case"]
    assert result["bear_case"] == ""
    assert result["confidence"] is None


def test_analysis_parser_clamps_confidence():
    from finterminal.agents.analyst import parse_analysis

    high = parse_analysis("## Confidence\n1.5\n")
    low = parse_analysis("## Confidence\n-0.2\n")
    assert high["confidence"] == 1.0
    assert low["confidence"] == 0.0


def test_context_block_tags_every_numeric():
    from finterminal.ui.panels import build_context_block

    quote = {
        "ticker": "RELIANCE.NS",
        "last_price": 1234.5,
        "change_pct": 1.2,
        "volume": 5_400_000,
        "market_cap": 1.66e13,
        "as_of": "2026-04-28T10:00:00Z",
        "provider": "yfinance",
    }
    fundamentals = {
        "pe_ttm": 28.5,
        "eps_ttm": 43.2,
        "roe": 0.091,
        "roce": 0.11,
        "debt_to_equity": 0.45,
        "revenue_ttm": 9.0e12,
        "net_income_ttm": 7.5e11,
    }
    news = [{"published_at": None, "source": "Mint", "headline": "Reliance Q4 up 12%"}]
    block = build_context_block("RELIANCE.NS", quote, fundamentals, news)

    assert "[src: quote.last_price]" in block
    assert "[src: fundamentals.pe_ttm]" in block
    assert "[src: news[0]]" in block
    assert "## Quote" in block and "## Fundamentals" in block and "## Recent News" in block
