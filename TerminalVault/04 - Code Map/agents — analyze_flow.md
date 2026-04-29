# Code Map — agents/analyze_flow.py

> Back to [[Index]] | See also [[04 - Code Map/agents — supervisor]] · [[04 - Code Map/config — agents.yaml]] · [[ADR-013 Hand-rolled Async over CrewAI for Phase 2]]

**File:** `src/finterminal/agents/analyze_flow.py`
**Shipped:** 2026-04-28, commit `6249c13` (scaffold); post-smoke fix commit `9c86769` (2026-04-29)
**Driver:** Phase 2 / 4a multi-agent flow replacing Phase 1's single-agent `supervisor.py`. See [[02 - Decisions/ADR-013 Hand-rolled Async over CrewAI for Phase 2]].

---

## Role

Orchestrates the three-agent linear DAG: `DataAgent → AnalystAgent → CriticAgent`. Exposes `run_analyze(ticker, fresh, registry)` as the single entry point called by `/analyze`.

---

## Key behaviors

- **Result cache** — `RESULT_CACHE_TTL_S = 300` (5 min). On cache hit, skips all three agents and returns stored `payload_json` from DuckDB `analyses` table. Cache-hit code path confirmed not yet smoke-tested end-to-end (FU-1).
- **`--fresh` flag** — bypasses result cache; forces full Data + Analyst + Critic pass.
- **Critic retry-degrade** — if Critic returns an unparseable response, flow degrades gracefully; a `degraded=True` row is written to `critiques` for forensic audit.
- **`registry=None` default** — when called without an explicit `AgentRegistry`, `run_analyze` constructs one via `build_router`. This path was untested until commit `9c86769`.

---

## Import fix (commit `9c86769`, 2026-04-29)

- **Line:** `analyze_flow.py:138`
- **Before:** `from ..llm.router import build_router`
- **After:** `from ..llm import build_router`
- **Why:** `build_router` is exported from `finterminal.llm.__init__`, not from `finterminal.llm.router` directly. Importing from the submodule caused `ImportError` on the `registry=None` default path — i.e., every real CLI invocation of `/analyze` without an injected registry.
- **Regression test added:** `tests/agents/test_analyze_flow.py::test_run_analyze_default_registry_path_resolves_build_router` — exercises `registry=None` with monkeypatched `build_router`. Pre-fix tests all injected fake registries and never hit this path.

---

## Flow summary

```
run_analyze(ticker, fresh=False, registry=None)
  ├── if not fresh and cache_hit → return cached payload (DuckDB analyses)
  ├── DataAgent.run(ticker)      → dossier + raw data
  ├── AnalystAgent.run(dossier)  → 7-section structured output
  └── CriticAgent.run(dossier, analyst_output)
        ├── success → CriticBlock appended to panel
        └── failure → degraded=True row in critiques; panel shows degraded badge
```

---

## Known issues / open follow-ups

- **FU-1:** Cache-hit path never exercised in smoke. Run back-to-back within 5 min to verify.
- **FU-2:** Dossier tag convention (`[FUND-REV]`) diverges from Analyst's `[src: fundamentals.revenue_ttm]` — Critic `VERIFY` directive can't reliably cross-reference. Fix target: align `prompts/analyst.md` to use dossier tags.

---

## Dependencies

- `finterminal.agents.base` — `Agent` protocol, `AgentRegistry`
- `finterminal.agents._dossier` — builds compact source dossier for Critic
- `finterminal.agents.analyst_agent` — `AnalystAgent`
- `finterminal.agents.critic_agent` — `CriticAgent`
- `finterminal.agents.data_agent` — `DataAgent` (deterministic; no LLM)
- `finterminal.llm` — `build_router` (imported from package `__init__`, not submodule)
- `finterminal.data.duckdb_store` — result cache read/write

---

## Cross-links

- ADR: [[02 - Decisions/ADR-013 Hand-rolled Async over CrewAI for Phase 2]]
- Config: [[04 - Code Map/config — agents.yaml]]
- Build log: [[05 - Build Log/2026-04-28 — Multi-Agent Scaffold (4a)]] · [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
