# ADR-010 — Generic OpenAI-Compatible Provider Class

> Back to [[Index]] | See also [[02 - Decisions/ADR-006 Model Abstraction in Phase 1]] · [[01 - Architecture/LLM Abstraction Layer]] · [[2026-04-28 - OpenAI Provider Added]]

**Status:** Accepted
**Date:** 2026-04-28
**Deciders:** Ajinkya Wagh

---

## Context

Phase 1 shipped with `AnthropicProvider` only. Adding OpenAI models (and routing Grok through xAI's OpenAI-compatible endpoint) requires at least one new provider class. The OpenAI Python SDK supports any base URL that speaks the OpenAI chat-completions API, making it a natural shared transport for `openai.com`, `api.x.ai`, and future OpenRouter / local-LLM endpoints.

Options considered:
1. One class per vendor (`OpenAIProvider`, `XAIProvider`, `OpenRouterProvider`, …)
2. One shared class (`OpenAICompatProvider`) registered under multiple keys

---

## Decision

**One class (`OpenAICompatProvider`), registered under multiple PROVIDERS dict keys.**

```
PROVIDERS = {
    "openai_compat": OpenAICompatProvider,
    "openai":        OpenAICompatProvider,   # alias
    "xai":           OpenAICompatProvider,   # alias — Grok endpoint
}
```

Per-model config in `models.yaml` carries everything the class needs:

```yaml
api_key_env:  XAI_API_KEY          # env var to read the key from
base_url:     https://api.x.ai/v1  # static base URL
base_url_env: XAI_BASE_URL         # optional override via env var
```

Resolution order inside `__init__`:
1. `api_key` ← `os.getenv(meta.api_key_env)` — defaults to `OPENAI_API_KEY` if field absent
2. `base_url` ← `os.getenv(meta.base_url_env)` if set, else `meta.base_url`, else `https://api.openai.com/v1`

---

## Rationale

| Factor | Why shared class wins |
|---|---|
| Shared retry logic | `RateLimitError` / `APIError` retries written once; all aliases benefit |
| Shared cost logging | Token counting + `budget.py` lookup runs through one code path |
| Shared streaming / JSON-mode | No duplication when these are added in Phase 2 |
| YAML readability | `provider: xai` in agents.yaml is self-documenting without a real `XAIProvider` class |
| Maintenance surface | One file to patch when the OpenAI SDK releases breaking changes |

---

## Consequences / Trade-offs

| Pro | Con |
|---|---|
| Fix bugs once; all providers benefit | Provider-specific quirks (xAI Live Search headers; OpenAI Structured Outputs; OpenRouter routing) need divergence eventually |
| New OpenAI-compat endpoint = one YAML entry, zero new code | Alias approach means `provider:` field in YAML must be one of the three registered keys — not freeform |
| Trivially swap supervisor model in one line | If two aliases need genuinely different retry policies, shared class becomes awkward |

**Mitigation for divergence:** subclass `OpenAICompatProvider` when a vendor-specific code path is real and unavoidable. Don't pre-design the subclass hierarchy.

---

## Affected files

- `src/finterminal/llm/providers/openai_compat.py` — new class
- `src/finterminal/llm/providers/__init__.py` — three-alias registration
- `src/finterminal/llm/base.py` — `ModelMetadata` new optional fields
- `src/finterminal/llm/registry.py` — field threading
- `config/models.yaml` — OpenAI models + Grok `provider: xai`

---

## Revisit trigger

When a provider alias requires a feature that cannot be conditionally toggled via `meta.*` fields (e.g., xAI Live Search tool, OpenAI Structured Outputs schema injection) — at that point, subclass rather than adding more conditionals to `OpenAICompatProvider`.
