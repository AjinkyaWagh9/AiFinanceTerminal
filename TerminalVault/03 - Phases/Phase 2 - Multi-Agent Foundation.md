# Phase 2 — Multi-Agent Foundation + News Trends

> Back to [[Index]] | See also [[03 - Phases/Phase 1 - MVP]] · [[01 - Architecture/Agent System]] · [[ADR-002 CrewAI then LangGraph]]

**Status:** In Progress
**Target weeks:** 3–4
**Source:** [PLAN.md §6 Phase 2](../docs/PLAN.md)

---

## Scope

The terminal stops being a single-shot REPL and becomes a coordinated agent system around news + critique.

- **CrewAI integration:** register agents 1–5 (Supervisor, Data, News & Trend, Critic, Quant/Bull-Bear).
- **News & Trend agent:** RSS aggregation across Indian + global sources, dedupe (MinHash), embeddings → DuckDB vss (ChromaDB rejected — see [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]]), daily clustering, narrative-arc detection. **Shipped B-2a.**
- **Critic agent:** runs on every `/analyze` output; confidence score + dissenting view appear in panel.
- **Watchlist persistence** in SQLite.
- **TUI upgrade to Textual:** tabs (Dashboard, Ticker, News, Watchlist).

---

## Status (2026-04-29)

Phase 2 split into independent sub-deliverables for incremental shipping:

| Sub | Name | Status |
|---|---|---|
| 4a | Multi-agent scaffold (`/analyze` → Data + Analyst + Critic) | **SHIPPED + LIVE-VERIFIED 2026-04-29** — smoke green [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]; Ollama provider live-verified against qwen3.5:9b [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]] |
| B-2a | News & Trend pipeline (`/refresh-news` + `/trends`) | **SHIPPED 2026-04-29** — 173 tests passing; DuckDB vss; 7 news modules + `NewsTrendAgent` + Momentum badge — [[05 - Build Log/2026-04-29 — Sprint B-2a News Trend]] |
| B-2b | `/analyze` enrichment + `/brief` command | **ON HOLD** — paused pending Sub-project #1 (Outcomes Ledger). Resuming before #1 lands would add unevaluated signals with no measurement layer. |
| 4c | Watchlist persistence | Already shipped in Phase 1 |
| 4d | Textual TUI migration | Deferred |

### Active workstream (2026-05-01): Sub-project #3 — Quality Engine

> After input.md critique, the build plan was reshaped into 4 sub-projects. Sub-project #3 (Quality Engine v1) shipped 2026-05-01. Sub-project #4 (Sentiment routing) now active.

| Sub-project | Name | Status |
|---|---|---|
| #1 | Foundation: Outcomes Ledger + Engine Taxonomy | Shipped 2026-04-29 |
| #2 | `/analyze` 5-engine card reshape | Shipped 2026-04-30 |
| #3 | Quality Engine v1 (roe, leverage, earnings_growth, quality_score) | **SHIPPED 2026-05-01** — 293 tests (266 baseline + 27 new) — [[05 - Build Log/2026-05-01 — Sub-project 3 Quality Engine v1]] |
| #4 | Sentiment routing (Reflexivity engine) | **Active** — blocked on outcome ledger baseline signal quality |

See [[05 - Build Log/2026-04-29 — Plan Reshape & Sub-Project 1 Spec]] for full rationale.

Framework note: per ADR-013, 4a uses hand-rolled async over the existing `router.for_agent()` interface, not CrewAI. ADR-002's Phase 3 LangGraph migration plan is unchanged.

---

## Phase 2 backlog (from 4a smoke, 2026-04-29)

Follow-ups and qualitative observations to address in next 4a/4b iterations:

- [ ] **FU-1 — Cache-hit path not smoke-tested.** The two `/analyze RELIANCE` runs were 24 min apart (beyond 300s TTL); cache-hit code path was never exercised end-to-end. Retest: run back-to-back within 5 min. No code change.
- [x] **FU-2 — Analyst↔dossier source-tag convention drift.** Dossier uses `[FUND-REV]` / `[QUOTE]` / `[NEWS-1]` tags; Analyst uses `[src: fundamentals.revenue_ttm]` / `[src: quote.last_price]` and hallucinates tags not in dossier. Critic's `VERIFY` can't cross-reference reliably. Fix: align `prompts/analyst.md` to use dossier tags. — **Done 2026-04-29, commits `cc16a01` `e17bfa6` `3244943`; see [[05 - Build Log/2026-04-29 — C Sprint (FU-2 Q-1 Q-2 Smoke Green)]]**
- [x] **Critic tone too harsh** — "high severity" used on stylistic critiques. Soften Critic system prompt (`prompts/critic.md`). — **Done 2026-04-29 (Q-1), commit `7889024`; severity rubric defined; tone reframed to senior peer-reviewer**
- [ ] **Data context too shallow** — Missing: cash-flow (op CF, FCF, capex), net debt, segmental P&L (Jio/Retail/O2C for Reliance), forward EPS consensus, peer multiples, historical PE/ROE band. Data agent enrichment required.
- [x] **Q-2 — Critic missed conglomerate framing** — consolidated PE/ROE insufficient for diversified targets; need segmental context. Prompt-side fix for Critic system prompt. — **Done 2026-04-29, commit `3244943`; conglomerate guard (principle #8) added to `prompts/analyst.md`; by-name list (Reliance, ITC, L&T, Adani Enterprises, Bajaj Finserv, Tata, Mahindra, Aditya Birla); Confidence capped at 0.55; ITC smoke confirmed**
- [ ] **ROE/ROCE = 7.9% for Reliance** — possibly correct for current consolidated FY; Data agent spot-check against independent source recommended before trusting Analyst on this metric.
- [x] **Q-5 — yfinance provider fallthrough hardening.** `yfinance` frequently returns "possibly delisted" / `EmptyDataError` for valid Indian symbols (e.g., `RELIANCE.NS`) when throttled. Quote-provider chain bails entirely instead of falling through to alternate providers. Fix: graceful provider fallthrough on yfinance throttle. Phase-2 data-layer hardening. — **Done 2026-04-29, commits `cc16a01` `bc269cb`; new `data/india/nse_quote.py`; `_QUOTE_PROVIDERS = ["yfinance", "nse"]`; live-verified on `/analyze ITC` (yfinance timed out, NSE chain held); see [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]]**
- [x] **Q-6 — Rich panel silently strips `[src: ...]` tags (UI rendering bug, pre-existing).** Rich interprets `[src: quote.last_price]`-style bracketed dotted text as failed style markup and strips it from the rendered `analysis_panel`. Tags are correctly emitted by analyst (Critic verifies them in raw text). Fix: escape brackets before passing to Rich's `Panel`/`Text` constructors, or use `Text(..., markup=False)`. Sized: 30–60 min. Cosmetic only; not blocking. — **Done 2026-04-29, commit `0b5e723`; `_escape_markup()` in `ui/panels.py:13`; applied to 5 LLM fields; live-verified on `/analyze ITC` (every `[src: ...]` tag renders literally); see [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]]**
- [ ] **Q-7 — Analyst confidence-cap wording ambiguous.** `prompts/analyst.md` says "Cap your `Confidence` at 0.55" — model correctly chose 0.50 (ceiling semantics) but Critic flagged the phrasing as a small inconsistency. Fix: change to "Confidence may not exceed 0.55". Small prompt tweak; not blocking; deferred to Phase 2.5 prompt-tuning batch. Surfaced 2026-04-29 by ITC Critic run; see [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]]

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
| Embedding model cold start (~8–12 s) | `all-MiniLM-L6-v2` lazy-loaded + cached in `./data/models/`; subsequent runs <4 s — ChromaDB not used (see [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]]) |
| Rich → Textual migration complexity | Both are from Will McGugan; `Layout` + `Panel` translate to Textual `Widget`s |

---

## Dependencies on Phase 1

Phase 2 requires Phase 1 exit criteria to pass first (PLAN.md §8 "After Phase 1" advice). Spend 1 week using only the Phase 1 terminal before adding agents — what's actually missing reveals itself.
