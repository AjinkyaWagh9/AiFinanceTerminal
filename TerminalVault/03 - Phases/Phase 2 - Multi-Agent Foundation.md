# Phase 2 — Multi-Agent Foundation + News Trends

> Back to [[Index]] | See also [[03 - Phases/Phase 1 - MVP]] · [[01 - Architecture/Agent System]] · [[ADR-002 CrewAI then LangGraph]]

**Status:** Planned
**Target weeks:** 3–4
**Source:** [PLAN.md §6 Phase 2](../docs/PLAN.md)

---

## Scope

The terminal stops being a single-shot REPL and becomes a coordinated agent system around news + critique.

- **CrewAI integration:** register agents 1–5 (Supervisor, Data, News & Trend, Critic, Quant/Bull-Bear).
- **News & Trend agent:** RSS aggregation across Indian + global sources, dedupe (MinHash), embeddings → ChromaDB, daily clustering, narrative-arc detection.
- **Critic agent:** runs on every `/analyze` output; confidence score + dissenting view appear in panel.
- **Watchlist persistence** in SQLite.
- **TUI upgrade to Textual:** tabs (Dashboard, Ticker, News, Watchlist).

---

## Status (2026-04-29)

Phase 2 split into independent sub-deliverables for incremental shipping:

| Sub | Name | Status |
|---|---|---|
| 4a | Multi-agent scaffold (`/analyze` → Data + Analyst + Critic) | **Smoke green 2026-04-29** — see [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]] |
| 4b | News & Trend agent + `/trends` | Planned (next) |
| 4c | Watchlist persistence | Already shipped in Phase 1 |
| 4d | Textual TUI migration | Deferred |

Framework note: per ADR-013, 4a uses hand-rolled async over the existing `router.for_agent()` interface, not CrewAI. ADR-002's Phase 3 LangGraph migration plan is unchanged.

---

## Phase 2 backlog (from 4a smoke, 2026-04-29)

Follow-ups and qualitative observations to address in next 4a/4b iterations:

- [ ] **FU-1 — Cache-hit path not smoke-tested.** The two `/analyze RELIANCE` runs were 24 min apart (beyond 300s TTL); cache-hit code path was never exercised end-to-end. Retest: run back-to-back within 5 min. No code change.
- [ ] **FU-2 — Analyst↔dossier source-tag convention drift.** Dossier uses `[FUND-REV]` / `[QUOTE]` / `[NEWS-1]` tags; Analyst uses `[src: fundamentals.revenue_ttm]` / `[src: quote.last_price]` and hallucinates tags not in dossier. Critic's `VERIFY` can't cross-reference reliably. Fix: align `prompts/analyst.md` to use dossier tags.
- [ ] **Critic tone too harsh** — "high severity" used on stylistic critiques. Soften Critic system prompt (`prompts/critic.md`).
- [ ] **Data context too shallow** — Missing: cash-flow (op CF, FCF, capex), net debt, segmental P&L (Jio/Retail/O2C for Reliance), forward EPS consensus, peer multiples, historical PE/ROE band. Data agent enrichment required.
- [ ] **Critic missed conglomerate framing** — consolidated PE/ROE insufficient for diversified targets; need segmental context. Prompt-side fix for Critic system prompt.
- [ ] **ROE/ROCE = 7.9% for Reliance** — possibly correct for current consolidated FY; Data agent spot-check against independent source recommended before trusting Analyst on this metric.

---

## New commands

| Command | Description |
|---|---|
| `/trends sector` | Cross-source narrative clusters |
| `/critic-deep RELIANCE` | Heavy critique cycle |
| `/llm-cost` | 30-day cost by agent and model |
| `/llm-test <model>` | Smoke-test a model side-by-side |

---

## Exit criteria

Opening the terminal at 8 AM surfaces ≥3 actionable signals you wouldn't have found by browsing, using fundamentals + news + critique only.

---

## Key risks

| Risk | Mitigation |
|---|---|
| CrewAI version pinning | Lock to a tested version; read release notes before upgrading |
| MinHash deduplication tuning | Threshold needs calibration; too-aggressive dedup loses related articles |
| ChromaDB cold start on first embed | Pre-warm ChromaDB on startup (backfill last 7 days) |
| Rich → Textual migration complexity | Both are from Will McGugan; `Layout` + `Panel` translate to Textual `Widget`s |

---

## Dependencies on Phase 1

Phase 2 requires Phase 1 exit criteria to pass first (PLAN.md §8 "After Phase 1" advice). Spend 1 week using only the Phase 1 terminal before adding agents — what's actually missing reveals itself.
