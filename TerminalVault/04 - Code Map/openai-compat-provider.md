# Code Map — openai-compat-provider

> Back to [[Index]] | See also [[04 - Code Map/llm — abstraction layer]] · [[ADR-010 Generic OpenAI-Compat Provider Class]]

**Maps to:** `finterminal/src/finterminal/llm/providers/openai_compat.py`

---

## Purpose

Single provider class that speaks the OpenAI chat-completions API. Registered under three aliases so `openai`, `xai`, and `openai_compat` all dispatch here without separate classes.

---

## Registered aliases

| Key in `PROVIDERS` | Used by |
|---|---|
| `openai_compat` | Explicit / future OpenRouter entries |
| `openai` | OpenAI-native models (`gpt-5`, `gpt-5-mini`, `gpt-5-nano`) |
| `xai` | Grok models via `api.x.ai/v1` |

Registered in: `src/finterminal/llm/providers/__init__.py`

---

## Resolution rules

**API key** (resolved in `__init__`):
- Read `os.getenv(meta.api_key_env)` — defaults to `OPENAI_API_KEY` if `api_key_env` is absent on the model entry.

**Base URL** (resolved in `__init__`):
1. `os.getenv(meta.base_url_env)` — runtime override via env var
2. `meta.base_url` — static value from `models.yaml`
3. `https://api.openai.com/v1` — hardcoded fallback

---

## `__init__` shape

- File: `openai_compat.py` (top of class)
- Accepts `meta: ModelMetadata` (see `src/finterminal/llm/base.py`)
- Constructs `openai.AsyncOpenAI(api_key=..., base_url=...)`
- Stores resolved client + model name on `self`

New `ModelMetadata` fields that feed this class:
- `api_key_env: str | None`
- `base_url: str | None`
- `base_url_env: str | None`

---

## `complete()` shape

- Signature mirrors the `LLMProvider` protocol: `async def complete(messages, **kwargs) -> str`
- Calls `self._client.chat.completions.create(model=..., messages=..., **kwargs)`
- Returns the first choice message content as a string
- Retries on `openai.RateLimitError` and `openai.APIError` (backoff logic in the method body)

---

## Retry behavior

- Catches `RateLimitError` and `APIError` from the `openai` SDK
- Uses exponential backoff (implementation detail — see file for exact retry count/delay)
- Exhausted retries propagate the original exception to the caller (`commands.py` → `dispatch` error boundary)

---

## Related config

- `config/models.yaml` — model entries with `provider: openai` / `provider: xai`
- `config/agents.yaml` — swap a model in one line (`model: gpt-5-mini`)
- `src/finterminal/llm/budget.py` — `_FALLBACK_COSTS` entries for gpt-5-nano, gpt-5-mini, gpt-5
- `pyproject.toml` — `openai>=1.60.0`
