---
adr: 020
title: Feature Versioning and Freeze-on-Write for Safe Model Evolution
date: 2026-05-01
status: accepted
context_doc: input.md (architecture critique), 2026-04-30
spec: docs/superpowers/plans/2026-05-01-reflexivity-engine-v1.md
predecessors: ADR-019 (Feature Store as the Bridge)
successors: ADR-005 (Feature Rollout), ADR-007 (Model Abstraction)
---

# ADR-020 — Feature Versioning and Freeze-on-Write for Safe Model Evolution

## Context

Sub-project #4 ships the Reflexivity Engine v1, which computes five sentiment-based features from news headlines. `input.md` identified a critical flaw in the earlier draft: **it locked the system to VADER sentiment, hid accidental rewrites, and exposed the system to ingestion-time leakage and unversioned drift.**

This ADR establishes the architectural guarantees that make sentiment model evolution safe, reproducible features, and historical data integrity possible.

## Seven Gaps from input.md (Pre-ADR-020)

| Gap | Problem | How ADR-020 Fixes It |
|---|---|---|
| 1. Hardcoded VADER | Only sentiment library imported directly; no swap path | Single `_sentiment_model()` wrapper; bump version, replace body, zero call-site changes |
| 2. No reproducible evolution | Model changes corrupt backward comparability | `feature_version` column stamps each row; old and new scores coexist; ML layer compares per-version |
| 3. No feature lifecycle / freeze | Recompute silently overwrites; truth is lost | Freeze-on-write upsert: same (signal_id, feature_name, feature_version) = no-op |
| 4. Ingestion-time leakage | Late-arriving headlines poison replay | Fetch query: `published_at <= ts AND fetched_at <= ts` (both conditions required) |
| 5. No z-norm activation rule | Where does z-normalization turn on? | `normalized` boolean column in schema; always False v1; activator in #5 |
| 6. No feature health metric | Narrative quality invisible to model | `feature_health = confidence * (1 - entropy_sentiment / log(3))` as 5th feature |
| 7. No debug traceability | Compute results opaque; hard to debug | `debug` dict in every cell (`mean_score`, `std`, `unique_ratio`); not persisted v1 |

## Decision

### 1. Feature Versioning Architecture

**Commit:** Every computed reflexivity feature carries a version constant that changes only when the compute logic or underlying model changes.

```python
# In compute_reflexivity.py
FEATURE_VERSION = "reflexivity_v1_vader_decay_0.5"

# In signal_features table (migration 007)
ALTER TABLE signal_features ADD COLUMN feature_version VARCHAR;
```

**Model evolution path:**
```python
# 1. Change the model (e.g., VADER → FinBERT)
def _sentiment_model(text: str) -> float:
    return finbert_score(text)  # was: _vader.polarity_scores(text)["compound"]

# 2. Bump the version
FEATURE_VERSION = "reflexivity_v2_finbert"  # was: "reflexivity_v1_vader_decay_0.5"

# 3. Emit signals with new version; old and new coexist in schema
# ML layer reads feature_version; trains/compares per version
```

**Versioning scheme:** `<engine>_<model>_<config>` where:
- `<engine>` = reflexivity, quality, regime, etc.
- `<model>` = vader, finbert, xgboost, etc.
- `<config>` = hyperparams or training date; e.g., decay_0.5, 2026-05-01

### 2. Freeze-on-Write Upsert

**Commit:** A row with matching `(signal_id, feature_name, feature_version)` is never overwritten. A *different* version is allowed to overwrite.

```python
# In store.py
conn.execute("""
    INSERT INTO signal_features
        (signal_id, feature_name, feature_value, is_missing, feature_version, …)
    VALUES (?, ?, ?, ?, ?, …)
    ON CONFLICT (signal_id, feature_name) DO UPDATE SET
        feature_value = EXCLUDED.feature_value,
        …
        feature_version = EXCLUDED.feature_version
    WHERE signal_features.feature_version IS DISTINCT FROM EXCLUDED.feature_version
""", rows)
```

**Semantics:**
- **Same version, recompute:** WHERE clause False; UPDATE doesn't execute; row frozen
- **Different version, evolution:** WHERE clause True; UPDATE executes; new version overwrites
- **No version (legacy):** WHERE clause True (NULL IS DISTINCT FROM NULL); normal overwrite

**Consequence:** First emission of a versioned feature is truth. Recompute attempts are silent no-ops. Backtest replay is reproducible — signal features don't drift over time.

### 3. Ingestion-Time Snapshot Defense

**Commit:** Feature fetch queries require *both* `published_at <= ts` *and* `fetched_at <= ts`.

```python
# In _fetch_articles()
rows = conn.execute("""
    SELECT headline, published_at
    FROM news_stories
    WHERE list_contains(tickers, ?)
      AND published_at >= ?
      AND published_at <= ?
      AND fetched_at <= ?  ← CRITICAL: excludes late-arriving articles
    ORDER BY published_at DESC
""", [ticker, start_ts, end_ts, end_ts])
```

**Why:** An article published 2026-04-28 but discovered (fetched) on 2026-05-01 exists "outside" the signal emitted on 2026-04-29. Including it creates leakage: information that didn't exist in the system at emission time retroactively influences the feature value. This breaks both backtest reproducibility and forward-looking signal integrity.

**Example:**
```
2026-04-29 signal emitted:
  - Fetch articles published 2026-04-22 to 2026-04-29 (7-day window)
  - Articles must also be fetched by 2026-04-29
  - → Includes April 28 article fetched April 28
  - → Excludes May 1 discovery of April 28 article

2026-05-01 backtest replay:
  - Same signal re-emitted
  - Same articles in same state
  - Same feature value (reproducibility)
```

### 4. Single Model Touchpoint

**Commit:** `_sentiment_model(text)` is the only function in the codebase that imports a sentiment library.

```python
# In compute_reflexivity.py
def _sentiment_model(text: str) -> float:
    """Single point of model dependency.
    
    Today: VADER. Tomorrow: FinBERT / hybrid. To swap, replace this
    body and bump FEATURE_VERSION. No other code should import a
    sentiment library directly.
    """
    return _vader.polarity_scores(text)["compound"]
```

**Enforcement:** Code review rules, no exceptions. Iff a new function needs sentiment, route through `_sentiment_model()`.

**Consequence:** Model swap requires changing exactly one file (compute_reflexivity.py), one function body, and one constant. ML layer is decoupled from model details.

### 5. Normalized Flag (Deferred Activation)

**Commit:** `signal_features.normalized` is always False in v1. Z-norm activator lives in sub-project #5.

```sql
ALTER TABLE signal_features ADD COLUMN normalized BOOLEAN DEFAULT FALSE;
```

**Rationale:** Z-normalization requires 30+ signals per ticker to compute stable statistics. v1 can't assume that history exists. Sub-project #5 will:
1. Let signals accumulate (30+ per ticker)
2. Compute 60-day rolling z-scores for reflexivity features
3. Set `normalized = True` for scored features
4. ML layer can then train on normalized data

**For v1:** All reflexivity features are emitted raw (`normalized = False`). ML layer sees raw sentiment, raw entropy. Doesn't impact model quality because v1 models are logistic regression with strong L2 (robust to scale).

### 6. Feature Health as Meta-Signal

**Commit:** `feature_health = confidence * (1 - entropy_sentiment / log(3))` is the fifth reflexivity feature, computed from in-memory cells, not re-queried from DB.

```python
def compute_feature_health(*, sentiment_level, entropy_sentiment, **_) -> dict:
    if sentiment_level.get("is_missing") or entropy_sentiment.get("is_missing"):
        return _make_cell(None, True, debug={})
    conf = float(sentiment_level.get("confidence") or 0.0)
    h    = float(entropy_sentiment.get("value") or 0.0)
    h_norm = max(0.0, min(1.0, h / log(3)))
    health = conf * (1.0 - h_norm)
    return _make_cell(health, False, …)
```

**Why:** Narrative quality (consensus + data volume) is invisible to models if only raw scores are provided. `feature_health` captures "how trustworthy is this signal's narrative state?"
- High value: high-confidence consensus (model can lean on it)
- Low value: thin data or split narrative (model should discount)

**Design:** Takes in-memory cells (no DB hit). Orchestrator passes already-computed `sentiment_level` and `entropy_sentiment` dicts. Reduces I/O.

## Architectural Consequences

### Positive

1. **Safe model evolution:** VADER → FinBERT is a three-line change; old/new scores coexist; ML layer is model-agnostic.

2. **Reproducible features:** Signal features are frozen at emission. Rerun signals at any past date and get identical values. Backtest is honest.

3. **No leakage by default:** Ingestion-time filter prevents late-arriving data from poisoning replays. Historical correctness is baked in.

4. **Versioning is explicit:** Every feature row carries its compute generation. ML layer can stratify models, compare distributions, detect model drift.

5. **Single source of truth:** One `_sentiment_model()` function = zero scattered dependencies. Audit trail is clear.

### Negative

1. **Freeze complicates recompute:** If a bug is found in compute logic, the "fix" can't retroactively correct old rows (by design). Mitigation: emit a new version; ML layer trains on both; keep old version for historical accuracy.

2. **Schema verbosity:** Every reflexivity feature row now carries n_samples, confidence, feature_version, normalized. Non-reflexivity rows have NULLs. Mitigation: schema is normalized (long-form); feature name + version is the natural composite key; indexes handle lookups efficiently.

3. **Version namespace collision:** If two developers bump FEATURE_VERSION independently, merging conflicts. Mitigation: version naming scheme enforced in code review; CI test prevents duplicate versions in registry.

## Tradeoffs

| Tradeoff | Choice | Rationale |
|---|---|---|
| Freeze all versions or only versioned? | Only versioned (legacy = normal overwrite) | Backward compat; old features (price, regime) don't break |
| One global version or per-feature? | Per-feature (versioning is in the cell) | Easy to evolve sentiment independently of entropy; future models don't all need bumps |
| Version in schema or config? | Both: constant in code, column in schema | Code is the contract; schema is the implementation; strong coupling |
| Z-norm on or off? | Off (v1), flag for future activation | Data doesn't support it yet; schema ready for it; no code churn |
| Debug dict persisted? | No (in-memory only in v1) | Storage cost without ML value; can add later if debugging demands |

## Related ADRs

- **ADR-019 (Feature Store):** Defines the `signal_features` table and atomicity semantics. ADR-020 adds the versioning/freeze columns.
- **ADR-005 (Sentiment is optional):** Sentiment features are optional to the terminal. ADR-020 ensures they evolve safely if present.
- **ADR-007 (Model Abstraction):** LLM models are swapped via YAML config. ADR-020 applies the same principle to sentiment.

## Implementation Checklist (Sub-project #4)

- [x] Migration 007: four columns on signal_features
- [x] FeatureCell TypedDict: optional fields for new columns
- [x] store.py: freeze-on-write upsert with IS DISTINCT FROM clause
- [x] compute_reflexivity.py: five compute functions + _sentiment_model wrapper
- [x] _fetch_articles: both published_at and fetched_at filters
- [x] FEATURE_VERSION constant exported
- [x] Registry: promote 5 FeatureSpecs
- [x] Orchestrator: reflexivity block wiring
- [x] Tests: freeze logic, ingestion-time leakage defense, version stamping

## Monitoring + Future

**Sub-project #5 (ML pipeline):**
- Read `feature_version` on backfill; train per version
- Trigger retraining when new version appears
- Validate model doesn't degrade on old version

**Sub-project #7 (Kill-switch):**
- If sentiment model swap (v1 → v2) causes model drift, detect via Brier score on held-out set
- Trigger alert; optionally revert to v1 pending retraining

---

## Cross-Links

- **Build Log:** [[05 - Build Log/2026-05-01 — Sub-project 4 Reflexivity Engine v1]]
- **Code Map:** [[04 - Code Map/features — compute_reflexivity]] · [[04 - Code Map/features — store (freeze-on-write)]] · [[04 - Code Map/data — migration 007]]
- **Plan:** `docs/superpowers/plans/2026-05-01-reflexivity-engine-v1.md`
- **Critique:** `input.md` (7-gap analysis that drove this ADR)
- **Predecessor:** [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]]
