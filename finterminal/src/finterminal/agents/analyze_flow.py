"""Orchestrator for /analyze.

Flow:
  1. Result-cache check (5-min TTL on analyses+critiques rows).
  2. Data agent (deterministic, parallel fetches).
  3. Analyst agent (LLM, system-cached).
  4. Critic agent with retry-then-degrade fallback.
  5. Persist analyses + critiques rows.
  6. Return AnalysisResult.

The Critic's failure is non-fatal: a degraded row is written and the result
returned with `degraded=True`. The Analyst's failure IS fatal — there is no
analysis without an Analyst.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import duckdb

from ..data import duckdb_store, openbb_client
from ..llm.base import LLMProvider
from ..llm.router import Router
from .analyst import AnalystAgent
from .base import AgentContext, AgentRegistry
from .critic import CriticAgent
from .data import DataAgent

RESULT_CACHE_TTL_S = 300  # 5 min — see spec §6 lever 4


class AnalysisError(Exception):
    """Raised when /analyze cannot produce any usable output (Analyst failure or data failure)."""


@dataclass
class AnalysisResult:
    analysis_id: str
    ticker: str
    created_at: datetime
    analyst_payload: dict          # parsed Analyst output (7 sections + ticker)
    critic_payload: dict | None    # Critic parsed output OR None when degraded
    degraded: bool                 # True when Critic failed
    critic_error: str | None       # populated when degraded


def _build_default_registry(router: Router) -> AgentRegistry:
    """Production registry. Wires real fetchers + router-resolved providers."""
    reg = AgentRegistry()
    reg.register(DataAgent(
        fetch_quote=openbb_client.fetch_quote,
        fetch_fundamentals=openbb_client.fetch_fundamentals,
        fetch_news=openbb_client.fetch_news,
    ))
    reg.register(AnalystAgent(get_provider=lambda: router.for_agent("analyst")))
    reg.register(CriticAgent(get_provider=lambda: router.for_agent("critic")))
    reg._critic_fallback = _critic_fallback_factory(router)  # type: ignore[attr-defined]
    return reg


def _critic_fallback_factory(router: Router) -> Callable[[], LLMProvider] | None:
    """Returns a callable that builds the Critic's first fallback provider, or None."""
    chain = router.fallback_chain("critic")
    if len(chain) < 2:
        return None
    fallback_provider = chain[1]
    return lambda: fallback_provider


def _build_registry_with_overrides(
    *,
    data_agent: DataAgent,
    analyst_provider: Callable[[], LLMProvider],
    critic_primary: Callable[[], LLMProvider],
    critic_fallback: Callable[[], LLMProvider] | None = None,
) -> AgentRegistry:
    """Test-only registry builder. Used by unit tests to inject mocks."""
    reg = AgentRegistry()
    reg.register(data_agent)
    reg.register(AnalystAgent(get_provider=analyst_provider))
    reg.register(CriticAgent(get_provider=critic_primary))
    if critic_fallback is not None:
        reg._critic_fallback = critic_fallback  # type: ignore[attr-defined]
    return reg


async def _run_critic_with_fallback(
    reg: AgentRegistry,
    ctx: AgentContext,
):
    """Run primary critic; on ok=False, retry once on the fallback provider.
    Returns the AgentResult (ok=True or ok=False — caller handles degrade)."""
    critic = reg.get("critic")
    result = await critic.run(ctx)
    if result.ok:
        return result

    fallback_factory = getattr(reg, "_critic_fallback", None)
    if fallback_factory is None:
        return result

    fallback_critic = CriticAgent(get_provider=fallback_factory)
    return await fallback_critic.run(ctx)


def _rehydrate_cached(cached: dict) -> AnalysisResult:
    return AnalysisResult(
        analysis_id=cached["analysis_id"],
        ticker=cached["ticker"],
        created_at=cached["created_at"],
        analyst_payload=cached["analyst_payload"],
        critic_payload=cached["critic_payload"],
        degraded=cached["degraded"],
        critic_error=cached["critic_error"],
    )


async def run_analyze(
    ticker: str,
    conn: duckdb.DuckDBPyConnection,
    registry: AgentRegistry | None = None,
    *,
    fresh: bool = False,
) -> AnalysisResult:
    """Top-level /analyze entry point.

    Raises AnalysisError if Data or Analyst fails. Critic failures degrade
    silently into the result (degraded=True, critic_payload=None).
    """
    if not fresh:
        cached = duckdb_store.recent_analysis(conn, ticker, ttl_s=RESULT_CACHE_TTL_S)
        if cached is not None:
            return _rehydrate_cached(cached)

    if registry is None:
        from ..llm import build_router as _build_router  # late import; avoids cycle
        router = _build_router()
        registry = _build_default_registry(router)

    ctx = AgentContext(ticker=ticker, conn=conn)

    # 1. Data
    data_result = await registry.get("data").run(ctx)
    if not data_result.ok:
        raise AnalysisError(f"data fetch failed: {data_result.error}")
    ctx.prior["data"] = data_result.payload

    # 2. Analyst
    analyst_result = await registry.get("analyst").run(ctx)
    if not analyst_result.ok:
        raise AnalysisError(f"analyst failed: {analyst_result.error}")
    ctx.prior["analyst"] = analyst_result.payload

    # 3. Critic (with retry-then-degrade)
    critic_result = await _run_critic_with_fallback(registry, ctx)

    degraded = not critic_result.ok
    critic_payload = critic_result.payload if critic_result.ok else None
    critic_error = critic_result.error if not critic_result.ok else None

    # 4. Persist analyses row
    sources = {
        "model": analyst_result.model,
        "tokens_in": analyst_result.tokens_in,
        "tokens_out": analyst_result.tokens_out,
        "data_quote_provider": (data_result.payload.get("quote") or {}).get("provider"),
    }
    aid = duckdb_store.record_analysis(
        conn,
        ticker=ticker,
        bull_case=analyst_result.payload.get("bull_case", ""),
        bear_case=analyst_result.payload.get("bear_case", ""),
        confidence=(analyst_result.payload.get("confidence") or 0.0),
        sources=sources,
        payload=analyst_result.payload,
    )

    # 5. Persist critique row
    cp = critic_payload or {}
    duckdb_store.record_critique(
        conn,
        analysis_id=aid,
        verdict=cp.get("verdict"),
        issues_md=cp.get("issues_md", ""),
        missing_md=cp.get("missing_md", ""),
        confidence_adj=cp.get("confidence_adj"),
        raw_text=cp.get("raw_text", "") if not degraded else "",
        model=critic_result.model,
        tokens_in=critic_result.tokens_in,
        tokens_out=critic_result.tokens_out,
        degraded=degraded,
        error=critic_error,
    )

    return AnalysisResult(
        analysis_id=aid,
        ticker=ticker,
        created_at=datetime.now(),
        analyst_payload=analyst_result.payload,
        critic_payload=critic_payload,
        degraded=degraded,
        critic_error=critic_error,
    )
