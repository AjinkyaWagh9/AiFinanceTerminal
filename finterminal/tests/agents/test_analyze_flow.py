"""End-to-end /analyze flow tests with all LLM calls mocked."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from finterminal.agents.analyze_flow import (
    AnalysisError,
    AnalysisResult,
    RESULT_CACHE_TTL_S,
    _build_registry_with_overrides,
    run_analyze,
)
from finterminal.agents.data import DataAgent
from finterminal.data.duckdb_store import get_conn
from finterminal.llm.base import Completion, ProviderError


_BASELINE = Path(__file__).parent / "fixtures" / "analyst_baseline_RELIANCE.json"
_RAW_ANALYST = json.loads(_BASELINE.read_text())["raw_response"]
_RAW_CRITIC = """## Issues
- [HIGH] Bull case "margin expansion" — only [NEWS-1] supports; weak.

## Missing Data
- pledge status

## Confidence Adjustment
0.45  — initial 0.55 too high without pledge data

## Verdict
REVISE
"""


def _quote(t):
    return {
        "ticker": t, "as_of": datetime.now(timezone.utc),
        "last_price": 100.0, "change_pct": 0.0,
        "volume": 1, "market_cap": 1, "provider": "stub",
    }


def _fund(t):
    return {"ticker": t, "as_of": datetime.now(timezone.utc).date(),
            "pe_ttm": 20.0, "eps_ttm": None, "roe": 0.1, "roce": None,
            "debt_to_equity": 0.5, "revenue_ttm": None, "net_income_ttm": None,
            "provider": "stub"}


def _news(t, limit=10):
    return [{"id": "n1", "ticker": t, "source": "Mint",
             "headline": "x", "url": "u", "published_at": "2026-04-26",
             "body": ""}]


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DUCKDB_PATH"] = f"{tmp}/test.duckdb"
        c = get_conn()
        yield c
        c.close()


class _MockProvider:
    def __init__(self, text: str, model: str = "mock"):
        self._text = text
        self._model = model
        self.calls = 0

    async def complete(self, **kwargs):
        self.calls += 1
        return Completion(text=self._text, tokens_in=100, tokens_out=80,
                          model=self._model, provider="mock")


class _ErrProvider:
    async def complete(self, **kwargs):
        raise ProviderError("simulated failure")


def _registry(*, analyst_provider, critic_primary, critic_fallback=None):
    """Build a flow registry with stubbed providers + stub fetchers."""
    data_agent = DataAgent(_quote, _fund, _news)
    return _build_registry_with_overrides(
        data_agent=data_agent,
        analyst_provider=lambda: analyst_provider,
        critic_primary=lambda: critic_primary,
        critic_fallback=(lambda: critic_fallback) if critic_fallback else None,
    )


def test_run_analyze_happy_path(conn):
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST, "gpt-5-mini"),
        critic_primary=_MockProvider(_RAW_CRITIC, "claude-sonnet-4-6"),
    )
    result: AnalysisResult = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))

    assert result.degraded is False
    assert result.analyst_payload["confidence"] == 0.55
    assert result.analyst_payload["conviction"] == "Watch Long"
    assert result.critic_payload is not None
    assert result.critic_payload["verdict"] == "REVISE"
    assert result.analysis_id  # uuid string


def test_run_analyze_persists_critique(conn):
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )
    asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    n = conn.execute("SELECT count(*) FROM critiques").fetchone()[0]
    assert n == 1


def test_run_analyze_critic_failure_with_fallback_succeeds(conn):
    primary = _ErrProvider()
    fallback = _MockProvider(_RAW_CRITIC)
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=primary,
        critic_fallback=fallback,
    )
    result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    assert result.degraded is False
    assert result.critic_payload["verdict"] == "REVISE"
    assert fallback.calls == 1


def test_run_analyze_critic_total_failure_degrades(conn):
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_ErrProvider(),
        critic_fallback=_ErrProvider(),
    )
    result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    assert result.degraded is True
    assert result.critic_payload is None
    assert "simulated failure" in (result.critic_error or "")
    # Analyst-side data still complete:
    assert result.analyst_payload["bull_case"]
    # Degraded row written:
    row = conn.execute(
        "SELECT degraded, error FROM critiques WHERE analysis_id = ?",
        [result.analysis_id],
    ).fetchone()
    assert row[0] is True
    assert "simulated failure" in row[1]


def test_run_analyze_analyst_failure_raises(conn):
    reg = _registry(
        analyst_provider=_ErrProvider(),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )
    with pytest.raises(AnalysisError):
        asyncio.run(run_analyze("X.NS", conn, reg))


def test_run_analyze_result_cache_hit_skips_llm(conn):
    primary = _MockProvider(_RAW_ANALYST)
    crit = _MockProvider(_RAW_CRITIC)
    reg = _registry(analyst_provider=primary, critic_primary=crit)

    asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    primary_calls_after_first = primary.calls
    crit_calls_after_first = crit.calls

    # Second call within TTL — should not invoke either provider:
    result2 = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    assert primary.calls == primary_calls_after_first
    assert crit.calls == crit_calls_after_first
    assert result2.analyst_payload["conviction"] == "Watch Long"


def test_run_analyze_fresh_flag_bypasses_cache(conn):
    primary = _MockProvider(_RAW_ANALYST)
    crit = _MockProvider(_RAW_CRITIC)
    reg = _registry(analyst_provider=primary, critic_primary=crit)
    asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    asyncio.run(run_analyze("RELIANCE.NS", conn, reg, fresh=True))
    assert primary.calls == 2
    assert crit.calls == 2


def test_run_analyze_non_regression_analyst_fields_match_baseline(conn):
    """The crown-jewel test: post-refactor flow's Analyst output equals the captured snapshot."""
    expected = json.loads(_BASELINE.read_text())["parsed"]
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )
    result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))

    actual = {k: result.analyst_payload[k] for k in expected.keys()}
    assert actual == expected


def test_result_cache_ttl_constant_is_300():
    assert RESULT_CACHE_TTL_S == 300


def test_run_analyze_default_registry_path_resolves_build_router(conn, monkeypatch):
    """Regression: the registry=None branch late-imports build_router. The
    symbol must live at finterminal.llm.build_router (the package), not on
    finterminal.llm.router (the submodule). Caught a real REPL crash.
    """
    import finterminal.agents.analyze_flow as flow_mod
    import finterminal.llm as llm_pkg

    sentinel_router = object()
    monkeypatch.setattr(llm_pkg, "build_router", lambda: sentinel_router)

    captured = {}

    def _fake_default_registry(router):
        captured["router"] = router
        return _registry(
            analyst_provider=_MockProvider(_RAW_ANALYST),
            critic_primary=_MockProvider(_RAW_CRITIC),
        )

    monkeypatch.setattr(flow_mod, "_build_default_registry", _fake_default_registry)

    result = asyncio.run(run_analyze("RELIANCE.NS", conn, fresh=True))
    assert captured["router"] is sentinel_router
    assert result.analyst_payload["confidence"] == 0.55
