# Sub-project #5 — ML Pipeline v1 — Design Spec

**Date:** 2026-05-01
**Status:** Approved (brainstorm complete; awaiting user spec sign-off before plan-writing)
**Owner:** Ajinkya Wagh
**Predecessors:** #1 Outcomes Ledger · #2 Feature Store · #3 Quality Engine v1 · #4 Reflexivity Engine v1
**Successors:** #6 mgmt_claims engine · v1.5 path-signature features + triple-barrier labelling + CPCV · Phase 3 Synthesis Layer (Scenario Engine consumes calibrated probabilities)
**Related ADRs:** [[ADR-006 Model Abstraction in Phase 1]] · [[ADR-019 Feature Store as the Bridge from Signals to Models]] · [[ADR-020 Feature Versioning and Freeze-on-Write]]

---

## 1. Goal

Train and serve calibrated **bull / base / bear** probability distributions per (signal, horizon) using the 20-feature store built by sub-projects #1–#4. v1 closes the feedback loop: features → model → predictions → outcomes → re-train.

The outputs are the substrate the Phase 3 Synthesis Layer (Scenario Engine, Signal Weighter, Calibration Loop) will consume. v1 ships *predictions*; v1.5+ ships the synthesis.

---

## 2. Non-goals (explicit)

- Path-signature features (interface stubbed; implementation in v1.5).
- Triple-barrier labelling (vol-scaled ±1σ in v1; triple-barrier in v1.5).
- Combinatorial Purged CV (walk-forward in v1; CPCV in v1.5).
- Fractional differentiation (lands when a backtest engine does).
- DeepSeek-R1 / Qwen routing for ML (separate model-registry concern).
- `/predict TCS` REPL command (v1 surfaces predictions inline in `/analyze`; standalone command in v1.5).
- Backtest harness — predictions ledger sets it up but v1 does not simulate trades.
- Position sizing / Hierarchical Risk Parity (parked in `BACKLOG.md` for a future portfolio-overlay sub-project).

---

## 3. Architecture

```
news_stories ─┐
prices_eod   ─┤        signals ──► compute_for_signal ──► signal_features
nifty/regime ─┘                                                 │
                                                                ▼
signal_outcomes ◄── outcomes_resolver (existing)        ml/labels.py     ◄── 252d nifty
                            │                                   │
                            └────────► ml/dataset.py  ◄─────────┘
                                          │  (joined matrix, version-tagged, until_ts honest)
                                          ▼
                                   ml/normaliser.py  (z-norm; sets normalized=true ONLY for matrix rows)
                                          │
                                          ▼
                                    ml/trainer.py  (LightGBM × {7,30,90}d × walk-forward)
                                          │
                                          ▼
                                    artifacts/{model_version}/{horizon}.lgb
                                          │
                                          ▼
                                  ml/predictor.py  ──► signal_predictions  (3 probs + conformal set + SHAP top-5)
                                          │
                                          ▼
                              analyze_flow.py (inline badge in /analyze)
```

Five flat modules under `finterminal/src/finterminal/ml/`. Each ≤200 lines, no cross-imports beyond the obvious data-flow direction.

---

## 4. Components

### 4.1 `ml/labels.py`
- **Purpose.** Vol-scaled ±1σ bull/base/bear labelling using `signal_outcomes.ret_pct_vs_nifty` and rolling 252d Nifty σ at the resolution date.
- **Public surface.** `label_outcomes(conn, horizon_days: int) -> pl.DataFrame[(signal_id, label, sigma_used)]`
- **Rule.**
  - `bull` if `ret_pct_vs_nifty > +sigma`
  - `bear` if `ret_pct_vs_nifty < -sigma`
  - `base` otherwise
  - `sigma` = stdev of daily Nifty log returns over the 252 trading days preceding `signal.ts_emitted`.
- **Excludes.** Unresolved outcomes (`resolved_at IS NULL`).

### 4.2 `ml/dataset.py`
- **Purpose.** Build a leakage-free training matrix.
- **Public surface.**
  ```python
  build_matrix(
      conn,
      horizon_days: int,
      feature_version: str,
      until_ts: datetime,
      extra_feature_builders: list[Callable[[Conn, str], dict]] = [],
  ) -> tuple[np.ndarray, np.ndarray, MatrixMeta]
  ```
- **Joins.** `signal_features` × `signals` (regime cols inline) × `labels`.
- **Filters.**
  - `signals.ts_emitted + horizon_days <= until_ts` (no peeking — only resolved horizons in the cut).
  - `signal_features.feature_version = ?` (no mixing model generations).
  - `is_missing = FALSE` for all 20 feature columns (rows with any missing feature are dropped; alternative imputation deferred to v1.5).
- **`extra_feature_builders` hook.** v1 ships empty. v1.5 path-sig drops in here without trainer changes.
- **`MatrixMeta`.** Carries `signal_ids`, `feature_columns`, `feature_version`, `until_ts`, `n_rows`, `n_dropped_for_missing`.

### 4.3 `ml/normaliser.py`
- **Purpose.** Z-normalisation activator (the deferred piece from #4).
- **Public surface.** `fit_transform(matrix, meta) -> (X_z, scaler)`, `transform(X, scaler) -> X_z`.
- **Algorithm.** Per-feature mean / std on the training cut only. Stores `(mean, std)` per feature column.
- **Write-back invariant.** Sets `normalized=TRUE` on `signal_features` rows in `meta.signal_ids` ONLY. Never touches rows outside the training cut. Re-running on a later cut inserts new rows (freeze rule from #4 protects prior).
  - Implemented as `UPDATE signal_features SET normalized=TRUE WHERE signal_id IN (?,?,...) AND feature_name IN (...)`.

### 4.4 `ml/trainer.py`
- **Purpose.** Train one calibrated multiclass model per horizon with walk-forward CV.
- **Public surface.** `train_all(conn, horizons: list[int], feature_version: str) -> ModelBundle`.
- **Per-horizon procedure.**
  1. `build_matrix(conn, h, feature_version, until_ts=now())`.
  2. Walk-forward split: 5 folds, each fold trains on `[t0, t_i]`, validates on `[t_i, t_i+30d]`. Final fold's training window = full matrix; promotion uses out-of-fold metrics.
  3. Within each fold's training window, do a fixed-time **60 / 20 / 20 split**: oldest 60% trains the booster, next 20% calibrates the isotonic regressor, newest 20% calibrates the conformal threshold. The three splits are *disjoint* and time-ordered (no shuffling — the conformal slice must be on data the calibrator never saw or coverage guarantees are lost).
  4. Fit `LGBMClassifier(objective="multiclass", num_class=3, metric="multi_logloss", random_state=42)` on the 60% slice.
  5. Wrap with `CalibratedClassifierCV(method="isotonic", cv="prefit")` on the 20% isotonic slice.
  6. Compute split-conformal non-conformity scores `s = 1 - p̂(true_class)` on the 20% conformal slice using the calibrated classifier's outputs. Store the (1−α) quantile threshold for α=0.10 (90% coverage prediction sets).
- **Baseline tracked.** Class-prior probabilities (just the empirical class frequencies) for every fold, so we can show "model lift over the prior" in `eval.json`.
- **Outputs.**
  - One LightGBM booster per horizon: `{horizon}.lgb`.
  - One isotonic calibrator per horizon: `{horizon}_isotonic.pkl`.
  - One conformal threshold per horizon: `{horizon}_conformal.pkl`.
  - One scaler: `scaler.pkl`.
  - `eval.json` (Brier per horizon per class, reliability bins, hit-rate vs class prior, fold-by-fold detail).
  - `manifest.json` (`feature_version`, `train_window_start`, `train_window_end`, `n_samples`, `n_dropped_for_missing`, lightgbm hyperparams, random_state, class-boundary-σ-used).
- **Promotion.** Atomic symlink swap of `data/ml/current` → new artifact dir, only if `mean(Brier across horizons) <= prior_mean_Brier + 0.01`. Old artifact dirs kept for 6 weeks then garbage-collected by a separate cron.

### 4.5 `ml/predictor.py`
- **Purpose.** Serve predictions in real-time and in nightly batch.
- **Public surface.**
  ```python
  predict(conn, signal_id: str) -> PredictionCell
  batch_backfill(conn, since_ts: datetime) -> int  # rows written
  ```
- **`PredictionCell` shape.**
  ```python
  {
    "horizon_days":    int,
    "p_bull":          float,
    "p_base":          float,
    "p_bear":          float,
    "predicted_class": str,           # 'bull' | 'base' | 'bear' | 'cold_start'
    "conformal_set":   list[str],     # e.g. ['bull','base'] for 90% coverage
    "shap_top":        list[tuple[str, float]],   # top-5 (feature_name, signed_contribution)
    "model_version":   str,
    "feature_version": str,
  }
  ```
- **Serialization to `signal_predictions`.** `conformal_set` is comma-joined for the VARCHAR column (`",".join(sorted(set))` so order is canonical). `shap_top` is JSON-serialized as a list of `[feature_name, signed_contribution]` pairs. Round-trip is symmetric on read.
- **Real-time hook.** `analyze_flow.py` calls `predictor.predict(conn, signal_id)` after `compute_for_signal`. Result inlined in the analyst output.
- **Nightly batch.** Cron-driven `finterminal ml backfill --since=yesterday` writes predictions for any new signals emitted that day (catches signals from non-`/analyze` paths).
- **Stale-model guard.** Refuses to load a bundle whose `manifest.feature_version` doesn't match the current `FEATURE_VERSION` constant. Logs `model_stale; retrain required` and falls back to cold-start contract.

### 4.6 Cold-start contract
If `count(resolved signal_outcomes) < 100` for a horizon, `predictor.predict` returns:
```python
{"horizon_days": h,
 "p_bull": 0.33, "p_base": 0.34, "p_bear": 0.33,
 "predicted_class": "cold_start",
 "conformal_set": ["bull", "base", "bear"],
 "shap_top": [],
 "model_version": "cold_start",
 "feature_version": <current>}
```
Downstream consumers (analyze badge, future Synthesis Layer) get a contract-compatible response, never a `None` — same defensive pattern as `is_missing` in feature cells.

---

## 5. Data contracts

### 5.1 Migration 008 — `signal_predictions` table

```sql
-- Sub-project #5: ML pipeline v1.
-- Symmetric with signal_outcomes; one row per (signal, horizon, model_version).
-- Multiple model_versions per (signal, horizon) is intentional — lets v1 and
-- v2 predictions live side-by-side for apples-to-apples model comparison.
CREATE TABLE IF NOT EXISTS signal_predictions (
  signal_id        VARCHAR NOT NULL,
  horizon_days     INTEGER NOT NULL,
  p_bull           DOUBLE  NOT NULL,
  p_base           DOUBLE  NOT NULL,
  p_bear           DOUBLE  NOT NULL,
  predicted_class  VARCHAR NOT NULL,        -- 'bull' | 'base' | 'bear' | 'cold_start'
  conformal_set    VARCHAR,                  -- comma-joined; e.g. 'bull,base'
  shap_top         JSON,                     -- [["feature", 0.13], ...] top-5 by |abs|
  model_version    VARCHAR NOT NULL,
  feature_version  VARCHAR NOT NULL,
  predicted_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (signal_id, horizon_days, model_version)
);
CREATE INDEX IF NOT EXISTS signal_predictions_ts_idx
  ON signal_predictions(predicted_at);
CREATE INDEX IF NOT EXISTS signal_predictions_lookup_idx
  ON signal_predictions(signal_id, horizon_days);
```

### 5.2 Model-version string format

```
lgb_v1_<feature_version>_<utc_ts>
```
where `utc_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")`.

Example: `lgb_v1_reflexivity_v1_vader_decay_0.5_20260508T030000`

### 5.3 Artifact layout (gitignored)

```
finterminal/data/ml/
  artifacts/
    lgb_v1_reflexivity_v1_vader_decay_0.5_20260508T030000/
      7d.lgb,  7d_isotonic.pkl,  7d_conformal.pkl
      30d.lgb, 30d_isotonic.pkl, 30d_conformal.pkl
      90d.lgb, 90d_isotonic.pkl, 90d_conformal.pkl
      scaler.pkl
      eval.json
      manifest.json
  current -> artifacts/lgb_v1_..._20260508T030000     # symlink
```

`finterminal/data/` is already gitignored (per the absorb commit). No extra ignore rules needed.

---

## 6. Cadence

| When | What | How |
|---|---|---|
| Sunday 03:00 IST, weekly | Train all horizons, evaluate, promote if non-regressive | `finterminal ml train` (cron-friendly CLI) |
| Real-time, on every signal emit | Predict for the new signal, write to `signal_predictions`, surface in `/analyze` output | `predictor.predict()` invoked from `analyze_flow.py` |
| Nightly, 23:30 IST | Backfill predictions for signals emitted that day outside `/analyze` paths | `finterminal ml backfill --since=yesterday` |

---

## 7. Conformal prediction — chosen approach

**Hand-rolled split-conformal**, ~40 LOC. Algorithm:
1. Hold out 20% of the training fold as the conformal calibration set.
2. For each calibration row, compute the non-conformity score `s = 1 - p̂(true_class)` from the calibrated classifier.
3. Pick `q = quantile(s, 1 - α)` for `α = 0.10` (90% coverage). Store `q` per horizon.
4. At predict time, the prediction set is `{c : 1 - p̂(c) <= q}` — i.e. all classes whose probability exceeds `1 - q`.

**Why not MAPIE.** MAPIE adds a dependency that gives capability we don't use in v1 (Mondrian, adaptive, regression variants). Hand-rolled keeps deps small and the logic auditable. Drop-in to MAPIE in v1.5 without touching `predictor.py` is trivial — same `(quantile, threshold)` shape.

---

## 8. Errors, determinism, drift

| Failure mode | Defence |
|---|---|
| Future-data leakage | `until_ts` cut in `dataset.build_matrix`; no row whose `ts_emitted + horizon_days > until_ts` is included |
| Mixed model generations | `feature_version` filter in `build_matrix`; predictor refuses stale bundle |
| Silent regression on retrain | Promotion guard: new `mean(Brier)` must be ≤ `prior + 0.01` to swap symlink |
| Non-deterministic training | `random_state=42` on every estimator; `manifest.json` records seed + window + hyperparams |
| Cold start | Class-prior cell with `model_version="cold_start"`; never `None` |
| Artifact corruption | Old artifacts retained 6 weeks; symlink is atomic — bad bundle never overwrites good one |

---

## 9. Stack additions to `pyproject.toml`

```
"lightgbm>=4.3.0",
"scikit-learn>=1.5.0",
"shap>=0.45.0",
"polars>=1.0.0",          # for dataset.py — handles join/filter at scale better than pandas
```

`numpy` and `scipy` are already in deps.

---

## 10. Testing strategy

| Test file | What it proves |
|---|---|
| `test_labels.py` | Vol-scaled bands compute correctly; unresolved outcomes excluded; sigma uses 252d window; empty input → empty output |
| `test_dataset.py` | Matrix has zero `is_missing=True` rows; honors `until_ts`; honors `feature_version` filter; rejects on missing feature columns |
| `test_normaliser.py` | Round-trip identity; transform with stored scaler matches fit_transform output; `normalized=true` flips ONLY for `meta.signal_ids` (leakage guard) |
| `test_trainer.py` | Walk-forward respects time order; class-prior baseline computed; eval.json has Brier per horizon; promotion guard rejects regression; manifest is deterministic across runs |
| `test_predictor.py` | Cold-start path returns class-prior cell; real prediction has 3 probs summing to ~1 (within float tolerance); SHAP top-5 returned and signed; stale-model error fires when feature_version mismatches |
| `test_signal_predictions.py` | Migration 008 applies; `(signal_id, horizon, model_version)` PK enforced; round-trip via `predictor.batch_backfill` |
| `test_analyze_inline.py` | `/analyze` output includes the 3-prob badge; respects cold-start state |

Target: **~30 new tests**, suite goes from **318 → ~348**.

---

## 11. Vault hooks (must update on ship per `docs/CLAUDE.md` protocol)

- New ADR: `02 - Decisions/ADR-021 — ML Pipeline Architecture (Walk-Forward + Calibration + Conformal)` — captures the multi-horizon + LightGBM + isotonic + split-conformal + cold-start choices.
- New code map: `04 - Code Map/ml — pipeline.md` — overview of the 5 modules.
- New build log: `05 - Build Log/2026-05-XX — Sub-project 5 ML Pipeline v1.md` — what shipped, test count delta, follow-ups.
- Update `Index.md` — Phase 2 status: `#5 SHIPPED (~348 tests)`.

---

## 12. Open questions deferred to plan / implementation phase

- Hyperparameter search strategy — fixed defaults vs Optuna. v1 leans fixed (LightGBM defaults + early stopping); revisit if eval shows under-fit.
- SHAP background-set size — 100 rows random sample of training data is the LightGBM-recommended default; lock this in implementation.
- Exact column list for the regime features pulled from `signals.regime_*` — confirmed in implementation step.
- Polars vs pandas — locked Polars in §9; revisit if a sub-agent finds a sklearn / shap interop friction.
