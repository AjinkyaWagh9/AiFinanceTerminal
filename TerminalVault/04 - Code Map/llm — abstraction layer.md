# Code Map — llm/ abstraction layer

> Back to [[Index]] | See also [[01 - Architecture/LLM Abstraction Layer]] · [[04 - Code Map/openai-compat-provider]] · [[ADR-006 Model Abstraction in Phase 1]]

**Directory:** `src/finterminal/llm/`

---

## File inventory

| File | Key exports | Role |
|---|---|---|
| `base.py` | `LLMProvider`, `Message`, `Completion`, `ModelMetadata`, `ToolSpec` | Protocol + dataclasses; the only thing agents import |
| `registry.py` | `ModelRegistry`, `build_registry()` | Loads `config/models.yaml`; instantiates provider objects |
| `router.py` | `Router`, `build_router()` | Loads `config/agents.yaml`; exposes `for_agent(name)` |
| `budget.py` | `CostTracker`, `record()` | Writes to DuckDB `llm_calls` table on every call |
| `providers/anthropic.py` | `AnthropicProvider` | Wraps Anthropic SDK; handles retry, cost logging |
| `providers/openai_compat.py` | `OpenAICompatProvider` | Wraps OpenAI SDK; covers OpenAI, xAI, NIM, OpenRouter |
| `providers/ollama.py` | `OllamaProvider` | Local Ollama — **live-verified 2026-04-29** against qwen3.5:9b on M4 Air |
| `providers/null.py` | `NullProvider` | No-op; for agents like Calendar that don't call an LLM |
| `providers/__init__.py` | `PROVIDERS` dict | Maps provider string keys → classes; three aliases for `OpenAICompatProvider` |

---

## `base.py` — key types

```python
@dataclass
class ModelMetadata:
    name: str           # "qwen3:8b"
    provider: str       # "ollama"
    api_id: str         # provider-specific identifier
    context_window: int
    cost_per_mtok_in: float
    cost_per_mtok_out: float
    capabilities: set[str]    # {"reasoning", "tool_use", "vision", "json_mode", "live_search"}
    tags: set[str]            # {"fast", "cheap", "synthesis", "local"}
    api_key_env: str | None   # env var name for API key (optional)
    base_url: str | None      # static base URL override (optional)
    base_url_env: str | None  # env var for base URL (optional)
```

New fields `api_key_env`, `base_url`, `base_url_env` were added in commit `cf79139` to support the OpenAI-compat provider. See [[04 - Code Map/openai-compat-provider]].

---

## `registry.py` — how it works

1. Reads `config/models.yaml` on init.
2. For each model entry, looks up `PROVIDERS[provider_key]` to get the class.
3. Instantiates the class with `ModelMetadata`.
4. `get_provider(name)` returns a ready-to-call `LLMProvider` instance.

---

## `router.py` — how agents call it

```python
# Inside any agent
llm = router.for_agent("supervisor")          # returns LLMProvider
completion = await llm.complete(system, messages)

# Future (Phase 2.5)
llm = router.for_capability("synthesis")      # picks cheapest synthesis-capable model
```

`build_router()` reads both `models.yaml` + `agents.yaml` and wires everything together. Called once at `terminal.py` startup.

---

## `budget.py` — cost logging

`record(agent_name, completion)` writes to DuckDB `llm_calls`:

```sql
(ts, agent, model, provider, tokens_in, tokens_out, cost_usd, latency_ms, cache_hit, error)
```

Cost computation: `(tokens_in / 1e6) * meta.cost_per_mtok_in + (tokens_out / 1e6) * meta.cost_per_mtok_out`.

---

## Provider aliases

```python
PROVIDERS = {
    "anthropic":    AnthropicProvider,
    "ollama":       OllamaProvider,
    "openai_compat": OpenAICompatProvider,
    "openai":       OpenAICompatProvider,   # alias
    "xai":          OpenAICompatProvider,   # alias
    "null":         NullProvider,
}
```

---

## `OllamaProvider` — live-verification notes (commit `4ea88f9`)

**Status:** Live-verified 2026-04-29 against `qwen3.5:9b` on M4 Air 16 GB.

| Stat | Value |
|---|---|
| Cold-start latency | 46 s (first call after `ollama serve`; model load) |
| Warm latency | ~1–3 s (expected; model already in memory) |
| Test `max_tokens` floor | 256 minimum for reasoning-tier models |
| Default `max_tokens` for `/analyze` | 2000 (unchanged; sufficient) |

**Reasoning-tier models (qwen3.x, gpt-5 thinking)** burn internal tokens before producing visible output. Setting `max_tokens=10` returns an empty string because all tokens go to internal thought. The live-smoke test bumped this to 256; the production `/analyze` default of 2000 is sufficient.

**Models registered (commit `4ea88f9`):**

| Model | Size | Role |
|---|---|---|
| `qwen3.5:9b` | 6.6 GB | Verified local inference option |
| `gemma4:e4b` | 9.6 GB | Second mid-tier option (NOT a fast classifier despite "e4b" tag) |

Fast-classifier role (Phase 2.5 Quality / Macro / Calendar / Ownership) has no pulled candidate yet — phi-class or qwen2.5:3b deferred. Cloud agents (Analyst, Critic) keep OpenAI defaults; local routing is opt-in via `agents.yaml`.

See [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]] for full verification details.

---

## Config files

- `config/models.yaml` — declare models; edit to add/upgrade.
- `config/agents.yaml` — assign agents to models; edit to swap.
- Swap = YAML edit + restart. No code change required.
- See [MODEL-SWAP-GUIDE.md](../docs/MODEL-SWAP-GUIDE.md) for 8 swap playbooks.
