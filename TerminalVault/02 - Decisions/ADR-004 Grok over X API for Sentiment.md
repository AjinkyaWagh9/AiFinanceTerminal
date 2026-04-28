# ADR-004 — Grok over X API for Sentiment

> Back to [[Index]] | See also [[02 - Decisions/ADR-005 Sentiment is Optional Feature-Flagged Module]] · [[01 - Architecture/Data Sources]]

**Status:** Accepted
**Date:** 2026-04-27 (resolved open question Q1 from PLAN.md §9)
**Source:** [PLAN.md §4.3 Decision Matrix](../docs/PLAN.md)

---

## Context

The terminal includes an optional X (Twitter) sentiment capability. Three acquisition paths exist: X API v2, StockTwits, or xAI Grok Live Search. The main factors: cost, legality/ToS safety, setup burden, and real-time freshness.

---

## Decision

**xAI Grok with Live Search** as the sole sentiment provider.

Pattern: prompt `grok-3-mini` with `"Summarize sentiment on $TICKER from X over the last N hours, cite the top 5 posts"`, store both the structured response and Grok's citations in DuckDB.

---

## Decision matrix (from PLAN.md §4.3)

| Aspect | Weight | Grok+Live Search | X API v2 Basic | X API Free | StockTwits | Skip sentiment |
|---|---:|---:|---:|---:|---:|---:|
| Legality / ToS | 5 | 5 | 5 | 5 | 5 | 5 |
| Cost (Phase 2 steady) | 4 | **5** (~$5–95/mo) | 2 ($200/mo flat) | 5 | 4 | 5 |
| Reliability | 5 | 4 | 5 | 3 | 4 | 5 |
| Setup/maintenance | 5 | **5** (one API) | 2 | 2 | 4 | 5 |
| Real-time freshness | 4 | **5** | 5 | 3 | 4 | 1 |
| **Weighted score** | | **108** | **101** | **80** | **94** | **84** |

---

## Rationale

- One API key replaces X API v2's rate-limit polling + FinBERT pipeline.
- Live Search $5 / 1k calls (verified 2026-04-27). Phase 2 hourly sweep → ~$5–10/mo. Per-ticker hourly → ~$95/mo.
- Grok is a retrieval + classification tool; Claude still owns synthesis and critique.
- Archive discipline: always log Grok's full response + cited post URLs into DuckDB on every call → builds a backtestable audit trail.

---

## Role of Grok vs Claude

- **Grok:** retrieval + sentiment scoring of X posts.
- **Claude:** synthesis, bull/bear analysis, self-critique.
- The Grok output is a *data source* fed into Claude's context block, not a substitute analyst.

---

## Consequences

- `grok-3-mini` registered in `config/models.yaml` under `provider: xai`.
- `GROK_API_KEY` and `SENTIMENT_ENABLED=true` required in `.env` to activate.
- Grok pricing may change — see [[02 - Decisions/ADR-005 Sentiment is Optional Feature-Flagged Module]] for how the terminal stays robust to this.
