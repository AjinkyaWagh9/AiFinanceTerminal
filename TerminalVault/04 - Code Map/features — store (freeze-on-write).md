# Features — store (freeze-on-write)

Maps to: `src/finterminal/features/store.py`

**Related:** [[04 - Code Map/features — compute_reflexivity]] · [[04 - Code Map/data — migration 007]]

---

## Overview

Version-aware upsert with freeze-on-write semantics. Protects historical signal feature values from accidental recompute overwrites while enabling safe model evolution via version bumps.

**Updated in:** [[05 - Build Log/2026-05-01 — Sub-project 4 Reflexivity Engine v1]] (Sub-project #4)

---

## Core Contract: Freeze-on-Write

**Rule:** If a row with matching `(signal_id, feature_name, feature_version)` already exists, the upsert is a **no-op** (freeze). A *different* version overwrites — that is how we evolve models.

```python
def upsert_features(conn, signal_id, features):
    """
    INSERT … ON CONFLICT (signal_id, feature_name) DO UPDATE SET …
    WHERE signal_features.feature_version IS DISTINCT FROM EXCLUDED.feature_version
    """
```

---

## FeatureCell TypedDict

```python
class FeatureCell(TypedDict, total=False):
    value: float | None
    is_missing: bool
    n_samples: int | None
    confidence: float | None
    feature_version: str | None
    normalized: bool
```

**Notes:**
- `total=False` → all fields optional; legacy price/regime features work without changes
- Reflexivity features always include `n_samples`, `confidence`, `feature_version`, `normalized`
- Non-reflexivity features leave those fields as None (impacted in schema)

---

## Migration 007 Schema Additions

See [[04 - Code Map/data — migration 007]] for DDL.

| Column | Type | Semantics |
|---|---|---|
| `n_samples` | INTEGER | Article count for sentiment features; NULL for price/regime features |
| `confidence` | DOUBLE | Quality metric; 0.0 (thin data) to 1.0 (robust data) |
| `feature_version` | VARCHAR | Model generation ID (e.g., "reflexivity_v1_vader_decay_0.5"); enables safe swap |
| `normalized` | BOOLEAN | z-norm activation flag; always False in v1; True when activator in #5 runs |

---

## Freeze-on-Write Logic

### Scenario 1: First write with version

```sql
-- Signal S1, feature "sentiment_level", version "reflexivity_v1_vader_decay_0.5"
-- Inserts new row
INSERT … VALUES (S1, sentiment_level, 0.25, false, 5, 0.5, reflexivity_v1_vader_decay_0.5, false)
-- ✅ Row created
```

### Scenario 2: Recompute, same version (freeze)

```sql
-- Attempt to rewrite with same version, different value
INSERT … VALUES (S1, sentiment_level, 0.99, false, 99, 1.0, reflexivity_v1_vader_decay_0.5, false)
-- WHERE signal_features.feature_version IS DISTINCT FROM 'reflexivity_v1_vader_decay_0.5'
-- ❌ WHERE clause evaluates FALSE (version IS NOT DISTINCT FROM itself)
-- → UPDATE clause doesn't execute → freeze → row stays (0.25, 5)
```

### Scenario 3: Model evolution, different version (overwrite)

```sql
-- Swap to FinBERT; same signal, different version
INSERT … VALUES (S1, sentiment_level, 0.42, false, 7, 0.7, reflexivity_v2_finbert, false)
-- WHERE signal_features.feature_version IS DISTINCT FROM 'reflexivity_v2_finbert'
-- ❌ WHERE clause evaluates TRUE (old version != new version)
-- → UPDATE clause executes → new row writes (0.42, 7, reflexivity_v2_finbert)
-- ✅ Both rows exist (one per version); ML layer compares separately
```

### Scenario 4: Legacy feature, no version (normal overwrite)

```sql
-- Price feature, no version specified (NULL)
INSERT … VALUES (S1, mom_7d, 0.05, false, NULL, NULL, NULL, false)
-- Existing row has mom_7d with feature_version=NULL
-- WHERE signal_features.feature_version IS DISTINCT FROM NULL
-- ✅ WHERE clause evaluates TRUE (NULL IS DISTINCT FROM NULL = TRUE in DuckDB)
-- → UPDATE clause executes → row overwrites
```

---

## Why This Matters

**Without freeze-on-write:**
- Rerun compute at time T → different random seed or news ingest order → slightly different score
- Write overwrites → historical signal + feature link is broken
- Backtest becomes non-reproducible

**With freeze-on-write:**
- First emission = truth for that version
- Recompute attempt = silently rejected
- Model evolution = version bump, both generations coexist
- Backtest is reproducible; ML layer is aware of model generations

---

## Integration with Orchestrator

[[04 - Code Map/features — orchestrator]] calls `upsert_features()` atomically with signal + outcome insert:

```python
# Pseudocode inside emit_signal transaction
conn.execute("INSERT INTO signals (id, signal_type, ticker, …) VALUES (…)")
conn.execute("INSERT INTO signal_outcomes (signal_id, ret_pct, …) VALUES (…)")

# Compute all features; build dict
features_dict = {
    "sentiment_level": {...},
    "sentiment_delta": {...},
    "entropy_sentiment": {...},
    ...
}

# Upsert (freeze-on-write enabled)
upsert_features(conn, signal_id, features_dict)

conn.commit()  # All or nothing
```

---

## Design Rationale

1. **Versioning is required for safe evolution:** Without it, swapping VADER → FinBERT creates a single series where old and new scores mix; you can't compare them.

2. **Freeze-on-write is required for reproducibility:** A signal's feature vector is fixed at emission time. Revisions (of news, headlines, fundamentals) don't retroactively change old features — that's the structural form of "no leakage."

3. **Different version overwrites:** Evolution path must be explicit. If you change the model and bump the version, you want the new generation to replace the old one (for forward progress) while keeping a record (for analysis).

4. **NULL version allows legacy behavior:** Non-reflexivity features (price, regime, quality) computed once, overwrite on rerun. Reflexivity features get versions immediately.

---

## Constants and Thresholds

None exported; all inherent to VADER/news domain.

---

## Testing

`tests/features/test_store.py` includes:
- `test_upsert_stores_n_samples_confidence_version` — new fields persist
- `test_upsert_freeze_same_version_does_not_overwrite` — freeze logic
- `test_upsert_different_version_overwrites` — evolution path
- `test_upsert_stores_none_for_non_reflexivity_features` — legacy compat

---

## Cross-Links

- **Build Log:** [[05 - Build Log/2026-05-01 — Sub-project 4 Reflexivity Engine v1]]
- **ADR:** [[02 - Decisions/ADR-020 Feature Versioning and Freeze-on-Write for Safe Model Evolution]]
- **Feature Store ADR:** [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]]
- **Migration 007:** [[04 - Code Map/data — migration 007]]
- **Orchestrator:** [[04 - Code Map/features — orchestrator]]
