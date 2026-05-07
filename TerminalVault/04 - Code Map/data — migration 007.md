# Data — migration 007

Maps to: `src/finterminal/data/migrations/007_reflexivity.sql`

**Related:** [[04 - Code Map/features — store (freeze-on-write)]] · [[04 - Code Map/features — compute_reflexivity]]

---

## Overview

Schema extension for reflexivity features. Adds four columns to `signal_features` to support:
- Feature versioning (safe model evolution)
- Quality metadata (n_samples, confidence for ML)
- Z-norm activation flag (deferred to sub-project #5)

**Created in:** [[05 - Build Log/2026-05-01 — Sub-project 4 Reflexivity Engine v1]] (Sub-project #4)

---

## SQL DDL

```sql
ALTER TABLE signal_features ADD COLUMN n_samples INTEGER;
ALTER TABLE signal_features ADD COLUMN confidence DOUBLE;
ALTER TABLE signal_features ADD COLUMN feature_version VARCHAR;
ALTER TABLE signal_features ADD COLUMN normalized BOOLEAN DEFAULT FALSE;
```

---

## Schema Changes

| Column | Type | Nullable | Default | Semantics |
|---|---|---|---|---|
| `n_samples` | INTEGER | Yes | NULL | Article count for sentiment features; NULL for price/regime |
| `confidence` | DOUBLE | Yes | NULL | Quality metric [0, 1]; higher = more robust data |
| `feature_version` | VARCHAR | Yes | NULL | Model generation ID; e.g., "reflexivity_v1_vader_decay_0.5" |
| `normalized` | BOOLEAN | No | FALSE | z-norm activation flag; False in v1; True after #5 activator |

---

## Usage in Reflexivity

### After migration, signal_features row for sentiment_level looks like:

```sql
INSERT INTO signal_features (
  signal_id, feature_name, feature_value, is_missing,
  n_samples, confidence, feature_version, normalized
) VALUES (
  'sig-123', 'sentiment_level', 0.25, false,
  8, 0.8, 'reflexivity_v1_vader_decay_0.5', false
)
```

### Non-reflexivity features (price, regime, quality) leave new columns NULL:

```sql
INSERT INTO signal_features (
  signal_id, feature_name, feature_value, is_missing,
  n_samples, confidence, feature_version, normalized
) VALUES (
  'sig-123', 'mom_7d', 0.05, false,
  NULL, NULL, NULL, false
)
```

---

## Design Rationale

1. **n_samples + confidence:** ML layer weights features by data quality. Thin sentiment (2 articles, high entropy) gets lower confidence; robust (12 articles, consensus) gets higher. Allows model to learn signal quality automatically.

2. **feature_version:** Enables evolution without destroying history.
   - v1 sentiment = VADER compound scores
   - v2 sentiment = FinBERT embeddings averaged
   - Both coexist; ML layer compares per-version
   - Backtest is reproducible; no mixing distributions

3. **normalized flag:** Infrastructure for future z-norm activation.
   - False in v1: raw sentiment level, raw entropy, raw deltas
   - True (when #5 activator runs): z-scored within 60d rolling window
   - Allows model to consume both raw and normalized variants without code changes

4. **NULL for legacy features:** Non-reflexivity features (price momentum, regime, quality) don't have sample count or version. NULLs are graceful; ML layer ignores metadata for those features.

---

## Backward Compatibility

- All four columns nullable (except `normalized` which has DEFAULT FALSE)
- Existing price/regime/quality rows auto-populate `normalized=FALSE`
- `n_samples` / `confidence` / `feature_version` remain NULL for non-reflexivity features
- Zero impact on queries that don't use the new columns

---

## Integration Points

| System | Impact |
|---|---|
| [[04 - Code Map/features — compute_reflexivity]] | Emits all four columns in cells |
| [[04 - Code Map/features — store (freeze-on-write)]] | Upsert logic uses feature_version for freeze-on-write |
| ML pipeline (#5) | Reads confidence for weighting; reads feature_version to stratify models |
| Normalization activator (#5) | Reads normalized flag; sets True when z-norm applied |

---

## Testing

Migration is validated by:
- `test_migration_007_columns_exist` — schema introspection confirms all four columns present
- [[04 - Code Map/features — store (freeze-on-write)]] tests round-trip all four columns
- [[04 - Code Map/features — compute_reflexivity]] tests emit all four columns correctly

---

## Cross-Links

- **Build Log:** [[05 - Build Log/2026-05-01 — Sub-project 4 Reflexivity Engine v1]]
- **ADR:** [[02 - Decisions/ADR-020 Feature Versioning and Freeze-on-Write for Safe Model Evolution]]
- **Feature Store ADR:** [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]]
- **Store (freeze-on-write):** [[04 - Code Map/features — store (freeze-on-write)]]
- **Compute:** [[04 - Code Map/features — compute_reflexivity]]
