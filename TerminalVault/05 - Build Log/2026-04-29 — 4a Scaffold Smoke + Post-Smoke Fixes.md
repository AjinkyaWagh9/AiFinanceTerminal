# 2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes

**TL;DR:** Phase 2 / 4a multi-agent scaffold (Data + Analyst + Critic) passed post-smoke verification on 2026-04-29. Both `/analyze RELIANCE` and `/analyze RELIANCE --fresh` rendered the full 7-section panel + Critic block end-to-end against live OpenAI (`gpt-5-mini` for Analyst and Critic). Three post-smoke fixes were committed on top of the 12-task scaffold work; tests went from 76 → 77. Two follow-up issues were surfaced and tracked for Phase 2 next iterations.

**Predecessor:** [[05 - Build Log/2026-04-28 — Multi-Agent Scaffold (4a)]]
**Commits:** `9c86769`, `f5f9c91`, `563c11f`

---

## Smoke result

| Run | Command | Result |
|---|---|---|
| 1 | `/analyze RELIANCE` | Full 7-section panel + Critic block rendered; cold fetch from live APIs |
| 2 | `/analyze RELIANCE --fresh` | Force-refetch; correct stale-and-refetch path confirmed (~24 min after run 1, beyond 300s TTL) |

Tests: **77/77 passing** (was 76; +1 regression from `9c86769`). Ruff clean.

---

## Post-smoke commits

| SHA | Type | Summary |
|---|---|---|
| `9c86769` | fix(agents) | Import `build_router` from `finterminal.llm` package (`__init__.py`), not `.llm.router` — symbol lives in the package init, not the submodule. Adds regression test for the `registry=None` default path. |
| `f5f9c91` | chore | `ruff --fix` unused imports in `duckdb_store.py`, `router.py`, `test_analyst_agent.py`, `test_analyze_flow.py` |
| `563c11f` | config(agents) | Point Critic at `gpt-5-mini` (was `claude-sonnet-4-6`). `Router.fallback_chain("critic")` eagerly instantiates all providers at registry-build time; `AnthropicProvider.__init__` raises `ProviderError` on missing `ANTHROPIC_API_KEY`, killing every `/analyze` run before the Analyst starts. Matches analyst block's existing OpenAI-default pattern. |

---

## Files affected

| File | Change |
|---|---|
| `src/finterminal/agents/analyze_flow.py:138` | Import path fixed: `from ..llm import build_router` (was `from ..llm.router import build_router`) |
| `tests/agents/test_analyze_flow.py` | New test `test_run_analyze_default_registry_path_resolves_build_router` covering `registry=None` branch with monkeypatched `build_router` |
| `src/finterminal/data/duckdb_store.py` | Unused imports dropped (ruff) |
| `src/finterminal/llm/router.py` | Unused imports dropped (ruff) |
| `tests/agents/test_analyst_agent.py` | Unused imports dropped (ruff) |
| `config/agents.yaml` | `critic.primary` → `gpt-5-mini`; fallbacks `[gpt-5]`; Claude lines kept as comments |

---

## Phase 2 backlog (surfaced by smoke)

### Follow-ups

- [ ] **FU-1 — Cache-hit smoke path not exercised.** The two `/analyze RELIANCE` runs were 24 min apart (beyond `RESULT_CACHE_TTL_S = 300`). The cache-hit code path was never validated end-to-end. Retest: run back-to-back within 5 min. No code change required — observation only.
- [ ] **FU-2 — Analyst↔dossier source-tag convention drift.** Dossier (`src/finterminal/agents/_dossier.py`) emits `[FUND-REV]`, `[FUND-NI]`, `[FUND-PE]`, `[QUOTE]`, `[NEWS-1]` etc. Analyst output uses `[src: fundamentals.revenue_ttm]`, `[src: quote.last_price]`, `[src: news[0]]`, and hallucinates `[src: quote.market_cap]` (not in dossier). Critic's `VERIFY` directive can't reliably match claims to dossier tags. Recommended fix: align `prompts/analyst.md` to use dossier tags (dossier is the deterministic source of truth).

### Qualitative critique observations (prompt-tuning + data enrichment)

- [ ] **Critic tone too harsh** — "high severity" used liberally on stylistic critiques. Soften via prompt edit in the Critic system prompt (likely `prompts/critic.md`).
- [ ] **Data context shallow** — only TTM fundamentals + RSS news + spot quote. Missing: cash-flow statement (operating CF, FCF, capex), net debt (vs D/E alone), segmental P&L (Jio / Retail / O2C / Oil&Gas for Reliance), forward EPS consensus, peer multiples, historical PE/ROE band. Critic is correctly canary-ing for input quality.
- [ ] **Critic missed conglomerate framing** — for diversified targets, consolidated PE/ROE is insufficient; segmental valuation context required. Prompt-side fix for Critic system prompt.
- [ ] **ROE/ROCE = 7.9% for Reliance warrants data-agent spot-check** — may be correct for current consolidated FY but should be cross-verified against an independent source before trusting Analyst output on this metric.

---

## Cross-links

- Predecessor: [[05 - Build Log/2026-04-28 — Multi-Agent Scaffold (4a)]]
- ADR: [[02 - Decisions/ADR-013 Hand-rolled Async over CrewAI for Phase 2]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- Code map: [[04 - Code Map/agents — analyze_flow]] · [[04 - Code Map/config — agents.yaml]]
