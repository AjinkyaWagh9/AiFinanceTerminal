"""Orchestrator for /analyze.

Flow:
  1. Result-cache check (5-min TTL on analyses+critiques rows).
  2. Data agent (deterministic, parallel fetches).
  3. Analyst agent (LLM, system-cached).
  4. Critic agent with retry-then-degrade fallback.
  5. Persist analyses + critiques rows.
  6. ML inline badge — calls predictor.predict on the latest signal for
     the ticker (if any). Errors here are non-fatal: warning logged,
     badge omitted (ml_cells=None). Never breaks the analyze flow.
  7. Return AnalysisResult.

The Critic's failure is non-fatal: a degraded row is written and the result
returned with `degraded=True`. The Analyst's failure IS fatal — there is no
analysis without an Analyst.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import duckdb

from ..data import duckdb_store, openbb_client
from ..llm.base import LLMProvider
from ..llm.router import Router
from ..ml import predictor
from .analyst import AnalystAgent
from .base import AgentContext, AgentRegistry
from .critic import CriticAgent
from .data import DataAgent

logger = logging.getLogger(__name__)

RESULT_CACHE_TTL_S = 300  # 5 min — see spec §6 lever 4


# ---------------------------------------------------------------------------
# ML inline badge helpers (spec §3 + M7)
# ---------------------------------------------------------------------------

def _latest_signal_id(conn: duckdb.DuckDBPyConnection, ticker: str) -> str | None:
    """Return the most recent signal_id for *ticker*, or None if no signals exist."""
    try:
        row = conn.execute(
            "SELECT signal_id FROM signals WHERE ticker = ? ORDER BY ts_emitted DESC LIMIT 1",
            [ticker],
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _render_ml_badge(cells: list[dict]) -> str:
    """Build a terminal-friendly multi-line badge string from PredictionCells.

    One line per horizon. Non-cold-start cells show probabilities + conformal
    set + top SHAP driver. Cold-start cells show the cold_start sentinel.

    Spec §M7 badge format (Rich markup is safe here — callers use Rich console).
    """
    lines: list[str] = []
    for cell in cells:
        h = cell["horizon_days"]
        mv = cell.get("model_version", "cold_start")

        if cell.get("predicted_class") == "cold_start":
            lines.append(
                f"[dim]Model · {h}d  cold_start  (need ≥100 resolved outcomes)[/dim]"
            )
        else:
            p_bull = cell.get("p_bull", 0.0)
            p_base = cell.get("p_base", 0.0)
            p_bear = cell.get("p_bear", 0.0)
            conformal = cell.get("conformal_set", [])
            conf_str = "{" + ",".join(sorted(conformal)) + "}" if conformal else "{}"
            # Short version string: last segment after last underscore
            ver = mv.rsplit("_", 1)[-1] if "_" in mv else mv

            badge_line = (
                f"[dim]Model · {h}d[/dim]  "
                f"[green]base {p_base:.0%}[/green]  ·  "
                f"[cyan]bull {p_bull:.0%}[/cyan]  ·  "
                f"[red]bear {p_bear:.0%}[/red]  ·  "
                f"[dim]conformal {conf_str}  ·  {ver}[/dim]"
            )
            lines.append(badge_line)

            # Top SHAP driver tagline
            shap_top = cell.get("shap_top", [])
            if shap_top:
                feat, val = shap_top[0]
                sign = "+" if val >= 0 else ""
                lines.append(f"  [dim]↳ top driver: {feat} ({sign}{val:.2f})[/dim]")

    return "\n".join(lines)


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
    ml_cells: list[dict] | None = field(default=None)   # PredictionCells (spec §4.5); None = badge skipped
    ml_badge_text: str | None = field(default=None)     # pre-rendered badge string for display


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
        # ml_cells not stored in cache — badge re-generated fresh on cache hit
        # (cold vs. real model may change between TTL windows)
        ml_cells=None,
        ml_badge_text=None,
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

    # 6. ML inline badge — non-fatal; errors produce ml_cells=None
    ml_cells: list[dict] | None = None
    ml_badge_text: str | None = None
    try:
        signal_id = _latest_signal_id(conn, ticker)
        if signal_id is not None:
            ml_cells = predictor.predict(conn, signal_id)
            ml_badge_text = _render_ml_badge(ml_cells)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ML badge skipped for %s: %s", ticker, exc)
        ml_cells = None
        ml_badge_text = None

    return AnalysisResult(
        analysis_id=aid,
        ticker=ticker,
        created_at=datetime.now(),
        analyst_payload=analyst_result.payload,
        critic_payload=critic_payload,
        degraded=degraded,
        critic_error=critic_error,
        ml_cells=ml_cells,
        ml_badge_text=ml_badge_text,
    )
