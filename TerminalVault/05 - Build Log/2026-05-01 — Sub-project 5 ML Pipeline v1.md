# 2026-05-01 — Sub-project #5 ML Pipeline v1

**What shipped:** Five compute modules (labels, dataset, normaliser, trainer, predictor) + CLI subcommands + inline `/analyze` badge. Test count went **318 → 365** (47 new tests across 7 milestones M1–M7 + polish).

**Core achievement:** Closed the feedback loop: features → model → predictions → outcomes → re-train. Trained v1 of calibrated bull/base/bear probability distributions per (signal, horizon).

---

## Milestones (318 → 365 tests)

| Milestone | What | Tests |
|---|---|---|
| M1 | labels.py — vol-scaled ±1σ labelling; 252d rolling σ | +6 |
| M2 | dataset.py — matrix build, no-peek until_ts, feature_version filter | +8 |
| M3 | normaliser.py — z-norm scaler, round-trip, freeze-on-write `normalized` | +6 |
| M4 | trainer.py — walk-forward 60/20/20 split; LightGBM + isotonic + conformal | +12 |
| M5 | predictor.py — real-time + batch; cold-start contract; stale-model guard | +9 |
| M6 | signal_predictions migration (008) + round-trip backfill | +4 |
| M7 | analyze_flow.py inline badge + end-to-end smoke | +2 |
| Polish | Misc fixes + integration | N/A |

**Total:** M1–M7 = 47 new tests. All pass.

---

## Architecture Summary (Authoritative: [[02 - Decisions/ADR-021]])

1. **Multi-horizon (7d, 30d, 90d)** with vol-scaled bull/base/bear bands (±1σ Nifty volatility).
2. **LightGBM multiclass + per-class isotonic calibration** (sklearn CalibratedClassifierCV dropped in v1.5+; hand-rolled) + **split-conformal (90% coverage)** ~40 LOC.
3. **Walk-forward CV** with **60/20/20 within-fold split** (oldest 60% trains booster, next 20% isotonic-calibrates, newest 20% conformal-calibrates; no shuffling).
4. **Cold-start contract** (< 100 resolved outcomes per horizon) returns class-prior (1/3, 1/3, 1/3) with `model_version="cold_start"`, never `None`.
5. **Stale-model guard:** predictor refuses any bundle whose `manifest.feature_version` mismatches `FEATURE_VERSION` constant; falls back to cold-start.
6. **Atomic symlink promotion** guarded by `mean(Brier) <= prior + 0.01` — silent regression prevention.
7. **signal_predictions table** (migration 008) symmetric with signal_outcomes; (signal_id, horizon_days, model_version) PK lets v1 + v2 coexist for A/B.
8. **model_version format** `lgb_v1_<feature_version>_<UTC YYYYMMDDTHHMMSS>` locks versioning continuity.
9. **Manifest authoritatively records feature_columns order** — closes silent column-reorder mismatch risk.
10. **SHAP top-5 per prediction.**
11. **Non-goals deferred to v1.5:** path signatures (interface stubbed), triple-barrier labelling, CPCV, `/predict` REPL.

---

## Code Map

See [[04 - Code Map/ml — pipeline]] for module breakdown and test matrix.

**Files:**
- `src/finterminal/ml/__init__.py` (new)
- `src/finterminal/ml/labels.py` (new; ~120 LOC)
- `src/finterminal/ml/dataset.py` (new; ~180 LOC)
- `src/finterminal/ml/normaliser.py` (new; ~100 LOC)
- `src/finterminal/ml/trainer.py` (new; ~200 LOC)
- `src/finterminal/ml/predictor.py` (new; ~180 LOC)
- `src/finterminal/commands_ml.py` (new; ~100 LOC)
- `src/finterminal/agents/analyze_flow.py` (modified; inline badge)
- `src/finterminal/commands.py` (modified; `/ml` dispatcher)
- `src/finterminal/data/migrations/008_signal_predictions.sql` (new)
- `tests/ml/*` (new; 7 test files)
- `pyproject.toml` (added lightgbm, scikit-learn, shap, polars)

---

## Test Breakdown

| File | What | Count |
|---|---|---|
| test_labels.py | Vol-scaled bands; unresolved excluded; 252d window; empty → empty | 6 |
| test_dataset.py | Zero missing rows; until_ts honoured; feature_version filter; rejects on missing | 8 |
| test_normaliser.py | Round-trip identity; scaler persist; normalized flag leakage guard | 6 |
| test_trainer.py | Walk-forward respects time; class-prior baseline; Brier per horizon; promotion guard; manifest deterministic | 12 |
| test_predictor.py | Cold-start returns prior; real pred sums ~1; SHAP top-5; stale-model mismatch fires | 9 |
| test_signal_predictions.py | Migration 008; PK enforced; round-trip via backfill | 4 |
| test_analyze_inline.py | /analyze includes badge; cold-start respected | 2 |

---

## Cadence (Phase 2 → 3 foundation)

- **Weekly (Sunday 03:00 IST):** `finterminal ml train` — train all horizons, evaluate, promote if non-regressive.
- **Real-time:** `/analyze` calls `predictor.predict(conn, signal_id)` → inlined badge.
- **Nightly (23:30 IST):** `finterminal ml backfill --since=yesterday` — batch predictions for new signals.

---

## Phase 2 Status

✅ 4a SHIPPED; ✅ B-2a SHIPPED (173 tests); ✅ #1 SHIPPED; ✅ #2 SHIPPED; ✅ #3 SHIPPED (293 tests); ✅ #4 SHIPPED (318 tests); ✅ **#5 SHIPPED (365 tests)**.

---

## Follow-ups (logged for v1.5+)

- Path-signature features (interface stubbed; v1.5 plugs via `extra_feature_builders`).
- Triple-barrier labelling (v1.5).
- CPCV (v1.5).
- Standalone `/predict TICKER HORIZON` REPL (v1.5).
- Hyperparameter search strategy (Optuna; v1 uses LightGBM defaults + early stopping).
- Model registry + rollout harness (v1.5 / Phase 3).

---

## References

- **Spec:** docs/superpowers/specs/2026-05-01-ml-pipeline-v1-design.md
- **ADR:** [[02 - Decisions/ADR-021 — ML Pipeline Architecture (Walk-Forward + Calibration + Conformal)]]
- **Code map:** [[04 - Code Map/ml — pipeline]]
- **Feature store:** [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]]
- **Feature versioning:** [[02 - Decisions/ADR-020 — Feature Versioning and Freeze-on-Write for Safe Model Evolution]]
