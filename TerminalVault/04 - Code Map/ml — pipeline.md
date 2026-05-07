# ML — Pipeline

Five compute modules under `finterminal/src/finterminal/ml/` form the core loop: signals + features → labels + dataset → normalisation → training → predictions → synthesis. Each module ≤200 lines, no cross-imports except data-flow direction.

## Architecture Flow

```
signals + signal_features ──► ml/labels.py    ──► bull/base/bear labels (vol-scaled ±1σ)
                                ↓
                           ml/dataset.py      ──► joined matrix (signal_id, 20 features, label)
                                ↓
                           ml/normaliser.py   ──► z-norm scaler
                                ↓
                           ml/trainer.py      ──► LightGBM booster + isotonic + conformal
                                ↓
                           ml/predictor.py    ──► p_bull, p_base, p_bear + conformal_set + SHAP top-5
                                ↓
                           analyze_flow.py    ──► inline badge in /analyze
```

## Modules

| Module | Role | Spec section | Source path |
|---|---|---|---|
| labels | Vol-scaled ±1σ bull/base/bear labelling; 252d rolling σ | 4.1 | `src/finterminal/ml/labels.py` |
| dataset | Leakage-free training matrix; join features × outcomes; no-peek `until_ts` filter | 4.2 | `src/finterminal/ml/dataset.py` |
| normaliser | Z-norm scaler; freeze-on-write `normalized` flag | 4.3 | `src/finterminal/ml/normaliser.py` |
| trainer | Walk-forward CV; LightGBM + isotonic + split-conformal; eval.json + manifest | 4.4 | `src/finterminal/ml/trainer.py` |
| predictor | Real-time + nightly batch; cold-start contract; stale-model guard | 4.5 | `src/finterminal/ml/predictor.py` |

## Dependencies

- **Upstream:** [[features — store (freeze-on-write)]] (signal_features table with feature_version + normalized); [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]] (20-feature contract); [[02 - Decisions/ADR-020 — Feature Versioning and Freeze-on-Write for Safe Model Evolution]] (feature_version immutability)

- **Downstream:** `analyze_flow.py` (inline /analyze badge); Phase 3 Synthesis Layer (consumes p_bull, p_base, p_bear distributions)

## Key Decisions

See [[02 - Decisions/ADR-021 — ML Pipeline Architecture (Walk-Forward + Calibration + Conformal)]] for:
- Multi-horizon (7d, 30d, 90d) with vol-scaled bands
- LightGBM + hand-rolled isotonic + split-conformal (90% coverage)
- Walk-forward 60/20/20 within-fold split
- Cold-start contract (< 100 outcomes)
- Stale-model guard (feature_version mismatch rejection)
- Atomic promotion guarded by Brier
- model_version format locks feature_version + UTC timestamp

## Tests

- `tests/ml/test_labels.py` — labelling logic
- `tests/ml/test_dataset.py` — matrix build, no leakage
- `tests/ml/test_normaliser.py` — scaler round-trip
- `tests/ml/test_trainer.py` — walk-forward, promotion guard
- `tests/ml/test_predictor.py` — cold-start, SHAP, stale-model
- `tests/ml/test_signal_predictions.py` — migration 008, PK
- `tests/ml/test_analyze_inline.py` — /analyze badge

**Test count:** 318 → 365 (47 new tests across 7 milestones + polish commit). See [[05 - Build Log/2026-05-01 — Sub-project 5 ML Pipeline v1]].

## Artifacts (gitignored)

```
finterminal/data/ml/
  artifacts/
    lgb_v1_reflexivity_v1_vader_decay_0.5_20260508T030000/
      {7d,30d,90d}.lgb
      {7d,30d,90d}_isotonic.pkl
      {7d,30d,90d}_conformal.pkl
      scaler.pkl
      eval.json
      manifest.json
  current → artifacts/lgb_v1_...      # atomic symlink
```

## CLI

- `finterminal ml train` — weekly (Sunday 03:00 IST); train all horizons, evaluate, promote if non-regressive
- `finterminal ml backfill --since=yesterday` — nightly 23:30 IST; writes predictions for new signals

## Related Notes

- [[02 - Decisions/ADR-006 Model Abstraction in Phase 1]] (routing)
- [[02 - Decisions/ADR-017 — Outcomes Ledger as the System's Moat]] (ground truth)
- [[03 - Phases/Phase 3 - US + Routing]] (Synthesis Layer consumes predictions)
