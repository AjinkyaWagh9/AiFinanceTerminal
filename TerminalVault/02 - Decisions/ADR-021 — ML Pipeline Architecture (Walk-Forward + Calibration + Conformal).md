---
adr: 021
title: ML Pipeline Architecture (Walk-Forward + Calibration + Conformal)
date: 2026-05-01
status: accepted
context_doc: docs/superpowers/specs/2026-05-01-ml-pipeline-v1-design.md
spec: docs/superpowers/specs/2026-05-01-ml-pipeline-v1-design.md
predecessors: ADR-006 (Model Abstraction), ADR-019 (Feature Store as Bridge), ADR-020 (Feature Versioning + Freeze-on-Write)
successors: ADR-022 (Model Registry + Rollout), ADR-023 (Synthesis Layer)
---

# ADR-021 — ML Pipeline Architecture (Walk-Forward + Calibration + Conformal)

## Context

Sub-project #5 ships the ML Pipeline v1, which consumes the 20-feature store built by sub-projects #1–#4, trains calibrated bull/base/bear probability distributions per signal and horizon, and feeds predictions to Phase 3 Synthesis Layer. The architecture must close the feedback loop: features → model → predictions → outcomes → re-train.

## Seven Architectural Commitments

### 1. Multi-Horizon Bull/Base/Bear with Volatility-Scaled Bands

Labelling rule:
- `bull` if `ret_pct_vs_nifty > +σ`
- `bear` if `ret_pct_vs_nifty < -σ`
- `base` otherwise

where `σ = stdev(daily Nifty log returns over 252 trading days preceding signal.ts_emitted)`.

**Why:** Nifty volatility couples to single-stock regime; vol-scaled bands adapt. Three horizons (7d, 30d, 90d) capture fast momentum, medium reversion, long structural change.

**Reference:** `ml/labels.py` computes this per `(signal, horizon)`.

### 2. LightGBM Multiclass + Per-Class Isotonic Calibration + Hand-Rolled Split-Conformal

**Booster:** `LGBMClassifier(objective="multiclass", num_class=3, metric="multi_logloss", random_state=42)`.

**Calibration:** Post-hoc isotonic regressor per horizon. sklearn's `CalibratedClassifierCV(cv="prefit")` was removed in newer sklearn (v1.5+); we hand-roll: fit isotonic on 20% calibration slice, apply to all three class probabilities. Stores `{horizon}_isotonic.pkl`.

**Conformal (Split):** ~40 LOC hand-rolled. Hold out 20% of training fold as conformal calibration set. Compute non-conformity `s = 1 - p̂(true_class)` for each row. Threshold `q = quantile(s, 1 - α)` for α=0.10 (90% coverage). At predict time, prediction set = {c : 1 - p̂(c) ≤ q}.

**Why:** Isotonic is simplest post-hoc calibrator and works best on LightGBM soft-label outputs. Conformal guarantees 90% coverage without retraining. Hand-rolled splits keep deps small; drop-in swap to MAPIE in v1.5 is trivial.

**Reference:** `ml/trainer.py` (§4.4 of spec).

### 3. Walk-Forward Cross-Validation (60/20/20 Within-Fold Split)

**Outer loop:** 5 folds, each trains on `[t0, t_i]`, validates on `[t_i, t_i+30d]`. Final fold's training window = full matrix; promotion uses out-of-fold metrics.

**Inner split (per fold):** Fixed-time, no-shuffle 60/20/20:
- 60%: train booster
- 20%: calibrate isotonic regressor (the booster never sees this)
- 20%: calibrate conformal threshold (both booster and isotonic are frozen)

Time order preserved. Oldest data trains; newest data conformal-calibrates. No data leakage.

**Why:** Walk-forward respects temporal structure of time series. The 60/20/20 split within each fold ensures isotonic and conformal calibrators work on data the booster never saw (coverage guarantees need it). Time-ordered, no shuffling.

**Reference:** `ml/trainer.py` (§4.4).

### 4. Cold-Start Contract (< 100 Resolved Outcomes per Horizon)

If `count(resolved signal_outcomes) < 100` for a horizon:
```python
{
  "horizon_days": h,
  "p_bull": 0.33, "p_base": 0.34, "p_bear": 0.33,
  "predicted_class": "cold_start",
  "conformal_set": ["bull", "base", "bear"],
  "shap_top": [],
  "model_version": "cold_start",
  "feature_version": <current>
}
```

**Why:** Downstream consumers (analyze badge, Synthesis Layer) never get `None`—contract always returns shape. Equal probabilities (empirical class prior) is honest about ignorance. Downstream routing can detect `model_version="cold_start"` and act (e.g. default to momentum or regime).

**Reference:** `ml/predictor.py` (§4.6 of spec).

### 5. Stale-Model Guard (Feature Version Mismatch Rejection)

Predictor loads model bundle only if `manifest.feature_version == FEATURE_VERSION` constant. If mismatch, refuses load, logs `model_stale; retrain required`, falls back to cold-start contract.

**Why:** Prevents silent mismatch: someone reorders columns in signal_features without touching the model → predictions degrade silently. Explicit mismatch detection + re-train forced.

**Reference:** `ml/predictor.py`, `FEATURE_VERSION` constant (§4.5).

### 6. Atomic Symlink Promotion Guarded by Mean Brier ≤ Prior + 0.01

Only promote `data/ml/current` → new artifact dir if `mean(Brier across horizons) <= prior_mean_Brier + 0.01`. Symlink is atomic; bad bundle never overwrites good one.

**Why:** Silent regression is the worst failure mode (ship bad model, no alert). +0.01 tolerance allows minor noise; strict inequality guards against neutral drift. Atomic symlink ensures no partially-written bundle on disk.

**Reference:** `ml/trainer.py` (§4.4), `eval.json` stores per-horizon Brier.

### 7. Model Versioning Locks Feature Version + UTC Timestamp

Format: `lgb_v1_<feature_version>_<UTC YYYYMMDDTHHMMSS>`.

Example: `lgb_v1_reflexivity_v1_vader_decay_0.5_20260508T030000`.

**Why:** `feature_version` in the name closes silent column-reordering risk. UTC timestamp is sortable and immutable. Manifest authoritatively records `feature_columns` order; manifest + model_version together guarantee bit-identical replay.

**Reference:** `ml/trainer.py` (§4.4), migration 008 `signal_predictions.model_version` VARCHAR.

## Eight Additional Design Details

| Aspect | Decision |
|---|---|
| Data contract | Migration 008 `signal_predictions` table: (signal_id, horizon_days, model_version) PK. Multiple versions per (signal, horizon) OK (v1 + v2 A/B comparison). Conformal set comma-joined; SHAP top-5 as JSON. |
| SHAP | Top-5 features per prediction, signed contribution. Computed via LightGBM SHAP API. |
| Scaler | Single z-norm scaler per model; fit on training 60% of each fold; stored as `scaler.pkl`. Applied uniformly across horizons. |
| Manifest | Records `feature_version`, `train_window_start/end`, `n_samples`, `n_dropped_for_missing`, LightGBM hyperparams, `random_state`, class-boundary-σ-used. Deterministic across runs. |
| Baseline | Class-prior probabilities per fold. Eval compares model Brier vs. prior Brier to show lift. |
| Artifact retention | Old bundles kept 6 weeks; separate cron garbage-collects. Protects rollback. |
| Prediction latency | Real-time: `predictor.predict(conn, signal_id)` synchronous, < 1s (cached scaler, booster, isotonic, conformal thresholds in memory). Batch: nightly `finterminal ml backfill --since=yesterday`. |
| Ingestion to decision | `analyze_flow.py` inline: after `compute_for_signal`, calls `predictor.predict()`; result inlined in analyst badge. |

## What We Deferred (v1.5+)

- **Path-signature features** (interface stubbed in dataset.py; v1.5 plugs in via `extra_feature_builders`).
- **Triple-barrier labelling** (vol-scaled ±1σ is v1; triple barrier in v1.5).
- **Combinatorial Purged CV** (walk-forward is v1; CPCV in v1.5).
- **Fractional differentiation** (lands when backtest engine ships).
- **`/predict` REPL command** (v1 surfaces predictions inline in `/analyze`; standalone in v1.5).

## Test Coverage (318 → 365 tests)

| Test suite | What it proves |
|---|---|
| `test_labels.py` | Vol-scaled bands; unresolved outcomes excluded; 252d window; empty → empty |
| `test_dataset.py` | Zero missing rows; honors `until_ts`; honors `feature_version` filter; rejects on missing columns |
| `test_normaliser.py` | Round-trip identity; transform with stored scaler; `normalized=true` flips ONLY for training set |
| `test_trainer.py` | Walk-forward time order; class-prior baseline; Brier per horizon; promotion guard rejects regression; manifest deterministic |
| `test_predictor.py` | Cold-start returns class-prior; real prediction sums ~1; SHAP top-5 returned; stale-model mismatch fires |
| `test_signal_predictions.py` | Migration 008 applies; PK enforced; round-trip via batch_backfill |
| `test_analyze_inline.py` | `/analyze` includes 3-prob badge; respects cold-start |

**Cadence:** Sunday 03:00 IST train; real-time `/analyze` predict; nightly backfill.

## Linking

- Implements [[ADR-006 Model Abstraction in Phase 1]] routing
- Depends on [[ADR-019 Feature Store as the Bridge from Signals to Models]] (20 features)
- Depends on [[ADR-020 Feature Versioning and Freeze-on-Write for Safe Model Evolution]] (feature_version guard)
- Related: [[05 - Build Log/2026-05-01 — Sub-project 5 ML Pipeline v1]] (ship record)
