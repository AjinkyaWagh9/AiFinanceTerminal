"""Ollama provider — talks to the local Ollama daemon over HTTP.

Uses Ollama's native /api/chat endpoint (not the /v1 OpenAI-compat shim) so
we control the request shape directly and don't depend on the openai SDK
for local inference.

Daemon URL resolution:
  1. OLLAMA_BASE_URL env var (e.g. for a remote Ollama server)
  2. http://localhost:11434 (default — Ollama's standard listen address)

No API key is required — Ollama is local-only by default. If you've fronted
your Ollama with auth (Cloudflare Tunnel, Tailscale + nginx, etc.), set
OLLAMA_API_KEY and it will be sent as a Bearer token.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..base import Completion, LLMProvider, Message, ModelMetadata, ProviderError, ToolSpec

_DEFAULT_BASE_URL = "http://localhost:11434"
_REQUEST_TIMEOUT_S = 600.0  # local inference can be slow on first model load


def _resolve_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


class OllamaProvider(LLMProvider):
    def __init__(self, meta: ModelMetadata):
        self._meta = meta
        self._base_url = _resolve_base_url()
        # Optional bearer token for fronted Ollama deployments. Local default = no auth.
        self._auth_token = os.environ.get("OLLAMA_API_KEY")

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
        cache_system: bool = False,  # accepted; Ollama has no remote cache to mark
    ) -> Completion:
        api_messages: list[dict] = [{"role": "system", "content": system}]
        api_messages.extend({"role": m.role, "content": m.content} for m in messages)

        payload: dict[str, Any] = {
            "model": self._meta.api_id,
            "messages": api_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_schema is not None:
            # Ollama supports `format: "json"` for free-form JSON or a JSON schema dict.
            payload["format"] = json_schema

        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        url = f"{self._base_url}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.ConnectError as e:
            raise ProviderError(
                f"Cannot reach Ollama at {self._base_url}. Is the daemon running? "
                f"(Try: `brew services start ollama` or `ollama serve`.) Underlying: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"Ollama timed out after {_REQUEST_TIMEOUT_S}s on model "
                f"{self._meta.api_id!r}. First-call cold-start can be slow; retry."
            ) from e

        if resp.status_code == 404:
            raise ProviderError(
                f"Ollama model {self._meta.api_id!r} not found locally. "
                f"Run `ollama pull {self._meta.api_id}` and retry."
            )
        if resp.status_code >= 400:
            raise ProviderError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError(f"Ollama returned non-JSON response: {resp.text[:300]}") from e

        message = data.get("message") or {}
        text = message.get("content", "")
        tokens_in = data.get("prompt_eval_count", 0)
        tokens_out = data.get("eval_count", 0)

        return Completion(
            text=text,
            tokens_in=int(tokens_in),
            tokens_out=int(tokens_out),
            model=self._meta.api_id,
            provider="ollama",
        )
