# LLM Abstraction Layer

> Back to [[Index]] | See also [[ADR-006 Model Abstraction in Phase 1]] · [[04 - Code Map/llm — abstraction layer]] · [[System Diagram]]

**Source:** [PLAN.md §3.1](../docs/PLAN.md) | [MODEL-SWAP-GUIDE.md](../docs/MODEL-SWAP-GUIDE.md)

---

## Design goal

Swapping `qwen3:8b → qwen3:32b` for one agent, or `claude-sonnet-4-6 → claude-opus-4-7` globally, is a **YAML edit + restart, not a code change.** Adding a new provider is one file.

---

## Component map

```
src/finterminal/llm/
├── base.py              LLMProvider protocol; Message, Completion, ModelMetadata dataclasses
├── registry.py          ModelRegistry: loads config/models.yaml, instantiates providers
├── router.py            Router: loads config/agents.yaml → for_agent("supervisor") → handle
├── budget.py            CostTracker; logs every call to DuckDB llm_calls table
└── providers/
    ├── anthropic.py     Claude (Sonnet, Opus)
    ├── ollama.py        Local Ollama (Phase 2 stub)
    ├── openai_compat.py OpenAI, xAI, NIM, OpenRouter, Together — one class, three aliases
    └── null.py          No-op for agents that don't need an LLM (e.g. Calendar)
```

See [[04 - Code Map/llm — abstraction layer]] for line-level detail.

---

## Provider protocol (the only thing agents see)

```python
class LLMProvider(Protocol):
    async def complete(
        self, system: str, messages: list[Message],
        max_tokens: int = 2000, temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
    ) -> Completion: ...

    @property
    def metadata(self) -> ModelMetadata: ...
```

Agents call `router.for_agent("critic")` and get back this protocol. They never name a model.

---

## Configuration files

### `config/models.yaml` — what's available

| Name | Provider | Tags |
|---|---|---|
| qwen3:8b | ollama | local, cheap, fast |
| qwen3:32b | ollama | local, premium, slow |
| phi4-mini | ollama | local, very-fast, classifier |
| claude-sonnet-4-6 | anthropic | cloud, premium, synthesis |
| claude-opus-4-7 | anthropic | cloud, premium, deep-thinking |
| grok-3-mini | xai | cloud, cheap, sentiment |
| gpt-5, gpt-5-mini, gpt-5-nano | openai | cloud, various |

Each entry also carries `context_window`, `cost_per_mtok_in/out`, `capabilities`, and optional `api_key_env` / `base_url` / `base_url_env`.

### `config/agents.yaml` — who uses what

```yaml
supervisor:    { primary: claude-sonnet-4-6, fallbacks: [claude-opus-4-7] }
data:          { primary: qwen3:8b,          fallbacks: [claude-sonnet-4-6] }
critic:        { primary: claude-sonnet-4-6, fallbacks: [claude-opus-4-7] }
sentiment:     { primary: grok-3-mini,       fallbacks: [], enabled: false }
calendar:      { primary: null }
```

---

## OpenAI-compat provider aliases

`openai_compat`, `openai`, and `xai` all map to `OpenAICompatProvider`. Per-model `api_key_env` + `base_url` carry the differentiation. See [[02 - Decisions/ADR-010 Generic OpenAI-Compat Provider Class]].

---

## Capability roadmap

| Capability | Phase |
|---|---|
| Per-agent model assignment via YAML | 1 ✅ |
| New provider = one new file | 1 ✅ |
| Cost logging to DuckDB `llm_calls` | 1 ✅ |
| Fallback on provider error (router walks `fallbacks` list) | 2 |
| Per-agent monthly cost cap (`BudgetGuard`) | 2.5 |
| Capability-based routing (`router.for_capability("synthesis")`) | 2.5 |
| Hot reload of `agents.yaml` without restart | 3 |
| A/B testing two models on same agent | 3 |
| Auto-tier-up (Opus when Sonnet confidence < threshold) | 4 |

---

## Swap playbooks

Full step-by-step in [MODEL-SWAP-GUIDE.md](../docs/MODEL-SWAP-GUIDE.md). Eight playbooks:
1. Swap one agent's model
2. Globally upgrade Claude (Sonnet → Opus)
3. Upgrade local model (qwen3:8b → qwen3:32b) on hardware upgrade
4. Add a new OpenAI-compatible endpoint (NIM, Groq, OpenRouter)
5. Add a brand-new provider class
6. Cost crisis: migrate an agent to a cheaper model
7. Disable an entire agent (sentiment off)
8. Pin a model version
