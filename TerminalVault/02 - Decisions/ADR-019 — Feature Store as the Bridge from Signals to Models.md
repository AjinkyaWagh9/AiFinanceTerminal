---
adr: 019
title: Feature Store as the Bridge from Signals to Models
date: 2026-04-30
status: accepted
context_doc: input.md (architecture critique, 2026-04-30)
spec: docs/superpowers/specs/2026-04-30-feature-store-design.md
plan: docs/superpowers/plans/2026-04-30-feature-store.md
predecessors: ADR-017, ADR-018
---

# ADR-019 — Feature Store as the Bridge from Signals to Models

## Context

`input.md` proposes a full target architecture: data → signals → engines → feature vector → ML models → LLM → critic → outcomes ledger → feedback loop. After review, the high-level shape is compatible with what we shipped on `feature/foundation-outcomes-engines` (ADR-017 outcomes ledger, ADR-018 dual pipelines). The new content is the **feature engineering layer, scoring engine, and feedback loop** — the three layers that turn signals into decisions and decisions into learning.

Four logic flaws in `input.md` need to be fixed before adoption:

1. **H=7 as the single horizon — rejected.** Different signal types peak at different horizons; collapsing to one hides which signals work because of the horizon mismatch. We keep `(1, 7, 30, 90, 365)`.
2. **`reflexivity_score - quality_score` divergence — fixed.** Both inputs are weighted z-sums with different weight schemes; subtraction assumes equivalent scale. Rule: z-score each side over the same 60d window before subtracting. Better still, feed both as separate features and let the model learn the weight.
3. **`signal_success_rate` leakage — gated.** The naive form uses signals whose outcomes haven't resolved yet. Rule: any historical-success feature must take an `as_of` cutoff and exclude signals that resolved after `as_of - horizon_days`.
4. **Entropy without min-articles gate — gated.** With <30 articles in the window, entropy is noise. Rule: feature is NULL with `is_missing=true` when source count is below threshold.

## Decision

Adopt the feature engineering / scoring / feedback layers from `input.md`, decomposed into three sub-projects (#5–#7) that slot in **before** the previously planned sub-project #2 (`/analyze SYMBOL` cards). The cards become much more compelling when they consume scored features rather than raw signal payloads.

### Sub-project re-ordering (final)

| Order | Sub-project | What it ships | Blocks on |
|-------|-------------|---------------|-----------|
| #1 ✅ shipped | Foundation: outcomes ledger + market_data + engine taxonomy | `signals`, `signal_outcomes`, `prices_eod`, `ingestion_log`; `cluster_momentum` wired | — |
| **#5 next** | **Feature store** | `signal_features` table; `features/` package; rolling 60d z-score; freshness gate; computed at emit time | #1 |
| #3 | Quality engine v1 | `mgmt_claims` ledger; `quality_score` feature lights up | #5 (so the feature lights up cleanly) |
| #4 | Reflexivity v1 | sentiment routing per story; `sentiment_delta` / `entropy_*` features light up | #5 |
| #6 | Label generator + scoring v0 (logistic) | `labels` view (alpha-vs-Nifty target, not raw return); logistic models per `(signal_type, horizon)`; `models` table; walk-forward backtest harness | #5 + ≥30d resolved outcomes |
| #2 | `/analyze SYMBOL` 5-engine card | UI consumes scored features | #5, #6 |
| #7 | Kill-switch + retraining cadence | `model_health` table; `/health` REPL; trade gating | #6 |
| #8 | Position sizing v0 | Kelly-fraction / vol-targeting / max-position bounds; takes scored probabilities → position weights | #6, #7 |
| #9 | Universe curation + survivorship-honest history | `tradable_universe` table with as-of-date semantics; delisted tickers preserved with retirement_date | #1 (anytime) |
| #10 | RISK engine v1 | Per-ticker `RISK_TRIGGER` signal types: concentration, drawdown, liquidity-drying. Schema slot exists since #1; signal types undefined | #5, #9 |

### What this ADR commits to architecturally

- **New table in migration 005:** `signal_features (signal_id, feature_name, feature_value, is_missing)` — long-form so adding features doesn't require migration. A `models` table is added later in #6.
- **New package boundary:** `features/` may import from `market_data/` and `outcomes/`; nothing may import from `features/`. Pipeline isolation D9 (ADR-018) extends one layer down.
- **Atomicity:** feature computation runs inside the same DuckDB transaction as the signal+outcome insert. A signal without features is useless for training, so partial writes are not allowed.
- **Reproducibility:** features are frozen at emission time. Fundamentals/news revisions don't retroactively rewrite the feature vector. This is the structural form of the "no leakage" rule.

### What this ADR explicitly rejects

- **One global H=7 model.** Models are trained per `(signal_type, horizon)` — five horizons × N signal types.
- **`y = return > 0` as the prediction target.** In a bull regime, ~60%+ of NSE stocks have positive 7d returns; a constant-yes predictor scores ~60% on this target. Use **`return > Nifty_return`** (alpha-vs-benchmark) as the binary label instead. The schema already supports it: `signal_outcomes.ret_pct_vs_nifty` is the source-of-truth column.
- **XGBoost in v1.** Logistic regression with strong L2 only, until ≥2,000 resolved signals per bucket and stable Brier score for 60d.
- **Module-based critic rebuild now.** Defer; revisit after #5–#7 land. The current LLM critic is sufficient.
- **Median-fill at write time.** Missing features are NULL with `is_missing=true`; imputation is a model concern that may evolve.

### Known gaps and where each is addressed

The `input.md` critique surfaced four gaps and missed eight. Recording all twelve so they don't re-emerge:

| # | Gap | Addressed in | Status |
|---|-----|-------------|--------|
| G1 | Feature engineering layer | #5 | Planned |
| G2 | Scoring engine | #6 | Planned |
| G3 | Feedback-driven retraining | #7 | Planned |
| G4 | Kill-switch | #7 | Planned |
| G5 | Universe definition (which tickers do we score?) | #9 | New sub-project |
| G6 | Position sizing / risk budgeting | #8 | New sub-project |
| G7 | Data quality monitoring (was bhavcopy ingest complete? RSS feeds dead?) | #5 (freshness gate) + #6 (model-input QA) | Partial in #5 |
| G8 | Backtest infrastructure (walk-forward, time-aware CV) | #6 | Folded into scoring sub-project |
| G9 | Model versioning / experiment tracking | #6 (`models` table) + #7 (`model_health`) | Planned |
| G10 | Latency / freshness contracts (perishable signals) | #5 (D12 freshness gate) | Planned |
| G11 | Per-ticker RISK signals (≠ portfolio kill-switch) | #10 — schema slot exists in #1 (`Engine.RISK`, `SignalType.RISK_TRIGGER`); signal types and emitters TBD | Slot reserved |
| G12 | Survivorship bias in NSE universe | #9 — `tradable_universe` keeps delisted tickers with `retirement_date` so historical backtests see real history | Planned |

G1, G7, G10 land in sub-project #5 (this ADR's scope). G2/G3/G4/G8/G9 land in #6/#7. G5/G6/G11/G12 are new sub-projects (#8/#9/#10) added to the roadmap by this ADR.

## Consequences

**Positive:**
- The feature vector is reproducible against future revisions (key prerequisite for honest backtesting).
- Sub-projects #3 and #4 each "light up" features in a known schema — they don't have to invent new wiring.
- The `/analyze` card has real content (scored features) instead of raw payloads.

**Negative:**
- Sub-project #2 (the user-visible cards) is delayed by ~2 sub-projects.
- `emit_signal` becomes more expensive; ingestion is no longer just an INSERT. Mitigated by indexed price lookups and prior-signal queries scoped to (signal_type, ticker).

**Risks:**
- Feature drift between training and serving: same code path computes features at emit and at backfill. This is the simplest defense — single source of truth.
- Z-score is sensitive to `(min_obs, window)` choices. Documented in spec D5; tuning lives behind a registry constant, not scattered through code.
