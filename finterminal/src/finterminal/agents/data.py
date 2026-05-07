"""Data agent — deterministic Python, no LLM.

Parallelizes the three Phase-1 fetches via asyncio.to_thread, persists to
DuckDB, and emits both:
  - context_block (full, for Analyst — same shape as today)
  - source_dossier (slim, for Critic — see agents._dossier)

Fetchers are injected via the constructor so tests can stub them. Production
construction (in analyze_flow._build_default_registry) wires the real
openbb_client functions.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from ..data import duckdb_store
from ..ui.panels import build_context_block
from . import _dossier
from .base import AgentContext, AgentResult

logger = logging.getLogger(__name__)


class DataAgent:
    """name='data', is_llm=False. Returns AgentResult with payload dict containing
    {quote, fundamentals, news, context_block, source_dossier}."""

    name = "data"
    is_llm = False

    def __init__(
        self,
        fetch_quote: Callable[[str], dict],
        fetch_fundamentals: Callable[[str], dict],
        fetch_news: Callable[..., list[dict]],
    ) -> None:
        self._fetch_quote = fetch_quote
        self._fetch_fundamentals = fetch_fundamentals
        self._fetch_news = fetch_news

    async def run(self, ctx: AgentContext) -> AgentResult:
        ticker = ctx.ticker

        # Fan out fetches in parallel. quote is required; fund + news are best-effort.
        quote_t = asyncio.create_task(asyncio.to_thread(self._fetch_quote, ticker))
        fund_t = asyncio.create_task(asyncio.to_thread(self._fetch_fundamentals, ticker))
        news_t = asyncio.create_task(asyncio.to_thread(self._fetch_news, ticker, 10))

        # Wait on all three; we tolerate fund/news exceptions.
        results = await asyncio.gather(quote_t, fund_t, news_t, return_exceptions=True)
        quote_or_exc, fund_or_exc, news_or_exc = results

        # Quote is required.
        if isinstance(quote_or_exc, Exception):
            return AgentResult(ok=False, error=f"quote fetch failed: {quote_or_exc!s}")
        quote: dict = quote_or_exc  # type: ignore[assignment]

        fundamentals: dict | None
        if isinstance(fund_or_exc, Exception):
            logger.warning("fundamentals unavailable for %s: %s", ticker, fund_or_exc)
            fundamentals = None
        else:
            fundamentals = fund_or_exc  # type: ignore[assignment]

        news: list[dict]
        if isinstance(news_or_exc, Exception):
            logger.warning("news unavailable for %s: %s", ticker, news_or_exc)
            news = []
        else:
            news = news_or_exc  # type: ignore[assignment]

        # Persist (sync — duckdb is thread-safe for this connection pattern).
        try:
            duckdb_store.upsert_quote(ctx.conn, quote)
            if fundamentals:
                duckdb_store.upsert_fundamentals(ctx.conn, fundamentals)
            if news:
                duckdb_store.upsert_news(ctx.conn, news)
        except Exception as exc:  # noqa: BLE001 — surface as agent-level error
            return AgentResult(ok=False, error=f"persistence failed: {exc!s}")

        context_block = build_context_block(ticker, quote, fundamentals, news)
        source_dossier = _dossier.build_source_dossier(ticker, quote, fundamentals, news)

        payload = {
            "quote": quote,
            "fundamentals": fundamentals,
            "news": news,
            "context_block": context_block,
            "source_dossier": source_dossier,
        }
        return AgentResult(ok=True, payload=payload)
