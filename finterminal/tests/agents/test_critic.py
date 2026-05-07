"""Critic parser + agent. LLM call is mocked; we only test parsing + agent surface."""
from __future__ import annotations

import asyncio

from finterminal.agents.base import AgentContext
from finterminal.agents.critic import CriticAgent, parse_critique
from finterminal.llm.base import Completion


_WELL_FORMED = """## Issues
- [HIGH] PE claim 23.4 unsourced; [FUND-PE] missing
- [MEDIUM] Bear case ignores GST collection slowdown

## Missing Data
- pledge status
- FII flow last 30d

## Confidence Adjustment
0.55  — initial 0.72 is too high given missing pledge data

## Verdict
REVISE
"""


def test_parse_critique_well_formed():
    out = parse_critique(_WELL_FORMED)
    assert out["verdict"] == "REVISE"
    assert "[HIGH]" in out["issues_md"]
    assert "pledge status" in out["missing_md"]
    assert out["confidence_adj"] == 0.55


def test_parse_critique_handles_accept():
    out = parse_critique("## Verdict\nACCEPT\n")
    assert out["verdict"] == "ACCEPT"
    assert out["issues_md"] == ""
    assert out["confidence_adj"] is None


def test_parse_critique_handles_reject():
    out = parse_critique("## Verdict\nREJECT\n")
    assert out["verdict"] == "REJECT"


def test_parse_critique_unparseable_returns_none_verdict():
    out = parse_critique("the model returned prose without sections")
    assert out["verdict"] is None
    assert out["raw_text"] == "the model returned prose without sections"


def test_parse_critique_clamps_confidence():
    out = parse_critique("## Confidence Adjustment\n1.5\n## Verdict\nACCEPT\n")
    assert out["confidence_adj"] == 1.0
    out = parse_critique("## Confidence Adjustment\n-0.2\n## Verdict\nACCEPT\n")
    assert out["confidence_adj"] == 0.0


# ---------- agent surface ----------


class _StubProvider:
    def __init__(self, completion: Completion):
        self._c = completion
        self.last_kwargs: dict | None = None

    async def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self._c


def _ok_completion(text: str = _WELL_FORMED) -> Completion:
    return Completion(text=text, tokens_in=1200, tokens_out=350,
                      model="claude-sonnet-4-6", provider="anthropic")


def test_critic_agent_happy_path():
    provider = _StubProvider(_ok_completion())
    agent = CriticAgent(get_provider=lambda: provider)

    ctx = AgentContext(
        ticker="RELIANCE.NS", conn=None,  # type: ignore[arg-type]
        prior={
            "analyst": {"bull_case": "...", "bear_case": "...", "variant_perception": "...",
                        "confidence": 0.72, "conviction": "Watch Long"},
            "data": {"source_dossier": "[QUOTE] ..."},
        },
    )
    result = asyncio.run(agent.run(ctx))

    assert result.ok is True
    assert result.payload["verdict"] == "REVISE"
    assert result.payload["confidence_adj"] == 0.55
    assert result.tokens_in == 1200
    assert result.tokens_out == 350
    assert result.model == "claude-sonnet-4-6"
    assert provider.last_kwargs is not None
    assert provider.last_kwargs["max_tokens"] == 500
    assert provider.last_kwargs["cache_system"] is True


def test_critic_agent_provider_error_returns_not_ok():
    from finterminal.llm.base import ProviderError

    class _ErrProvider:
        async def complete(self, **kwargs):
            raise ProviderError("rate limited")

    agent = CriticAgent(get_provider=lambda: _ErrProvider())
    ctx = AgentContext(
        ticker="X.NS", conn=None,  # type: ignore[arg-type]
        prior={"analyst": {}, "data": {"source_dossier": ""}},
    )
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "rate limited" in (result.error or "")


def test_critic_agent_unparseable_output_returns_not_ok():
    """Malformed LLM text → ok=False so the orchestrator can degrade gracefully."""
    provider = _StubProvider(_ok_completion("just some prose, no sections"))
    agent = CriticAgent(get_provider=lambda: provider)
    ctx = AgentContext(
        ticker="X.NS", conn=None,  # type: ignore[arg-type]
        prior={"analyst": {}, "data": {"source_dossier": ""}},
    )
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "parse" in (result.error or "").lower()


def test_critic_agent_metadata():
    agent = CriticAgent(get_provider=lambda: _StubProvider(_ok_completion()))
    assert agent.name == "critic"
    assert agent.is_llm is True
