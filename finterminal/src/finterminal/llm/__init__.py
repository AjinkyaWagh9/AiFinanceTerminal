"""LLM abstraction layer. Agents import from here only.

Typical use:
    from finterminal.llm import build_router, Message
    router = build_router()
    llm = router.for_agent("supervisor")
    completion = await llm.complete(system="...", messages=[Message("user", "...")])
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    BudgetExceeded,
    Completion,
    LLMProvider,
    Message,
    ModelMetadata,
    ProviderError,
    ToolSpec,
)
from .registry import ModelNotFound, ModelRegistry
from .router import AgentNotConfigured, Router

__all__ = [
    "AgentNotConfigured",
    "BudgetExceeded",
    "Completion",
    "LLMProvider",
    "Message",
    "ModelMetadata",
    "ModelNotFound",
    "ModelRegistry",
    "ProviderError",
    "Router",
    "ToolSpec",
    "build_router",
]


def build_router(config_dir: Path | None = None) -> Router:
    """Convenience constructor — finds config/ relative to repo root."""
    if config_dir is None:
        # Walk up from this file to find the repo root (the dir containing config/).
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "config" / "models.yaml").exists():
                config_dir = parent / "config"
                break
        if config_dir is None:
            raise FileNotFoundError(
                "Could not locate config/models.yaml. "
                "Pass config_dir explicitly or run from the repo root."
            )
    registry = ModelRegistry(config_dir / "models.yaml")
    return Router(config_dir / "agents.yaml", registry)
