"""Null provider — for agents like Calendar that don't need an LLM."""

from __future__ import annotations

from ..base import Completion, LLMProvider, Message, ModelMetadata, ToolSpec


class NullProvider(LLMProvider):
    def __init__(self, meta: ModelMetadata):
        self._meta = meta

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
    ) -> Completion:
        return Completion(
            text="",
            tokens_in=0,
            tokens_out=0,
            model=self._meta.name,
            provider="null",
        )
