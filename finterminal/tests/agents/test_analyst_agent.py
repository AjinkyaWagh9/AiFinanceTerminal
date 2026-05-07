"""Analyst agent surface tests."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path


from finterminal.agents.analyst import AnalystAgent, parse_analysis
from finterminal.agents.base import AgentContext
from finterminal.llm.base import Completion


_BASELINE = Path(__file__).parent / "fixtures" / "analyst_baseline_RELIANCE.json"


def test_parse_analysis_against_baseline():
    """The new parser MUST produce the same output as the captured baseline."""
    data = json.loads(_BASELINE.read_text())
    parsed_now = parse_analysis(data["raw_response"])
    expected = data["parsed"]
    assert parsed_now == expected, (
        "parse_analysis output drifted from baseline. "
        "If this is intended, regenerate via "
        "`uv run python tests/agents/fixtures/baseline_capture.py`."
    )


class _StubProvider:
    def __init__(self, completion: Completion):
        self._c = completion
        self.last_kwargs: dict | None = None

    async def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self._c


def test_analyst_agent_happy_path():
    raw = json.loads(_BASELINE.read_text())["raw_response"]
    completion = Completion(
        text=raw, tokens_in=2200, tokens_out=1800,
        model="gpt-5-mini", provider="openai",
    )
    provider = _StubProvider(completion)
    agent = AnalystAgent(get_provider=lambda: provider)

    ctx = AgentContext(
        ticker="RELIANCE.NS", conn=None,  # type: ignore[arg-type]
        prior={"data": {"context_block": "# RELIANCE.NS\n## Quote ..."}},
    )
    result = asyncio.run(agent.run(ctx))

    assert result.ok is True
    assert result.payload["bull_case"]
    assert result.payload["bear_case"]
    assert result.payload["confidence"] == 0.55
    assert result.payload["conviction"] == "Watch Long"
    assert result.tokens_in == 2200
    assert result.tokens_out == 1800
    assert result.model == "gpt-5-mini"
    assert provider.last_kwargs["cache_system"] is True
    assert provider.last_kwargs["max_tokens"] == 2000


def test_analyst_agent_provider_error_returns_not_ok():
    from finterminal.llm.base import ProviderError

    class _Err:
        async def complete(self, **kwargs):
            raise ProviderError("boom")

    agent = AnalystAgent(get_provider=lambda: _Err())
    ctx = AgentContext(
        ticker="X.NS", conn=None,  # type: ignore[arg-type]
        prior={"data": {"context_block": ""}},
    )
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "boom" in (result.error or "")


def test_analyst_agent_metadata():
    agent = AnalystAgent(get_provider=lambda: _StubProvider(
        Completion(text="", tokens_in=0, tokens_out=0, model="m", provider="p")))
    assert agent.name == "analyst"
    assert agent.is_llm is True
