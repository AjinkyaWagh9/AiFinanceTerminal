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
| `providers/ollama.py` | `OllamaProvider` | Local Ollama (Phase 2 stub; importable but minimal in Phase 1) |
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

## Config files

- `config/models.yaml` — declare models; edit to add/upgrade.
- `config/agents.yaml` — assign agents to models; edit to swap.
- Swap = YAML edit + restart. No code change required.
- See [MODEL-SWAP-GUIDE.md](../docs/MODEL-SWAP-GUIDE.md) for 8 swap playbooks.
