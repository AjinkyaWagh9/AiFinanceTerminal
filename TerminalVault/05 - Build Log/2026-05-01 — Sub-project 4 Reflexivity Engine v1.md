# 2026-05-01 — Sub-project #4: Reflexivity Engine v1

**TL;DR:** Sub-project #4 ships the Reflexivity Engine v1 on `feature/reflexivity-v1`. 318 passing tests (293 baseline + 25 new). Five reflexivity features (`sentiment_level`, `sentiment_delta`, `entropy_sentiment`, `entropy_change`, `feature_health`) compute from news headlines via VADER wrapper. Feature versioning via `FEATURE_VERSION` constant + per-row column enables safe model evolution (VADER → FinBERT). Freeze-on-write upsert protects historical truth. Ingestion-time snapshot defends against late-arriving articles. Signal count: 18 → 20 features; `signal_features` schema: 4 → 8 columns.

**Predecessor:** [[05 - Build Log/2026-05-01 — Sub-project 3 Quality Engine v1]]
**Next:** Sub-project #5 — ML pipeline + scoring engine

---

## What Shipped

### Architecture: Five Key Decisions

1. **Feature versioning (safe model evolution)**
   - `FEATURE_VERSION = "reflexivity_v1_vader_decay_0.5"` constant published by compute module
   - `signal_features.feature_version` column stamps each row
   - Enables VADER → FinBERT swap: change `_sentiment_model()` body, bump version, old and new scores coexist
   - ML layer reads version, compares distributions separately

2. **Freeze-on-write upsert (historical truth)**
   - `upsert_features()` uses `WHERE … IS DISTINCT FROM …` clause on UPDATE
   - Same `(signal_id, feature_name, feature_version)` triple = no-op (freeze)
   - Different version = allowed overwrite (model evolution)
   - Protects against accidental recompute corruption

3. **Ingestion-time snapshot (no leakage)**
   - Fetch query: `published_at <= ts AND fetched_at <= ts` (both conditions)
   - Articles published before ts but *fetched* after ts are excluded
   - Prevents late-arriving headlines from poisoning replay / backtest
   - See `_fetch_articles()` in `compute_reflexivity.py:line 505–530`

4. **Single model touchpoint (easy swap)**
   - `_sentiment_model(text)` wraps VADER; returns compound score in [-1, 1]
   - Only function that knows about sentiment library
   - Replace body + bump `FEATURE_VERSION` = zero call-site changes upstream

5. **Feature health (meta-signal)**
   - `feature_health = confidence * (1 - entropy_sentiment / log(3))`
   - High = high-confidence consensus narrative; low = thin data or split sentiment
   - Input: `sentiment_level` (confidence) + `entropy_sentiment` (narrative dispersion)
   - Takes in-memory cells, no second DB hit in orchestrator

### New Modules — `src/finterminal/features/`

| Module | Role |
|---|---|
| `compute_reflexivity.py` | 5 compute functions: `compute_sentiment_level`, `compute_sentiment_delta`, `compute_entropy_sentiment`, `compute_entropy_change`, `compute_feature_health`; `_sentiment_model()` wrapper; helpers: `_fetch_articles()`, `_passes_quality_gate()`, `_weighted_mean()`, `_entropy()`, `_debug_dict()` |

### Schema + Store Hardening

| File | Change |
|---|---|
| `src/finterminal/data/migrations/007_reflexivity.sql` | New: `n_samples`, `confidence`, `feature_version`, `normalized` columns on `signal_features` |
| `src/finterminal/features/store.py` | Rewrite: version-aware `FeatureCell` + freeze-on-write upsert logic |

### Registry & Orchestrator Wiring

| File | Change |
|---|---|
| `src/finterminal/features/registry.py` | Promote 3 sentiment placeholders; add `entropy_change`, `feature_health` (5 new FeatureSpecs) |
| `src/finterminal/features/orchestrator.py` | Reflexivity block: 4 DB-backed computes + 1 meta-signal from in-memory cells |

---

## Key Design Rationale

| Decision | Rationale |
|---|---|
| VADER as v1 sentiment model | Lightweight, deterministic, no API calls; FinBERT path documented; swappable via `_sentiment_model()` wrapper |
| 7-day window for level/entropy | News cycle resolution; captures 1–2 weeks of narrative drift; non-overlapping prior window for delta/entropy_change |
| Min 5 articles per feature | Gate noise: fewer samples = higher entropy; 5 is pragmatic threshold for Indian markets (lower news volume) |
| 70% unique ratio gate | Filters duplicate headlines; 30% duplication is common in RSS feeds |
| Decay weighting: `exp(-0.5 * age_days)` | Recent headlines weight more; 0.5 = moderate recency (vs. 1.0 sharp cutoff); published before fetched—both constrain age |
| Confidence = min(1.0, n_samples / 10) | After 10 articles, hit full confidence; per-signal quality metric for ML layer |
| Normalized = False in v1 | Z-norm activator deferred to #5 once 30-signal history accrues; schema supports future activation |
| feature_health as meta-signal | Model sees narrative quality separately from magnitude; captures "is this signal trustworthy?" |

---

## Test Count

| State | Count |
|---|---|
| Baseline (Sub-project #3) | 293 |
| New (#4) | 25 |
| Total | 318 |

**New test file:**
- `tests/features/test_compute_reflexivity.py` (21 tests)

**Modified test files:**
- `tests/features/test_store.py` (+4 tests: freeze logic, n_samples/confidence/version round-trip)
- `tests/features/test_orchestrator.py` (+further test updates)
- `tests/features/test_registry.py` (PLACEHOLDER_NAMES validation)
- `tests/features/test_atomicity.py` (comment added)

---

## Files Affected

| File | Change |
|---|---|
| `src/finterminal/features/compute_reflexivity.py` | New (5 computes + 7 helpers) |
| `src/finterminal/features/store.py` | Rewrite: version-aware upsert, freeze-on-write |
| `src/finterminal/features/registry.py` | 5 FeatureSpec promotions/additions |
| `src/finterminal/features/orchestrator.py` | Reflexivity block wiring |
| `src/finterminal/data/migrations/007_reflexivity.sql` | New: 4 columns |
| `tests/features/test_compute_reflexivity.py` | New (21 tests) |
| `tests/features/test_store.py` | +4 tests |
| `tests/features/test_orchestrator.py` | +updates |

---

## Commits (via subagent execution of plan)

All commits follow the format:
```
feat(#4): <change>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Topics:
- vaderSentiment dep + migration 007
- freeze-on-write upsert + version/n_samples/confidence on FeatureCell
- compute_sentiment_level + delta with model wrapper, version stamp, ingestion-time fix
- compute_entropy_sentiment + compute_entropy_change with VADER bins
- compute_feature_health — meta-signal of narrative trustworthiness
- promote 5 reflexivity FeatureSpecs + wire orchestrator

---

## Cross-Links

- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- ADR: [[02 - Decisions/ADR-020 Feature Versioning and Freeze-on-Write for Safe Model Evolution]]
- Code map: [[04 - Code Map/features — compute_reflexivity]] · [[04 - Code Map/features — store (freeze-on-write)]] · [[04 - Code Map/data — migration 007]]
- Plan: `/Users/ajinkyawagh/Desktop/FINTERMINAL/docs/superpowers/plans/2026-05-01-reflexivity-engine-v1.md`
- Critique: `/Users/ajinkyawagh/Desktop/FINTERMINAL/input.md` (7 gaps fixed)
- Predecessor: [[05 - Build Log/2026-05-01 — Sub-project 3 Quality Engine v1]]
