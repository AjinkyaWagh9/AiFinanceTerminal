# ADR-017 — Outcomes Ledger as the System's Moat

> Build a per-signal measurement layer that resolves every signal the system emits against forward returns vs Nifty 50, making the terminal's edge provable.

**Status:** Accepted
**Date:** 2026-04-29
**Source:** input.md critique (2026-04-29 planning session); [[05 - Build Log/2026-04-29 — Plan Reshape & Sub-Project 1 Spec]]
**Drivers:** No existing mechanism proves whether system signals predict market outcomes. Without this, the terminal is unfalsifiable narrative.

---

## Context

Sprint B-2a shipped news clustering and trend detection. The system now emits `cluster_momentum` signals. But there is no way to answer: "When this signal fired, did the relevant ticker outperform Nifty 50 over the next 7 / 30 / 90 days?"

input.md's load-bearing critique: the system cannot prove it makes money. This is not a feature count problem — it is a measurement plumbing problem. Sub-project #1 closes it.

Full spec: `docs/superpowers/specs/2026-04-29-foundation-outcomes-engines-design.md`
Full plan (15 TDD tasks): `docs/superpowers/plans/2026-04-29-foundation-outcomes-engines.md`

---

## Decisions

| # | Decision |
|---|---|
| D1 | **Per-signal granularity** — one row per emission in `signals`; aggregates are derived |
| D2 | **Hybrid schema** — `signals` flat + `signal_outcomes` long (one row per horizon) |
| D3 | **Engine taxonomy lives in Python** — `Engine` and `SignalType` enums in `outcomes/schema.py`; not DB tables |
| D4 | **Stub outcome rows inserted at emit time** — 5 rows per signal (1 / 7 / 30 / 90 / 365 days) with NULL ret; makes "find unresolved" cheap |
| D5 | **Sentinel tickers** — `_MACRO` and `_NIFTY50` for non-equity signals; keeps ticker NOT NULL + uniqueness constraint intact |
| D6 | **`_MACRO` signals resolve against Nifty forward return** — a regime_shift signal's "did it work?" is whether Nifty moved as predicted |
| D7 | **Calendar-day horizons, not trading-day** — avoids holiday-calendar dependency; resolution finds last close ≤ target date |
| D8 | **Wiring from `cluster.py` is fail-safe** — try/except; failures never break `/refresh-news`; gated by `OUTCOMES_LEDGER_ENABLED` flag |
| D9 | **Two independent upstream pipelines** — see [[02 - Decisions/ADR-018 — Bhavcopy Market Data as Independent Peer Pipeline]] |
| D10 | **Store full OHLCV in `prices_eod`**, not just close — future volume/gap/ATR signals need it; marginal storage cost |
| D11 | **Every fetch attempt logged in `ingestion_log`** — audit trail; cheap answer to "did we have yesterday's prices?" |

---

## Schema (summary)

| Table | Owned by | Purpose |
|---|---|---|
| `signals` | `outcomes/` | One row per signal emission; regime snapshot cols |
| `signal_outcomes` | `outcomes/` | Per-horizon return rows (5 per signal); NULL until resolved |
| `prices_eod` | `market_data/` | OHLCV by (ticker, trade_date); source of truth for resolution |
| `ingestion_log` | `market_data/` | Audit log for every bhavcopy fetch attempt |

Full DDL: `src/finterminal/data/migrations/004_outcomes_ledger.sql`

---

## Engine Taxonomy

| Engine | Key signal types |
|---|---|
| `mispricing` | `divergence` |
| `quality` | `claim_reconciliation` |
| `regime` | `regime_shift` |
| `reflexivity` | `cluster_momentum`, `sentiment_delta` |
| `risk` | `risk_trigger` |

Defined in `src/finterminal/outcomes/schema.py` as `Engine` + `SignalType` enums + `SIGNAL_REGISTRY` dict.

---

## Consequences

### Positive
- Every signal the system emits now has a falsifiable forward-return track record
- `queries.predictive_power(signal_type, horizon)` becomes a first-class primitive
- Engine taxonomy organises all future signals into five coherent categories
- Enables sub-projects #2, #3, #4 to contribute signals that are immediately scored

### Negative / risks
- Zero ROI until ≥ 30 days of signals accumulate (outcomes resolve over time)
- NSE URL / cookie patterns may drift — centralized `_http.py` mitigates but doesn't eliminate
- Regime cols partially NULL in v1 (INR, Brent, 10y yield sources not wired)

### What this does NOT change
- ADR-007 non-goals (no DCF, no backtesting, no alt-data) remain in force
- `market_data/` never imports `outcomes/` — see ADR-018

---

## Alternatives Considered and Rejected

| Alternative | Why rejected |
|---|---|
| Wide table per-signal (all horizons as columns) | NULL bloat; can't add horizons without migration |
| Full normalization (FK between signals → outcomes → prices) | DuckDB house style avoids FK constraints (match 003 pattern) |
| Reuse Bhavcopy via existing `data/india/nse_quote.py` | Real-time quote API ≠ official EOD archive; different cadence, different reliability |
| Shared pipeline module for both news + price ingest | Couples independent systems; contradicts D9 |

---

## Cross-Links

- Triggered by: [[05 - Build Log/2026-04-29 — Plan Reshape & Sub-Project 1 Spec]]
- Peer pipeline: [[02 - Decisions/ADR-018 — Bhavcopy Market Data as Independent Peer Pipeline]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]] (sub-project #1, B-2b on hold)
- Supersedes (partially): [[02 - Decisions/ADR-007 No DCF no alt-data no backtesting]] — outcomes ledger is NOT backtesting (no strategy simulation); it is forward-measurement of live signals
