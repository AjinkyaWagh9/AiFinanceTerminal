"""Router — agents.yaml is the only place that maps role → model.

Agents call `router.for_agent("critic")` and get an LLMProvider handle.
They never know which concrete model is behind it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .base import LLMProvider
from .registry import ModelNotFound, ModelRegistry


class AgentNotConfigured(Exception):
    pass


class Router:
    def __init__(self, agents_yaml: Path, registry: ModelRegistry):
        self._registry = registry
        self._agents: dict[str, dict] = {}
        self._load(agents_yaml)

    def _load(self, path: Path) -> None:
        data = yaml.safe_load(path.read_text())
        self._agents = data.get("agents", {})

    def for_agent(self, name: str) -> LLMProvider:
        cfg = self._agents.get(name)
        if cfg is None:
            raise AgentNotConfigured(f"Agent {name!r} not in agents.yaml")
        if cfg.get("enabled") is False:
            raise AgentNotConfigured(f"Agent {name!r} is disabled in agents.yaml")
        primary = cfg.get("primary")
        if primary is None:
            raise AgentNotConfigured(f"Agent {name!r} has no primary model")
        return self._registry.get(primary)

    def fallback_chain(self, name: str) -> list[LLMProvider]:
        """Returns [primary, *fallbacks]. Caller iterates on ProviderError."""
        cfg = self._agents.get(name)
        if cfg is None:
            raise AgentNotConfigured(f"Agent {name!r} not in agents.yaml")
        chain = []
        for model_name in [cfg["primary"], *cfg.get("fallbacks", [])]:
            try:
                chain.append(self._registry.get(model_name))
            except ModelNotFound:
                continue
        return chain

    def is_enabled(self, name: str) -> bool:
        cfg = self._agents.get(name)
        if cfg is None:
            return False
        return cfg.get("enabled", True)
