# ADR-006 — Model Abstraction Layer Built in Phase 1

> Back to [[Index]] | See also [[01 - Architecture/LLM Abstraction Layer]] · [[04 - Code Map/llm — abstraction layer]] · [[02 - Decisions/ADR-010 Generic OpenAI-Compat Provider Class]]

**Status:** Accepted
**Date:** 2026-04-27
**Source:** [PLAN.md §3.1, Phase-1-Kickoff.md Day 5](../docs/PLAN.md)

---

## Context

Phase 1 only uses one LLM: Claude Sonnet 4.6 via the Anthropic provider. The abstraction layer (protocol, registry, router, budget) is ~200 lines. The question: build it now, or skip it and refactor in Phase 2?

---

## Decision

**Build the full model abstraction layer in Phase 1.** Agent code never names a model; it calls `router.for_agent("supervisor")`.

---

## Rationale

| Factor | Reasoning |
|---|---|
| Phase 2.5 has 13 agents | Retrofitting model-indirection across 13 agents in Phase 2.5 is a multi-day refactor. Building it in Phase 1 (when there's one agent) costs ~200 lines. |
| YAML-driven swap | Swapping `qwen3:8b → qwen3:32b` for one agent, or upgrading Claude globally, is a YAML edit + restart — no code change. |
| Cost observability | Every call writes `(agent, model, tokens_in, tokens_out, cost_usd)` to DuckDB from day one. After a month you can ask "which agent eats my Claude budget?" |
| Provider isolation | Adding a new provider (Together.ai, Groq) is one new file implementing one protocol method. |
| No premature abstraction | The Phase 1 implementation is simple: `LLMProvider` protocol, `ModelRegistry` loading `models.yaml`, `Router` loading `agents.yaml`. Capability routing, A/B testing, hot-reload come later. |

---

## What "model abstraction" means at each phase

| Capability | Phase | Mechanism |
|---|---|---|
| Per-agent model assignment | 1 | `agents.yaml` |
| New provider plug-in | 1 | drop a file in `providers/` |
| Cost logging per call | 1 | `budget.py` → DuckDB `llm_calls` |
| Fallback on provider error | 2 | Router retries down `fallbacks` list |
| Per-agent cost cap | 2.5 | `BudgetGuard` |
| Capability-based routing | 2.5 | `router.for_capability("synthesis")` |
| Hot reload of `agents.yaml` | 3 | filesystem watcher |
| A/B testing two models | 3 | `mode: ab_test` in agents.yaml |
| Auto-tier-up on low confidence | 4 | Critic-driven escalation |

---

## Consequences

- `src/finterminal/llm/` directory is the only place that knows about model names.
- Swapping Claude for OpenAI or local Qwen is a YAML edit + restart (see [MODEL-SWAP-GUIDE.md](../docs/MODEL-SWAP-GUIDE.md) for all 8 playbooks).
- Tests: `test_openai_provider_registered`, `test_xai_uses_openai_compat_under_the_hood` verify the registry works.
