"""Agent protocol + per-call context + uniform result type + a small registry.

Every agent (deterministic or LLM-backed) implements this Protocol. The
orchestrator (`agents/analyze_flow.py`) composes them. Future agents
(Phase 2.5: ownership, transcript, quality, comps, macro, ...) drop in
as one file each + one registry entry.

This module has zero LLM dependencies — providers are reached via
`finterminal.llm.router.Router.for_agent(name)` from inside concrete agents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import duckdb


@dataclass
class AgentContext:
    """Per-call payload threaded through agents.

    `prior` accumulates outputs from earlier-running agents in the flow,
    keyed by agent.name (e.g. {"data": <DataPayload>, "analyst": <AnalystPayload>}).
    """
    ticker: str
    conn: duckdb.DuckDBPyConnection
    prior: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Uniform return shape across agents.

    ok=False means the agent's job failed cleanly — the orchestrator decides
    whether to degrade or raise based on the agent's role.
    """
    ok: bool
    payload: Any = None
    error: str | None = None
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0


@runtime_checkable
class Agent(Protocol):
    """Agents implement this; orchestrator depends only on this surface."""
    name: str
    is_llm: bool

    async def run(self, ctx: AgentContext) -> AgentResult: ...


class AgentRegistry:
    """Tiny in-memory registry keyed by Agent.name.

    Built lazily by each flow (e.g. `analyze_flow._build_default_registry()`).
    Not a global — when 4b News flow lands, it will build its own registry the
    same way, sharing nothing.
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.name in self._agents:
            raise ValueError(f"agent already registered: {agent.name}")
        self._agents[agent.name] = agent

    def get(self, name: str) -> Agent:
        if name not in self._agents:
            raise KeyError(f"agent not registered: {name}")
        return self._agents[name]
