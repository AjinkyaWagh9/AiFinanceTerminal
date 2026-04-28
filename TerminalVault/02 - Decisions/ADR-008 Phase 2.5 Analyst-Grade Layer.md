# ADR-008 — Phase 2.5: Analyst-Grade Layer

> Back to [[Index]] | See also [[03 - Phases/Phase 2.5 - Analyst-Grade Layer]] · [[01 - Architecture/Agent System]] · [[01 - Architecture/Data Sources]]

**Status:** Accepted (planned for Weeks 5–7)
**Date:** 2026-04-27
**Source:** [PLAN.md §6.5](../docs/PLAN.md)

---

## Context

After Phase 2, the terminal handles the daily check-in flow. But a JP Morgan / Marcellus / Motilal Oswal analyst's morning involves five capabilities that no amount of news + sentiment can substitute for: **transcripts, consensus revisions, ownership flows, quality scores, peer comps.**

These are free for Indian markets if you know where to look. The moat is in stitching them into a coherent surface.

---

## Decision

**Insert Phase 2.5 between Phase 2 and Phase 3.** Adds 8 new agents, ~15 new commands, and ~14 new DuckDB tables. CEO Tracker is relocated from Phase 2 to Phase 2.5 (analyst-grade signal, not a starter feature).

---

## Capabilities included (from §6.5.2 decision matrix)

| # | Capability | Score | Decision |
|---|---|---|---|
| 1 | Earnings call transcript intelligence | 17 | Phase 2.5 core |
| 2 | Consensus estimates + revisions | 19 | Phase 2.5 core |
| 3 | Ownership flows (FII/DII/promoter/pledges/blocks) | 21 | Phase 2.5 core |
| 4 | Forensic / quality scores (Piotroski/Beneish/Altman/Montier) | 21 | Phase 2.5 core |
| 5 | Comps & relative valuation | 19 | Phase 2.5 core |
| 6 | CEO / leader tracker | 15 | Phase 2.5 (moved from Phase 2) |
| 7 | Event calendar | 17 | Phase 2.5 (trivial, do it) |
| 8 | Macro overlay (DXY/INR/yields/Brent) | 18 | Phase 2.5 core |
| 9 | Multi-timeframe charts (Plotext) | 16 | Phase 2.5 polish |
| 14 | Quant screen library (Magic Formula, GARP, etc.) | 17 | Phase 2.5 polish |

Excluded: sell-side aggregation (Phase 3), DCF (see [[ADR-007 Non-Goals — No DCF, No Alt-Data, No Backtesting]]).

---

## New agents (8 added)

| Agent | LLM | Primary sources |
|---|---|---|
| X Sentiment (optional) | grok-3-mini | xAI Grok Live Search |
| Transcript | Qwen3 8B + Claude | NSE/BSE, Trendlyne, screener.in, YouTube + faster-whisper |
| CEO Tracker | Qwen3 8B | YouTube Data API, NSE/BSE filings |
| Ownership | Phi-4 Mini | NSE/BSE shareholding, SEBI SAST, AMFI, NSDL/CDSL |
| Quality / Forensic | Phi-4 Mini | DuckDB (formula-based) |
| Comps | Qwen3 8B | DuckDB, OpenBB |
| Macro | Phi-4 Mini | OpenBB, FRED, RBI |
| Calendar | (no LLM) | NSE/BSE corp actions, RBI/Fed schedules |

---

## New schema tables (14 added)

`transcripts`, `transcript_sections`, `transcript_topics`, `transcript_guidance`, `consensus_snapshots`, `earnings_actuals`, `ownership_snapshots`, `sast_filings`, `bulk_block_deals`, `mf_holdings`, `fii_flows_daily`, `quality_scores`, `peer_groups`, `valuation_snapshots`, `macro_series`, `sector_macro_betas`, `events`.

---

## Exit criteria

Tested on a 25-name Indian watchlist:
1. `/transcript TICKER Q3` within 30s (cached) or ≤4 min (fresh transcription).
2. `/consensus TICKER` shows 90-day revision trend; ≥8 weeks historical snapshots.
3. `/ownership TICKER` shows ≥4 quarter deltas + 30 days of SAST/bulk/block.
4. `/quality TICKER` returns all four scores with plain-English component breakdown.
5. `/comps TICKER` shows ≥6 peers with 6 multiples each, color-coded.
6. ≥3 non-obvious flags/week across the 25-name watchlist (topic shift, pledge change, quality deterioration, consensus revision, unusual block deal).

---

## Why this is the actual moat

Phase 1–2 = smart watchlist. Phase 2.5 = what a working analyst does not want to give up.
- *What did management say differently this quarter?* → Transcripts
- *What does the street think, and is that view changing?* → Consensus
- *Is smart money accumulating or distributing?* → Ownership
- *Is anything fishy in the accounts?* → Quality
- *Is this cheap or expensive vs. peers?* → Comps
- *What macro headwind is this name exposed to?* → Macro
