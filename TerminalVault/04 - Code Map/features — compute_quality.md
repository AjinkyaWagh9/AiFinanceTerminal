# Features — compute_quality

Maps to: `src/finterminal/features/compute_quality.py`

**Related:** [[04 - Code Map/features — registry]] · [[04 - Code Map/features — freshness]] · [[04 - Code Map/features — orchestrator]]

---

## Overview

Four compute functions implementing the Quality Engine v1. Produces cross-sectional z-score based quality metrics for individual equities.

**Added in:** [[05 - Build Log/2026-05-01 — Sub-project 3 Quality Engine v1]] (Sub-project #3)

---

## Functions

### `compute_roe(ticker: str, as_of: date) -> float | None`

**Returns:** Return on Equity as direct column from `fundamentals` table.

- Source: `fundamentals.roe` (set during data ingest from Screener.in or manual load)
- Staleness gate: [[04 - Code Map/features — freshness]] calls `is_fundamentals_data_fresh(ticker, as_of)`
- Returns None if stale or missing

---

### `compute_leverage(ticker: str, as_of: date) -> float | None`

**Returns:** Debt-to-equity ratio (negative for quality ranking: lower debt is better).

- Source: `fundamentals.debt_to_equity`
- Staleness gate: Same as ROE
- Formula: `-debt_to_equity` (negated so higher z-score = better quality in composite)
- Returns None if missing

---

### `compute_earnings_growth(ticker: str, as_of: date) -> float | None`

**Returns:** Year-over-year earnings growth.

- Source: Derived from `fundamentals.net_income_ttm` (quarterly updates)
- Computation: `(net_income_ttm_current - net_income_ttm_1y_ago) / abs(net_income_ttm_1y_ago)`
- Staleness gate: Same as ROE
- Returns None if insufficient history or missing

---

### `compute_quality_score(ticker: str, as_of: date, cross_section: list[str] | None = None) -> float | None`

**Returns:** Equal-weight cross-sectional z-score of (z_roe, -z_leverage, z_earnings_growth).

**Parameters:**
- `ticker`: symbol to score
- `as_of`: reference date
- `cross_section`: list of tickers to use for z-score normalization (e.g., sector or index); if None, uses full universe

**Behavior:**
- Calls `compute_roe()`, `compute_leverage()`, `compute_earnings_growth()` for each ticker in cross_section
- Computes mean and std of each metric across cross_section
- Z-scores the target ticker's metrics: `(value - mean) / std`
- Uses helper `_zscore()` which returns 0.0 (not None) for degenerate stats
- Returns equal-weight average of three z-scores: `(z_roe + (-z_leverage) + z_earnings_growth) / 3`
- Returns `is_missing` if:
  - Any input metric is None
  - Cross-section size < MIN_CROSS_SECTION_COUNT (3)
  - Target ticker not in cross_section

**Z-score degenerate handling:**
```
_zscore(value, mean, std):
  if std == 0:
    return 0.0  # neutral contribution, not None
  else:
    return (value - mean) / std
```

---

## Dependencies

| Dependency | File | Role |
|---|---|---|
| Fundamentals table | Migration 001 | Raw ROE, debt_to_equity, net_income_ttm columns |
| is_fundamentals_data_fresh | [[04 - Code Map/features — freshness]] | Gate: returns False if stale (>120 days) |
| Orchestrator call | [[04 - Code Map/features — orchestrator]] | Wired in quality computation block; receives cross_section from universe snapshot |

---

## Design Rationale

1. **Reuse existing table:** fundamentals table (migration 001) already has the columns; no separate quality-specific table needed.

2. **Cross-sectional z-score:** Ranks equities within a peer set (sector or index). Avoids absolute thresholds and adapts to market regime. Equal-weight (not correlation-weighted) keeps logic simple for v1.

3. **MIN_CROSS_SECTION_COUNT=3:** Ensures at least 3 tickers to compute meaningful statistics. Smaller sets lead to unstable z-scores.

4. **120-day staleness gate:** Fundamentals are quarterly (~90 days apart). Using 120-day gate (one quarter buffer) vs price data's 5-day gate reflects data frequency.

5. **Degenerate handling (0.0 not None):** If all tickers in cross_section have same ROE (std=0), setting that metric to z-score 0 is neutral (contributes equally to mean) vs NULL (breaks entire score). Graceful degradation.

6. **Negated leverage:** Quality prefers lower debt. Negating it means higher (better) debt_to_equity z-scores become negative contributions, lowering final score. Semantically clearer than explaining "inverse" in scoring docs.

---

## Integration with Orchestrator

[[04 - Code Map/features — orchestrator]] calls this module in its quality computation block:

```
# Pseudocode
for ticker in universe:
  roe = compute_roe(ticker, as_of)
  lev = compute_leverage(ticker, as_of)
  eg = compute_earnings_growth(ticker, as_of)
  quality = compute_quality_score(ticker, as_of, cross_section=universe)
  feature_vector[ticker].update({
    "roe": roe,
    "leverage": lev,
    "earnings_growth": eg,
    "quality_score": quality
  })
```

---

## Testing

- `tests/features/test_compute_quality.py` (15 tests)
  - Unit tests for each compute function
  - Z-score degenerate cases
  - Cross-section size validation
  - Staleness gating

---

## Cross-Links

- **Phase:** [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- **Build Log:** [[05 - Build Log/2026-05-01 — Sub-project 3 Quality Engine v1]]
- **ADR:** [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]]
