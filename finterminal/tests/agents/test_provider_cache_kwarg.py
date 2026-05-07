"""All 3 providers must accept the `cache_system` kwarg (Anthropic uses it; others ignore)."""
from __future__ import annotations

import inspect

from finterminal.llm.base import LLMProvider
from finterminal.llm.providers.anthropic import AnthropicProvider
from finterminal.llm.providers.ollama import OllamaProvider
from finterminal.llm.providers.openai_compat import OpenAICompatProvider


def test_protocol_complete_accepts_cache_system():
    sig = inspect.signature(LLMProvider.complete)
    assert "cache_system" in sig.parameters
    p = sig.parameters["cache_system"]
    assert p.default is False


def test_anthropic_provider_complete_accepts_cache_system():
    sig = inspect.signature(AnthropicProvider.complete)
    assert "cache_system" in sig.parameters
    assert sig.parameters["cache_system"].default is False


def test_openai_compat_provider_complete_accepts_cache_system():
    sig = inspect.signature(OpenAICompatProvider.complete)
    assert "cache_system" in sig.parameters
    assert sig.parameters["cache_system"].default is False


def test_ollama_provider_complete_accepts_cache_system():
    sig = inspect.signature(OllamaProvider.complete)
    assert "cache_system" in sig.parameters
    assert sig.parameters["cache_system"].default is False
