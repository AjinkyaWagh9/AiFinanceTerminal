# Feature Store: Frozen Feature Vector at Signal Emission

**Date:** 2026-04-30
**Status:** Spec — pending user review
**Sub-project:** #5 of 7 (post-input.md re-ordering, see ADR-019)
**Predecessors:** Sub-project #1 (outcomes ledger + market_data, shipped)
**Successors blocked by this:** #3 Quality engine v1, #4 Reflexivity v1, #6 Scoring v0
**Decision doc:** `TerminalVault/02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models.md`

---

## 1. Why this exists

Sub-project #1 shipped the outcomes ledger but emit_signal stores only the raw signal payload (e.g. `{cluster_id, story_count_delta}`). To train models we need a **stable, reproducible feature vector** at emission time — not at training time, when fundamentals and news may have been revised.

This sub-project ships the feature engineering layer described in `input.md` §0–§7, with the four logic fixes from ADR-019 baked into the design:

- **No H=7 collapse.** Features are horizon-agnostic; one model per `(signal_type, horizon)` later.
- **Z-on-both-sides for divergence.** `narrative_price_divergence = z(cluster_momentum) - z(mom_7d)`, both rolled over the same 60d window of the same `(signal_type, ticker)` history.
- **`signal_success_rate` deferred to #6.** Computing it correctly requires an as-of cutoff that excludes resolved-after-cutoff outcomes; lives in the scoring sub-project, not here.
- **Entropy gated on min-articles.** Not computed in #5 (entropy needs sentiment, which is #4); but the registry-level rule is established here.

What this sub-project does NOT ship:
- ML models (sub-project #6)
- Quality / sentiment features (sub-projects #3 / #4 — registry slots are reserved as NULL placeholders)
- Backfill of features for the ~weeks of signals already in the ledger (one-shot historical backfill, scoped as a follow-up Q-7B; cheap to write once the v1 compute exists)

```
prices_eod (market_data)  ┐
                           ├─►  features/ (compute) ─►  signal_features  ─► [later: scoring v0]
signals history           ─┘
       ▲
       │ same DuckDB tx
emit_signal (outcomes)
```

## 2. Scope

### In scope
- DuckDB migration `005_signal_features.sql` — `signal_features` table.
- `features/` Python package: registry, rolling-z helper, freshness gate, three compute modules (price / regime / news), store, orchestrator.
- Wiring: `outcomes/ledger.py:emit_signal` calls the orchestrator inside the existing transaction.
- v1 feature catalog: 11 computable features + 7 NULL placeholders (slots reserved for #3/#4).
- **Freshness gate (G7/G10):** all price-derived features mark `is_missing=true` when the most recent `prices_eod` row for the ticker is older than `MAX_PRICE_STALENESS_DAYS` from `ts_emitted`. Same gate applies to Nifty (regime features). Implemented in `features/freshness.py`; consulted by `compute_price.py` and `compute_regime.py`.
- Pipeline-isolation guard extended: `features/` is downstream of both pipelines.
- End-to-end test: emit a `cluster_momentum` signal → assert all 11 computable features have rows; assert NULL placeholders have `is_missing=true`.
- Stale-data integration test: emit a signal where prices stop 10 days before `ts_emitted` → assert price/regime features are `is_missing=true`.

### Out of scope (each becomes its own sub-project or follow-up)
- Models, scoring, retraining (#6).
- Quality features (`roe`, `leverage`, `quality_score`, `earnings_growth`) — registry slots only; compute lives in #3.
- Sentiment features (`sentiment_delta`, `entropy_sentiment`, `entropy_news`) — registry slots only; compute lives in #4.
- Outcome-derived features (`signal_success_rate_60d`, `signal_success_given_regime`) — #6, with leakage gate.
- Historical backfill of features for already-emitted signals — Q-7B follow-up.
- Web UI; the v1 surface is a `/features SIGNAL_ID` REPL command for inspection.

## 3. Architectural decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | Long-form schema: one row per `(signal_id, feature_name)` | Adding a new feature in #6/#3/#4 requires a registry entry only — no migration. Cost: indexed pivot at read time, trivial for our scale. |
| D2 | Feature registry lives in Python (`features/registry.py`), not as a DB table | Matches D3 from ADR-017 (engine taxonomy in code). Static, version-controlled, type-checked. |
| D3 | Feature computation runs inside the same transaction as signal+outcome insert | A signal without its features is useless for training. Atomicity > availability. |
| D4 | Pure functions for compute; orchestrator is the only stateful entry point | Each `compute_*` function takes (`conn`, `ticker`, `ts_emitted`, `payload`, ...) → `dict[name, value]`. Easy to unit-test, no hidden state. |
| D5 | Rolling 60d z-score with `min_obs=30`, exclusive-right window | Below 30 prior observations → NULL with `is_missing=true`. Window is `[ts_emitted - 60d, ts_emitted)` — the signal being emitted is never in its own normalization window. |
| D6 | Two-sided z before subtraction in divergence-style features | Both inputs z'd over the same window; result is unit-equivalent. Fixes input.md §4.1 logic flaw. |
| D7 | Missing features stored as `feature_value=NULL, is_missing=true` | Imputation is a model concern (#6); the store keeps the truth. The flag is a feature itself for the model. |
| D8 | Feature drift defense: same `compute_for_signal` runs at emit and at any backfill | One code path. No "training features" vs "serving features" duality. |
| D9 | Pipeline isolation extended | `features/` may import from `market_data/` and `outcomes/`. Nothing imports from `features/`. Guard test (AST-walk variant) extended in this sub-project. |
| D10 | Horizon-agnostic features | No feature contains "_h7" in its name. Multi-horizon scoring (#6) reads the same feature vector for all 5 horizons. |
| D11 | Idempotency: re-emitting a duplicate signal does NOT recompute features | `emit_signal` already short-circuits on duplicate (returns None). Features are gated behind that same check. |
| D12 | **Freshness gate** — features whose source data is older than `MAX_*_STALENESS_DAYS` from `ts_emitted` are emitted with `is_missing=true` | News-driven signals are perishable (G10). A 6-hour-old `cluster_momentum` is a different statistical object than a 10-day-old one. Defaults: `MAX_PRICE_STALENESS_DAYS=5`, `MAX_NIFTY_STALENESS_DAYS=5`. Tunables live in `registry.py`. The gate also doubles as a data-quality check (G7) — if bhavcopy ingest silently dies for a week, models stop training on lies. |
| D13 | Survivorship handling deferred to #9 | The feature store reads tickers as-given from the signals table. It does not consult `nse_universe` to filter delisted tickers. Survivorship-honest universe is the job of sub-project #9 (`tradable_universe` with `retirement_date`); #5 must not bake in today's universe in any compute path. |

## 4. Schema (`005_signal_features.sql`)

```sql
-- Sub-project #5: feature vector frozen at emission.
-- Conventions match 003/004: VARCHAR keys, IF NOT EXISTS, no FK constraints.

CREATE TABLE IF NOT EXISTS signal_features (
    signal_id     VARCHAR NOT NULL,
    feature_name  VARCHAR NOT NULL,
    feature_value DOUBLE,                  -- NULL when is_missing
    is_missing    BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (signal_id, feature_name)
);

CREATE INDEX IF NOT EXISTS signal_features_name_idx ON signal_features(feature_name);
```

No FK to `signals(signal_id)` — matches the no-FK convention from 003/004 and lets DuckDB drop/recreate `signals` independently if needed.

## 5. Architecture

### 5.1 Package layout

```
src/finterminal/features/__init__.py
src/finterminal/features/registry.py        # FeatureSpec dataclass + V1_FEATURES list + tunables
src/finterminal/features/zscore.py          # rolling_zscore(values, *, min_obs=30) -> float | None
src/finterminal/features/freshness.py       # last_prices_date(...), is_prices_data_fresh(...) — D12 gate
src/finterminal/features/store.py           # upsert_features(conn, signal_id, features: dict) -> None
src/finterminal/features/compute_price.py   # mom_7d, mom_30d, vol_20d, mom_7d_z (gated by D12)
src/finterminal/features/compute_regime.py  # nifty_return_50d, nifty_vol_20d, regime_bull/bear/volatile (gated by D12)
src/finterminal/features/compute_news.py    # cluster_momentum_z, narrative_price_divergence
src/finterminal/features/orchestrator.py    # compute_for_signal(...) — the only public entry point used by ledger
```

### 5.2 v1 feature catalog

**Computable in #5 (11 features):**

| Name | Source | Formula | Missing-when |
|---|---|---|---|
| `mom_7d` | `prices_eod` | `(close[t] / close[t-7d]) - 1` | <7 trading days of prices for ticker before `t` |
| `mom_30d` | `prices_eod` | `(close[t] / close[t-30d]) - 1` | <30 trading days |
| `vol_20d` | `prices_eod` | `std(log_returns over last 20 trading days)` | <20 trading days |
| `mom_7d_z` | derived | `z(mom_7d)` over 60d rolling window of same ticker | <30 prior obs of `mom_7d` |
| `nifty_return_50d` | `prices_eod` (`_NIFTY50`) | `(P_t / P_{t-50d}) - 1` | <50 trading days of Nifty |
| `nifty_vol_20d` | `prices_eod` (`_NIFTY50`) | `std(log_returns over 20d)` | <20 trading days of Nifty |
| `regime_bull` | derived | 1 if `nifty_return_50d > 0 AND nifty_vol_20d ≤ historical_median(nifty_vol_20d, 252d)`, else 0 | inputs missing |
| `regime_bear` | derived | 1 if `nifty_return_50d < 0`, else 0 | inputs missing |
| `regime_volatile` | derived | 1 if `not regime_bull and not regime_bear`, else 0 | inputs missing |
| `cluster_momentum_z` | `signals.payload` history | `z(payload['story_count_delta'])` over 60d of prior `cluster_momentum` signals on same ticker | only emitted on `cluster_momentum` signals; NULL with `is_missing=true` for other signal types |
| `narrative_price_divergence` | derived | `cluster_momentum_z - mom_7d_z` (after both z'd; D6) | either input missing |

**NULL placeholders (registry slots reserved, populated when #3/#4 ship):**

| Name | Owner |
|---|---|
| `roe` | #3 (Quality engine v1) |
| `leverage` | #3 |
| `earnings_growth` | #3 |
| `quality_score` | #3 |
| `sentiment_level` | #4 (Reflexivity v1) |
| `sentiment_delta` | #4 |
| `entropy_sentiment` | #4 |

These appear in `V1_FEATURES` with `compute=None`. The orchestrator writes a row with `feature_value=NULL, is_missing=true` for each, so the schema and consumers stay stable across the next two sub-projects.

### 5.3 Wiring into `emit_signal`

```python
# In outcomes/ledger.py, after the existing outcome-stub insert:
from finterminal.features.orchestrator import compute_for_signal
from finterminal.features.store import upsert_features

# ... existing emit_signal logic up through the outcome-stub insert ...

features = compute_for_signal(
    conn,
    signal_id=signal_id,
    signal_type=st,
    ticker=ticker,
    ts_emitted=ts_emitted,
    payload=payload or {},
)
upsert_features(conn, signal_id, features)

return signal_id
```

If `compute_for_signal` raises, the whole emission rolls back (D3). Callers (`news/pipeline.py`) already wrap `emit_signal` in try/except behind `OUTCOMES_LEDGER_ENABLED`, so a feature failure cannot break the news pipeline either.

### 5.4 Z-score helper (D5)

```python
# features/zscore.py
def rolling_zscore(value: float, history: list[float], *,
                   min_obs: int = 30) -> tuple[float | None, bool]:
    """Returns (z, is_missing). history excludes the value being z'd (D5)."""
    if len(history) < min_obs:
        return None, True
    mu = statistics.mean(history)
    sd = statistics.stdev(history) if len(history) > 1 else 0.0
    if sd == 0.0:
        return None, True
    return (value - mu) / sd, False
```

The orchestrator passes `history = SELECT feature_value FROM signal_features ...` filtered by name, ticker, and `signals.ts_emitted < this signal's ts_emitted`, ordered by ts_emitted DESC, LIMIT (rough 60d window). Exact window boundary in code, not the registry — registry says "60d, min_obs=30" once.

## 6. Leakage and freshness rules

Every compute function is responsible for these:

1. **Prices: `WHERE trade_date <= ts_emitted::DATE`.** Never look at the day's open/high — the signal might have been emitted intraday.
2. **Prior signals: `WHERE ts_emitted < this_signal.ts_emitted`.** Strict less-than (D5 exclusive-right window).
3. **Nifty as a ticker is `_NIFTY50`** (matches ADR-017 sentinel convention).
4. **No outcomes-derived features in #5.** `signal_success_rate_60d` waits for #6 because correctly excluding resolved-after-cutoff outcomes requires an `as_of` parameter that isn't meaningful at emit time (the as-of IS emit time, but the rate is for *training*, where we need to step backward through time).
5. **Pure functions only.** No `datetime.now()` inside compute; everything pulled from `ts_emitted` argument.
6. **Freshness gate (D12).** Before any price-derived compute reads `prices_eod`, it calls `is_prices_data_fresh(conn, ticker, ts_emitted)`. If the most recent `trade_date <= ts_emitted::DATE` is more than `MAX_PRICE_STALENESS_DAYS` (default 5) before `ts_emitted`, the feature is emitted as `is_missing=true` with `feature_value=NULL`. Same applies to `_NIFTY50` for regime features.
7. **Survivorship (D13).** No filter against `nse_universe`. Tickers are read as-given from `signals.ticker`. Delisted-ticker handling lives in sub-project #9.

A guard test (`tests/features/test_no_leakage.py`) seeds prices/signals at `t+1d` past the signal and asserts they don't influence the feature value. A second guard (`tests/features/test_freshness.py`) seeds prices that stop `>5d` before `ts_emitted` and asserts price-derived features are `is_missing=true`.

## 7. Testing strategy

- **Unit per compute function:** seed `prices_eod` deterministically, call the compute, assert the dict.
- **Z-score boundary tests:** below `min_obs` returns NULL+is_missing; zero-variance history returns NULL+is_missing; happy path returns correct z to 1e-9.
- **Leakage test:** emit signal at `t`, seed price at `t+1`, recompute, assert unchanged.
- **Atomicity test:** monkey-patch `compute_for_signal` to throw; assert no signal/outcome/feature rows persist after the call.
- **Idempotency test:** call `emit_signal` twice with same `(signal_type, ticker, ts_emitted)`; assert exactly one set of feature rows.
- **End-to-end:** `tests/integration/test_features_e2e.py` — bhavcopy ingest → emit cluster_momentum signal → assert 11 computable features + 7 NULL-placeholders.

## 8. Open questions (resolve before plan)

None at this stage. The four logic fixes from `input.md` are baked into D5/D6/leakage rules and the deferred feature list. Tuning constants (`min_obs=30`, `window=60d`, regime volatility median window=252d) are educated v1 picks — they live in `registry.py` and can be tuned with one-line changes after we have data.

## 9. Acceptance criteria

- Migration 005 applies cleanly on a DB created from 004.
- 222 (post-foundation review fixes) + new feature tests pass.
- A `cluster_momentum` signal emitted via `/refresh-news` produces 18 rows in `signal_features` (varies by data freshness; 7 always `is_missing=true` as placeholders).
- A signal emitted with stale prices (>5d gap from `ts_emitted`) produces 18 rows where all 9 price+regime features are `is_missing=true` — the freshness gate (D12) verifiably bites.
- Pipeline isolation guard rejects an attempted `from finterminal.features import` inside `market_data/` or `outcomes/` at the module top level (function-local import inside `emit_signal` is the deliberate exception for circular-import avoidance — see plan Task 9).
