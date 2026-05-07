"""Core types for the LLM abstraction. Every provider implements LLMProvider.

Agents only see this module — they never import a concrete provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    provider: str
    latency_ms: int = 0
    cache_hit: bool = False
    raw: dict | None = None


@dataclass(frozen=True)
class ModelMetadata:
    name: str
    provider: str
    api_id: str
    context_window: int
    cost_per_mtok_in: float
    cost_per_mtok_out: float
    capabilities: frozenset[str] = field(default_factory=frozenset)
    tags: frozenset[str] = field(default_factory=frozenset)
    # Optional fields for OpenAI-compatible providers (OpenAI, xAI, OpenRouter, Together, Groq, NVIDIA NIM).
    # Anthropic provider ignores these.
    api_key_env: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None  # env var name; takes precedence over base_url if both set


@runtime_checkable
class LLMProvider(Protocol):
    """All concrete providers (Anthropic, Ollama, xAI, OpenAI-compat) implement this."""

    @property
    def metadata(self) -> ModelMetadata: ...

    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
        cache_system: bool = False,
    ) -> Completion: ...


class ProviderError(Exception):
    """Raised when a provider call fails after retries."""


class BudgetExceeded(Exception):
    """Raised by BudgetGuard when a per-agent or global cap is hit."""
