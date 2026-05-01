# 2026-05-01 — Sub-project #3: Quality Engine v1

**TL;DR:** Sub-project #3 ships the Quality Engine v1 on branch `feature/quality-engine-v1`. 293 tests passing (266 baseline + 27 new). Four quality features (`roe`, `leverage`, `earnings_growth`, `quality_score`) wired into the feature vector via new `compute_quality.py` module. New `mgmt_claims` ledger table (migration 006) foundational for sub-project #6's `signal_success_rate` feature.

**Predecessor:** [[05 - Build Log/2026-04-29 — Plan Reshape & Sub-Project 1 Spec]]
**Next:** Sub-project #4 — Sentiment routing (Reflexivity engine)

---

## What Shipped

### New Modules — `src/finterminal/features/`

| Module | Role |
|---|---|
| `compute_quality.py` | 4 compute functions: `compute_roe`, `compute_leverage`, `compute_earnings_growth`, `compute_quality_score` using cross-sectional z-scores with MIN_CROSS_SECTION_COUNT=3 |

### Registry & Freshness Updates

| File | Change |
|---|---|
| `src/finterminal/features/registry.py` | Added `MAX_FUNDAMENTALS_STALENESS_DAYS=120`; promoted 4 FeatureSpecs from `compute=None` |
| `src/finterminal/features/freshness.py` | Added `last_fundamentals_date()` + `is_fundamentals_data_fresh()` gate |

### Orchestrator Wiring

| File | Change |
|---|---|
| `src/finterminal/features/orchestrator.py` | Added quality computation block before placeholder loop (atomic commit with FeatureSpec promotion) |

### New Data Layer

| File | Role |
|---|---|
| `src/finterminal/data/duckdb_store.py` | Added `insert_mgmt_claim()` + `list_mgmt_claims()` CRUD helpers |
| `src/finterminal/data/migrations/006_mgmt_claims.sql` | New table: 8 columns + 2 indexes; leakage rule documented in SQL comment |

**Schema (mgmt_claims table):**

| Column | Type | Detail |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Sequential |
| `ticker` | VARCHAR | NSE/BSE symbol |
| `claim_date` | DATE | When claim was filed |
| `claim_type` | VARCHAR | Category (e.g., "guidance", "restructuring") |
| `claim_text` | TEXT | Extracted claim (no NLP in v1 — CRUD only) |
| `claim_source` | VARCHAR | "mgmt", "analyst", "news" |
| `resolved` | BOOLEAN | Outcome recorded |
| `resolved_at` | DATE | When resolved |

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Fundamentals source | Existing `fundamentals` table (migration 001) | Reused table; `roe` and `debt_to_equity` are direct columns; `earnings_growth` derived as YoY of `net_income_ttm` |
| Quality score formula | Cross-sectional equal-weight z-score of (z_roe, -z_leverage, z_earnings_growth) | Requires ≥3 tickers; returns is_missing if any input None or cross-section too small |
| Degenerate handling | `_zscore` returns 0.0 (not None) when stats degenerate | Graceful neutral contribution instead of NULL cascade |
| Fundamentals staleness | MAX_FUNDAMENTALS_STALENESS_DAYS = 120 (one quarter) | Much longer than 5-day price gate because fundamentals are quarterly |
| mgmt_claims design | CRUD only; no NLP extractor in v1 | Structural foundation laid; NLP integration deferred to later sprint |
| mgmt_claims leakage | Documented in SQL comment; feature derivation must use as_of cutoff + exclude claims resolved after (as_of - horizon_days) | Prevents look-ahead bias |
| Commit atomicity | FeatureSpec promotion + orchestrator wiring land together | Completeness check breaks if split |

See [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]] for design context.

---

## Test Count

| State | Count |
|---|---|
| Baseline (4a + B-2a) | 266 |
| New (#3) | 27 |
| Total | 293 |

**New test files:**
- `tests/features/test_compute_quality.py` (15 tests)
- `tests/test_mgmt_claims.py` (5 tests)
- `tests/features/test_freshness.py` (+5 additions)
- `tests/features/test_orchestrator.py` (+2 additions)
- `tests/test_atomicity.py` (comment added)

---

## Commits

Branch: `feature/quality-engine-v1` (cut from `feature/feature-store`)

| Commit | Message |
|---|---|
| `9a69a88` | feat(#3): migration 006 — mgmt_claims ledger table |
| `ac8421d` | feat(#3): compute_roe, compute_leverage, compute_earnings_growth |
| `86ff280` | feat(#3): compute_quality_score — cross-sectional equal-weight z-score |
| `e9c5f27` | feat(#3): promote quality FeatureSpecs + wire orchestrator quality block |
| `487b012` | feat(#3): insert_mgmt_claim + list_mgmt_claims CRUD helpers |

---

## Files Affected

| File | Change |
|---|---|
| `src/finterminal/features/compute_quality.py` | New |
| `src/finterminal/features/registry.py` | MAX_FUNDAMENTALS_STALENESS_DAYS + 4 FeatureSpec promotions |
| `src/finterminal/features/freshness.py` | last_fundamentals_date + is_fundamentals_data_fresh |
| `src/finterminal/features/orchestrator.py` | Quality computation block |
| `src/finterminal/data/migrations/006_mgmt_claims.sql` | New |
| `src/finterminal/data/duckdb_store.py` | insert_mgmt_claim + list_mgmt_claims |
| `tests/features/test_compute_quality.py` | New (15 tests) |
| `tests/test_mgmt_claims.py` | New (5 tests) |
| `tests/features/test_freshness.py` | +5 additions |
| `tests/features/test_orchestrator.py` | +2 additions |
| `tests/test_atomicity.py` | Comment added |

---

## Cross-Links

- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- ADR: [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]]
- Code map: [[04 - Code Map/features — compute_quality]] · [[04 - Code Map/data — mgmt_claims]]
- Predecessor: [[05 - Build Log/2026-04-29 — Plan Reshape & Sub-Project 1 Spec]]
