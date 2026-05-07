"""Unit tests for the Agent protocol + AgentRegistry."""
from __future__ import annotations

import pytest

from finterminal.agents.base import (
    Agent,
    AgentContext,
    AgentRegistry,
    AgentResult,
)


class _FakeAgent:
    """A minimal protocol-compliant agent used only in tests."""

    name = "fake"
    is_llm = False

    async def run(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(ok=True, payload={"got": ctx.ticker})


def test_agent_result_defaults():
    r = AgentResult(ok=True)
    assert r.ok is True
    assert r.payload is None
    assert r.error is None
    assert r.tokens_in == 0
    assert r.tokens_out == 0
    assert r.model is None


def test_agent_context_defaults():
    ctx = AgentContext(ticker="RELIANCE.NS", conn=None)  # type: ignore[arg-type]
    assert ctx.ticker == "RELIANCE.NS"
    assert ctx.prior == {}


def test_registry_register_and_get():
    reg = AgentRegistry()
    a = _FakeAgent()
    reg.register(a)
    assert reg.get("fake") is a


def test_registry_rejects_duplicates():
    reg = AgentRegistry()
    reg.register(_FakeAgent())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_FakeAgent())


def test_registry_unknown_name_raises_keyerror():
    reg = AgentRegistry()
    with pytest.raises(KeyError, match="not registered"):
        reg.get("nope")


def test_protocol_runtime_check_accepts_fake():
    """The Agent protocol is runtime_checkable so we can isinstance-test fakes in other tests."""
    a = _FakeAgent()
    assert isinstance(a, Agent)
