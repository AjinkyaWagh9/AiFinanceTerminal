# FINTERMINAL — Vault Index

> Local-first, AI-augmented equity research terminal for Indian + US markets.
> Owner: Ajinkya Wagh | Hardware: MacBook M4 Air 16 GB | Repo: github.com/AjinkyaWagh9/Finance-Terminal

---

## Quick navigation

| Section | What you'll find |
|---|---|
| [[00 - Project Overview]] | Exec summary, goals, success metrics |
| [[01 - Architecture/System Diagram]] | Component diagram + descriptions |
| [[01 - Architecture/LLM Abstraction Layer]] | Model routing design, YAML config, provider protocol |
| [[01 - Architecture/Storage]] | DuckDB + SQLite + ChromaDB rationale |
| [[01 - Architecture/Agent System]] | All 13 agents, roles, phases, model assignments |
| [[01 - Architecture/Data Sources]] | OpenBB, NSE/BSE, Trendlyne, SEBI, AMFI, Grok, etc. |
| [[06 - Glossary]] | Indian-finance + tech terms — NSE/BSE, FII/DII, SAST, CASA, Piotroski, Beneish, Brier, regime, conviction tier, etc. |
| [[07 - External References]] | URLs: OpenBB, xAI, Anthropic, NSE/BSE, SEBI, AMFI, RBI DBIE, Trendlyne, screener.in, etc. |

---

## Design decisions (ADRs)

| ADR | Decision |
|---|---|
| [[02 - Decisions/ADR-001 Indian Markets First]] | NSE/BSE primary; US deferred to Phase 3 |
| [[02 - Decisions/ADR-002 CrewAI then LangGraph]] | CrewAI for MVP speed; migrate hot paths in Phase 3 |
| [[02 - Decisions/ADR-003 DuckDB + SQLite + ChromaDB local-only]] | Three-tier embedded storage, no servers |
| [[02 - Decisions/ADR-004 Grok over X API for sentiment]] | xAI Grok Live Search wins on cost + setup |
| [[02 - Decisions/ADR-005 Sentiment is optional]] | Feature-flagged; terminal works fully without it |
| [[02 - Decisions/ADR-006 Model Abstraction in Phase 1]] | YAML-driven routing built from day one |
| [[02 - Decisions/ADR-007 No DCF no alt-data no backtesting]] | Hard non-goals; scope protection |
| [[02 - Decisions/ADR-008 Phase 2.5 Analyst-Grade Layer]] | 8 new agents turn "smart watchlist" into analyst desk |
| [[02 - Decisions/ADR-009 Synchronous REPL with asyncio.run for LLM calls]] | Sync REPL + asyncio.run bridge; revisit in Phase 2 |
| [[02 - Decisions/ADR-010 Generic OpenAI-Compat Provider Class]] | One class, three aliases (`openai_compat`, `openai`, `xai`); per-model key/URL config |
| [[02 - Decisions/ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] | 3-layer heatmap + Banking Health depth + 5-component Synthesis Layer (Regime/Scenario/Weighter/Calibration/Auditor) — the actual edge over JP Morgan |
| [[02 - Decisions/ADR-012 Custom Indian Data Layer]] | Build dedicated `data/india/` (Screener.in + Moneycontrol/Mint/ET RSS) instead of US-centric global APIs. Implemented commit `1232297` |
| [[02 - Decisions/ADR-013 Hand-rolled Async over CrewAI for Phase 2]] | Drop CrewAI from Phase 2's `/analyze` flow. Use hand-rolled async orchestration with Agent Protocol + AgentRegistry. Phase 3 LangGraph migration unchanged. |
| [[02 - Decisions/ADR-014 Single Tag Convention dotted-path]] | `[src: dotted.path]` is the one canonical source-tag vocabulary; short-codes retired |
| [[02 - Decisions/ADR-015 Provider Chain Pattern for Fallthrough]] | Ordered `_QUOTE_PROVIDERS` list with silent fallthrough; NSE added as yfinance fallback for Indian tickers |
| [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]] | DuckDB bundled `vss` extension chosen over ChromaDB for news embeddings — no extra dep, SQL join support, in-process |
| [[02 - Decisions/ADR-017 — Outcomes Ledger as the System's Moat]] | Per-signal outcomes ledger + 5-engine taxonomy — every signal scored against forward returns vs Nifty 50; sub-project #1 |
| [[02 - Decisions/ADR-018 — Bhavcopy Market Data as Independent Peer Pipeline]] | NSE Bhavcopy pipeline (`market_data/`) is independent peer; MUST NOT import `outcomes/`; enforced by test |
| [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]] | Long-form `signal_features` table; per-signal feature atomicity; z-score gate; feature drift protection; sub-projects #3–#7 dependency |
| [[02 - Decisions/ADR-020 — Feature Versioning and Freeze-on-Write for Safe Model Evolution]] | FEATURE_VERSION constant + per-row column; freeze-on-write upsert; ingestion-time snapshot defense; single model touchpoint; reflexivity v1 |
| [[02 - Decisions/ADR-021 — ML Pipeline Architecture (Walk-Forward + Calibration + Conformal)]] | Multi-horizon (7d, 30d, 90d) bull/base/bear; LightGBM + hand-rolled isotonic + split-conformal; walk-forward 60/20/20 split; cold-start contract; stale-model guard; atomic promotion; ML Pipeline v1 |

---

## Phases

| Phase | Status | Key milestone |
|---|---|---|
| [[03 - Phases/Phase 1 - MVP]] | **Complete** — `/analyze` running live on gpt-5-mini | 5 commands wired; 12 tests pass; bull/bear with sourced citations confirmed on RELIANCE.NS |
| [[03 - Phases/Phase 2 - Multi-Agent Foundation]] | **In Progress** — 4a SHIPPED; B-2a SHIPPED (173 tests); #1 SHIPPED; #2 SHIPPED; #3 SHIPPED (293 tests); #4 SHIPPED (318 tests); #5 SHIPPED (365 tests) | Data→Analyst→Critic; news pipeline; trends UI; NSE fallthrough; markup escape; feature store foundation; quality metrics wired; reflexivity engine; ML pipeline |
| [[03 - Phases/Phase 2.5 - Analyst-Grade]] | Planned | Transcripts, Consensus, Ownership, Quality, Comps, Macro |
| [[03 - Phases/Phase 3 - US + Routing]] | Planned | LangGraph migration, US tickers, probabilistic bull/bear |
| [[03 - Phases/Phase 4 - Polish]] | Planned | Reports, alerts, confidence calibration |

---

## Code map

| Module | Maps to |
|---|---|
| [[04 - Code Map/llm — abstraction layer]] | `src/finterminal/llm/` |
| [[04 - Code Map/data — OpenBB + DuckDB]] | `src/finterminal/data/` (the wrapper that routes between providers; multi-provider fallthrough chain) |
| [[04 - Code Map/data — india module]] | `src/finterminal/data/india/` — Screener.in + RSS aggregator |
| [[04 - Code Map/data — india — nse_quote]] | `src/finterminal/data/india/nse_quote.py` — NSE direct quote API (Q-5 fallback) |
| [[04 - Code Map/ui — Rich-Textual]] | `src/finterminal/ui/panels.py` — all renderers + context helpers |
| [[04 - Code Map/commands]] | `src/finterminal/commands.py` — REPL dispatcher |
| [[04 - Code Map/agents — supervisor]] | `src/finterminal/agents/supervisor.py` — Phase 1 LLM orchestration |
| [[04 - Code Map/agents — analyze_flow]] | `src/finterminal/agents/analyze_flow.py` — Phase 2 Data→Analyst→Critic orchestrator |
| [[04 - Code Map/config — agents.yaml]] | `config/agents.yaml` — agent-to-model mapping; Critic now defaults to `gpt-5-mini` |
| [[04 - Code Map/prompts]] | `src/finterminal/prompts/` |
| [[04 - Code Map/openai-compat-provider]] | `src/finterminal/llm/providers/openai_compat.py` |
| [[04 - Code Map/prompts]] | `src/finterminal/prompts/` — `analyst.md` v2, `critic.md`, `supervisor.md` |
| [[04 - Code Map/news — pipeline]] | `src/finterminal/news/` — 7-module news pipeline (collect → tag → dedupe → embed → cluster → lineage) |
| [[04 - Code Map/agents — news_trend]] | `src/finterminal/agents/news_trend.py` — `NewsTrendAgent`; powers `/trends [sector]` |
| [[04 - Code Map/data — news_store]] | `src/finterminal/data/news_store.py` — DuckDB read/write for 3 news tables |
| [[04 - Code Map/features — compute_quality]] | `src/finterminal/features/compute_quality.py` — 4 quality metrics (roe, leverage, earnings_growth, quality_score) with cross-sectional z-scoring |
| [[04 - Code Map/data — mgmt_claims]] | `src/finterminal/data/migrations/006_mgmt_claims.sql` + CRUD helpers — outcomes ledger for mgmt claims (v1 structural foundation) |
| [[04 - Code Map/features — compute_reflexivity]] | `src/finterminal/features/compute_reflexivity.py` — 5 reflexivity computes (sentiment_level, sentiment_delta, entropy_sentiment, entropy_change, feature_health); VADER wrapper; versioning |
| [[04 - Code Map/features — store (freeze-on-write)]] | `src/finterminal/features/store.py` — version-aware upsert; freeze-on-write semantics; FeatureCell with n_samples/confidence/feature_version |
| [[04 - Code Map/data — migration 007]] | `src/finterminal/data/migrations/007_reflexivity.sql` — adds n_samples, confidence, feature_version, normalized columns to signal_features |
| [[04 - Code Map/ml — pipeline]] | `src/finterminal/ml/` — labels, dataset, normaliser, trainer, predictor modules + signal_predictions table (migration 008); 5 compute modules, walk-forward CV, conformal prediction |

---

## Build log

| Date | Entry |
|---|---|
| 2026-04-27 | [[05 - Build Log/2026-04-27 — Plan finalized]] |
| 2026-04-28 | [[05 - Build Log/2026-04-28 — Phase 1 Day 1 bootstrap]] |
| 2026-04-28 | [[05 - Build Log/2026-04-28 - Phase 1 REPL Wiring Complete]] — all commands wired, 10 tests pass |
| 2026-04-28 | [[05 - Build Log/2026-04-28 - Indian News Gap]] — known pre-Phase-2 gap; yfinance thin for Indian tickers |
| 2026-04-28 | [[05 - Build Log/2026-04-28 - OpenAI Provider Added]] — OpenAICompatProvider; 3 aliases; gpt-5-nano 45× cheaper than Sonnet 4.6 |
| 2026-04-28 | [[05 - Build Log/2026-04-28 - Days 3-5 analyze on gpt-5-mini]] — **Phase 1 complete**; gpt-5 quirks fixed (max_completion_tokens, 8000-token reasoning floor, yfinance window) |
| 2026-04-28 | [[05 - Build Log/2026-04-28 - Strategy Review and Synthesis Layer]] — input.md feedback integrated; PLAN §6.6 added; ADR-011; analyst.md prompt v2 with 6-factor hierarchy + Variant Perception + Conviction tiering |
| 2026-04-28 | [[05 - Build Log/2026-04-28 - OpenBB Keys Wired and Ticker Prefix]] — Benzinga US news live (20 hdlns/call); FMP/FRED/Tiingo/AV probed; `US:AAPL` `NSE:HDFC` prefix syntax; Indian gap requires Phase 2.5.B not API keys |
| 2026-04-28 | [[05 - Build Log/2026-04-28 - Indian Data Layer Shipped]] — Screener.in fundamentals + Moneycontrol/Mint/ET RSS news + Finnhub client. /analyze RELIANCE now cites real EPS, D/E, revenue + today's broker target hike. **Phase 1 genuinely usable for Indian research.** |
| 2026-04-28 | [[05 - Build Log/2026-04-28 — Multi-Agent Scaffold (4a)]] — Data → Analyst → Critic async flow; result cache (5m); prompt caching via Anthropic; Critic with degraded badge on failure |
| 2026-04-29 | [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]] — Smoke green; 3 post-smoke commits; FU-1 + FU-2 + 4 qualitative items tracked as Phase 2 backlog |
| 2026-04-29 | [[05 - Build Log/2026-04-29 — C Sprint (FU-2 Q-1 Q-2 Smoke Green)]] — FU-2 + Q-1 + Q-2 prompt sprint; conglomerate guard; severity rubric; 77 → 93 tests |
| 2026-04-29 | [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]] — Sprint A Ollama live-verified (qwen3.5:9b); Q-5 NSE fallthrough + Q-6 markup escape shipped; 104 → 123 tests; Q-7 backlog |
| 2026-04-29 | [[05 - Build Log/2026-04-29 — Sprint B-2a News Trend]] — Full news + trend pipeline shipped; DuckDB vss; 7 news modules + NewsTrendAgent + Momentum badge; 123 → 173 tests |
| 2026-04-29 | [[05 - Build Log/2026-04-29 — Plan Reshape & Sub-Project 1 Spec]] — Planning session: input.md critique absorbed; build plan reshaped into 4 sub-projects; Sub-project #1 (Outcomes Ledger + Engine Taxonomy) fully specced; dual-pipeline architecture locked; no code shipped |
| 2026-05-01 | [[05 - Build Log/2026-05-01 — Sub-project 3 Quality Engine v1]] — Quality Engine v1 shipped; 4 quality metrics (roe, leverage, earnings_growth, quality_score) wired via compute_quality.py; mgmt_claims ledger (migration 006) foundation for sub-project #6; 266 → 293 tests |
| 2026-05-01 | [[05 - Build Log/2026-05-01 — Sub-project 4 Reflexivity Engine v1]] — Reflexivity Engine v1 shipped; 5 features (sentiment_level, sentiment_delta, entropy_sentiment, entropy_change, feature_health); feature versioning + freeze-on-write upsert; ingestion-time snapshot defense; VADER wrapper; ADR-020; 293 → 318 tests |
| 2026-05-01 | [[05 - Build Log/2026-05-01 — Sub-project 5 ML Pipeline v1]] — ML Pipeline v1 shipped; 5 compute modules (labels, dataset, normaliser, trainer, predictor); walk-forward + isotonic + split-conformal; cold-start contract; stale-model guard; signal_predictions table; inline /analyze badge; ADR-021; 318 → 365 tests |

---

## Key tensions (understand these to understand the project)

- **Local vs. cloud LLM**: Qwen3 8B runs offline and is free; Claude is better but costs money. The [[01 - Architecture/LLM Abstraction Layer]] makes it a YAML swap, not a code change.
- **Sentiment is optional**: Grok Live Search is the best option but the terminal must work without it. See [[02 - Decisions/ADR-005 Sentiment is optional]].
- **Indian-first discipline**: Free NSE/BSE data covers the core use case better than any US-first tool. US expansion waits until Indian watchlist is solid. See [[02 - Decisions/ADR-001 Indian Markets First]].
- **What is deliberately not built**: DCF, alt-data, backtesting, order execution. See [[02 - Decisions/ADR-007 No DCF no alt-data no backtesting]] and `BACKLOG.md`.
