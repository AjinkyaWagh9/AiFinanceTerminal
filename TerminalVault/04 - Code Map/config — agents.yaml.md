# Code Map — config/agents.yaml

> Back to [[Index]] | See also [[04 - Code Map/llm — abstraction layer]] · [[04 - Code Map/agents — analyze_flow]] · [[ADR-013 Hand-rolled Async over CrewAI for Phase 2]]

**File:** `config/agents.yaml`
**Role:** Maps agent names to primary model + fallback chain. Read by `Router` / `build_router()` at startup to wire `router.for_agent(name)`.

---

## Current state (as of 2026-04-29, commit `563c11f`)

| Agent key | Primary | Fallbacks | Notes |
|---|---|---|---|
| `analyst` | `gpt-5-mini` | `[gpt-5]` | Unchanged from 4a scaffold |
| `critic` | `gpt-5-mini` | `[gpt-5]` | **Changed 2026-04-29** — was `claude-sonnet-4-6` |
| `supervisor` | (see file) | — | Phase 1 legacy; not used in 4a flow |

---

## Why critic moved to gpt-5-mini (commit `563c11f`, 2026-04-29)

- `Router.fallback_chain("critic")` eagerly instantiates **every** provider in the chain at registry-build time.
- `AnthropicProvider.__init__` raises `ProviderError` on missing `ANTHROPIC_API_KEY`.
- This killed every `/analyze` run before the Analyst even started — the error was thrown during router construction, not during the Critic's actual invocation.
- Fix: set `critic.primary` to `gpt-5-mini` and `fallbacks: [gpt-5]`, matching the analyst block's existing OpenAI-default pattern.
- Claude Sonnet 4.6 swap lines kept as **commented-out** in the YAML for easy re-enabling once `ANTHROPIC_API_KEY` is present in the environment.

---

## Swap instructions

To re-enable Claude for Critic (when `ANTHROPIC_API_KEY` is available):

1. Uncomment the Claude lines in `config/agents.yaml` under `critic`.
2. Ensure `ANTHROPIC_API_KEY` is set in the shell environment before starting the terminal.
3. Restart terminal (registry is built once at startup).

No code change required — YAML edit + restart. See `docs/MODEL-SWAP-GUIDE.md`.

---

## Design note — eager instantiation risk

`Router.fallback_chain()` builds all provider instances at startup, not lazily at call time. Any provider with a missing API key will raise at startup. Mitigation options for Phase 2.5:
- Lazy instantiation (defer provider init to first call)
- Or: validate env vars before adding to fallback chain

---

## Cross-links

- Code map: [[04 - Code Map/llm — abstraction layer]]
- Code map: [[04 - Code Map/agents — analyze_flow]]
- Build log: [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]
- ADR: [[02 - Decisions/ADR-013 Hand-rolled Async over CrewAI for Phase 2]]
