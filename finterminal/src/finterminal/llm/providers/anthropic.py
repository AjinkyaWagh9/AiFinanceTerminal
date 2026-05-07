"""Anthropic provider — wraps the Claude SDK with retry + cost recording."""

from __future__ import annotations

import asyncio
import os
import time

from anthropic import APIError, AsyncAnthropic, RateLimitError

from ..base import Completion, LLMProvider, Message, ModelMetadata, ProviderError, ToolSpec


class AnthropicProvider(LLMProvider):
    def __init__(self, meta: ModelMetadata):
        self._meta = meta
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderError(
                "ANTHROPIC_API_KEY is not set. Add it to .env before using Claude-backed agents."
            )
        self._client = AsyncAnthropic(api_key=api_key)

    @property
    def metadata(self) -> ModelMetadata:
        return self._meta

    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
        cache_system: bool = False,
    ) -> Completion:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        # Anthropic prompt caching: mark the system block as ephemeral (5min TTL).
        # https://docs.anthropic.com/claude/docs/prompt-caching
        if cache_system:
            system_param: str | list[dict] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        else:
            system_param = system

        last_err: Exception | None = None
        for attempt in range(3):
            t0 = time.monotonic()
            try:
                resp = await self._client.messages.create(
                    model=self._meta.api_id,
                    system=system_param,
                    messages=api_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                latency_ms = int((time.monotonic() - t0) * 1000)
                text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
                return Completion(
                    text="".join(text_parts),
                    tokens_in=resp.usage.input_tokens,
                    tokens_out=resp.usage.output_tokens,
                    model=self._meta.name,
                    provider="anthropic",
                    latency_ms=latency_ms,
                )
            except RateLimitError as exc:
                last_err = exc
                await asyncio.sleep(2 ** attempt)
            except APIError as exc:
                last_err = exc
                if attempt == 2:
                    break
                await asyncio.sleep(2 ** attempt)

        raise ProviderError(f"Anthropic call failed after retries: {last_err!r}")
