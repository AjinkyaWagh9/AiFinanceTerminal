# Features — compute_reflexivity

Maps to: `src/finterminal/features/compute_reflexivity.py`

**Related:** [[04 - Code Map/features — store (freeze-on-write)]] · [[04 - Code Map/features — registry]] · [[04 - Code Map/features — orchestrator]]

---

## Overview

Five compute functions for the Reflexivity Engine v1. Reads news headlines via snapshot + ingestion-safe fetch; scores through VADER sentiment wrapper; emits version-stamped reflexivity signals with quality metadata.

**Added in:** [[05 - Build Log/2026-05-01 — Sub-project 4 Reflexivity Engine v1]] (Sub-project #4)

---

## Architecture: Single Model Touchpoint

The module exports one constant + five compute functions + seven helpers. Model swap (VADER → FinBERT) requires only:
1. Replace `_sentiment_model()` body
2. Bump `FEATURE_VERSION` constant
3. Zero call-site changes

```python
FEATURE_VERSION = "reflexivity_v1_vader_decay_0.5"  # Change this + body to evolve

def _sentiment_model(text: str) -> float:
    """Single point of dependency."""
    return _vader.polarity_scores(text)["compound"]  # Replace here
```

---

## Functions

### `compute_sentiment_level(conn, *, ticker, ts_emitted) -> dict`

**Returns:** Recency-weighted mean sentiment over [ts_emitted - 7d, ts_emitted].

- **Data source:** `news_stories` with `published_at <= ts_emitted AND fetched_at <= ts_emitted`
- **Quality gate:** ≥5 articles, ≥70% unique headlines, std(scores) ≥ 0.05, max age ≤ 7 days
- **Computation:** `sum(score_i * exp(-0.5 * age_days_i)) / sum(exp(-0.5 * age_days_i))`
- **Returns:** `{"value": float, "is_missing": bool, "n_samples": int, "confidence": float, "feature_version": str, "normalized": false, "debug": dict}`
- **Missing:** when quality gate rejects; confidence = min(1.0, n_samples / 10)

---

### `compute_sentiment_delta(conn, *, ticker, ts_emitted) -> dict`

**Returns:** Raw delta between non-overlapping 7-day windows.

- **Windows:** current [ts - 7d, ts], prior [ts - 14d, ts - 7d)
- **Computation:** `level(current) - level(prior)`
- **Missing:** when either window fails quality gate
- **n_samples:** sum of both windows' article counts

---

### `compute_entropy_sentiment(conn, *, ticker, ts_emitted) -> dict`

**Returns:** Shannon entropy of sentiment-bin distribution over [ts - 7d, ts].

- **Bins:** negative (compound < -0.05), neutral (-0.05 to 0.05), positive (> 0.05)
- **Computation:** `-sum(p_i * log(p_i))` where p_i = count_i / total_articles
- **Range:** [0, log(3)] ≈ [0, 1.099]; 0 = consensus, log(3) = maximally split
- **Missing:** when quality gate rejects
- **Use:** detects narrative disagreement; high entropy with positive level = fragile bull case

---

### `compute_entropy_change(conn, *, ticker, ts_emitted) -> dict`

**Returns:** Delta of Shannon entropy between non-overlapping 7-day windows.

- **Windows:** current [ts - 7d, ts], prior [ts - 14d, ts - 7d)
- **Computation:** `entropy(current) - entropy(prior)`
- **Interpretation:** positive = narrative breaking down; negative = consensus forming
- **Missing:** when either window fails quality gate

---

### `compute_feature_health(*, sentiment_level, entropy_sentiment, **_) -> dict`

**Returns:** Meta-signal of narrative trustworthiness.

- **Formula:** `confidence_level * (1 - entropy_sentiment / log(3))`
- **Inputs:** dicts from `compute_sentiment_level()` and `compute_entropy_sentiment()` (already computed; passed as cells)
- **No DB hit:** orchestrator passes in-memory cells; reduces I/O
- **Range:** [0, 1]; high = high-confidence consensus, low = thin data or split sentiment
- **Missing:** when either input is missing
- **Use:** model meta-feature; "how trustworthy is this signal's narrative state?"

---

## Helpers

| Helper | Role |
|---|---|
| `_fetch_articles(conn, ticker, start, end)` | Snapshot + ingestion-safe query with both `published_at <= end` and `fetched_at <= end` filters. Returns list of (headline, compound, age_days) |
| `_passes_quality_gate(articles)` | Validates min_articles, unique ratio, std, max age. Returns bool. |
| `_weighted_mean(articles)` | Recency-weighted mean using `exp(-decay * age_days)` |
| `_entropy(scores)` | Shannon entropy over 3 VADER bins |
| `_debug_dict(articles)` | In-memory debug metadata: mean_score, std, unique_ratio |
| `_make_cell(value, is_missing, n_samples, debug)` | Factory for uniform cell shape: value, is_missing, n_samples, confidence, feature_version, normalized, debug |

---

## Constants

| Constant | Value | Rationale |
|---|---|---|
| `_WINDOW_DAYS` | 7 | News cycle resolution; captures 1–2 weeks of narrative drift |
| `_MIN_ARTICLES` | 5 | Pragmatic threshold for Indian markets (lower news volume) |
| `_MIN_UNIQUE_RATIO` | 0.7 | Filters RSS feed duplication (common ≥30% duplicate headlines) |
| `_MIN_SCORE_STD` | 0.05 | Avoid homogeneous data (all "good news" or all "bad news" = noise) |
| `_MAX_AGE_DAYS` | 7 | Don't fetch stale articles outside the window |
| `_DECAY_LAMBDA` | 0.5 | Moderate recency weighting; 0.5 is less sharp than 1.0 cutoff |
| `_CONFIDENCE_SCALE` | 10 | After 10 articles, hit full confidence = 1.0 |

---

## Design Rationale

1. **Snapshot + ingestion filter:** `fetched_at <= ts` excludes articles published in-window but discovered after emission — defends against late-arriving headlines poisoning replay or backtest.

2. **VADER (not FinBERT v1):** Lightweight, deterministic, no API calls. Swap path clear via `_sentiment_model()` wrapper and `FEATURE_VERSION` constant.

3. **Decay weighting:** Recent articles matter more; 0.5 is moderate (not hard cutoff at 7 days). Expires naturally as age → ∞.

4. **Non-overlapping delta/entropy_change windows:** Ensures independence; avoids double-counting articles.

5. **Feature_health as meta-signal:** Takes in-memory cells so orchestrator doesn't re-query DB. ML layer sees narrative quality separately.

6. **Normalized = False in v1:** Z-norm activator deferred to sub-project #5 once 30-signal history accrues; schema already supports it.

---

## Integration with Orchestrator

[[04 - Code Map/features — orchestrator]] calls this module in its reflexivity block:

```python
# Pseudocode
sl_cell = compute_sentiment_level(conn, ticker=ticker, ts_emitted=ts)
out["sentiment_level"] = sl_cell

out["sentiment_delta"] = compute_sentiment_delta(conn, ticker=ticker, ts_emitted=ts)

es_cell = compute_entropy_sentiment(conn, ticker=ticker, ts_emitted=ts)
out["entropy_sentiment"] = es_cell

out["entropy_change"] = compute_entropy_change(conn, ticker=ticker, ts_emitted=ts)

# Meta-signal: no second DB hit
out["feature_health"] = compute_feature_health(
    sentiment_level=sl_cell,
    entropy_sentiment=es_cell,
)
```

---

## Dependencies

| Dependency | File | Role |
|---|---|---|
| news_stories table | Migration 002 | Raw headline + published_at + fetched_at |
| vaderSentiment library | pyproject.toml (≥3.3.2) | Sentiment scoring |
| Orchestrator | [[04 - Code Map/features — orchestrator]] | Calls 5 compute functions; passes cells to feature_health |

---

## Testing

`tests/features/test_compute_reflexivity.py` (21 tests)

Key coverage:
- Ingestion-time leakage defense (articles published before ts, fetched after ts, are excluded)
- Quality gate thresholds (min articles, unique ratio, std, max age)
- Version constant validation
- Determinism (future articles don't change prior snapshot)
- Feature_health input-missing handling
- Confidence capping at 1.0

---

## Cross-Links

- **Phase:** [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- **Build Log:** [[05 - Build Log/2026-05-01 — Sub-project 4 Reflexivity Engine v1]]
- **ADR:** [[02 - Decisions/ADR-020 Feature Versioning and Freeze-on-Write for Safe Model Evolution]]
- **Feature Store ADR:** [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]]
