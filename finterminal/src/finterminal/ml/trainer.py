"""ml/trainer.py — LightGBM trainer with isotonic calibration and split-conformal.

Public surface:
    train_all(conn, horizons, feature_version, ...) -> ModelBundle

Spec §4.4 + §7 + §8: time-ordered 60/20/20 split, atomic symlink promotion.
"""
from __future__ import annotations

import json
import logging
import math
import os
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss

from .dataset import build_matrix, MatrixMeta
from .normaliser import fit_transform, transform, Scaler

logger = logging.getLogger(__name__)

ARTIFACTS_ROOT = Path("data/ml/artifacts")
CURRENT_SYMLINK = Path("data/ml/current")
PROMOTION_BRIER_TOLERANCE = 0.01
CONFORMAL_ALPHA = 0.10
RANDOM_STATE = 42
SPLIT_TRAIN = 0.60
SPLIT_ISOTONIC = 0.20
COLD_START_MIN_ROWS = 100

_DEFAULT_LGBM_PARAMS: dict[str, Any] = {
    "objective": "multiclass", "num_class": 3, "metric": "multi_logloss",
    "n_estimators": 200, "learning_rate": 0.05, "max_depth": -1,
    "num_leaves": 31, "min_data_in_leaf": 20, "verbose": -1,
}


@dataclass
class HorizonArtifact:
    booster_path: str | None
    isotonic_path: str | None
    conformal_path: str | None
    brier: float
    brier_class_prior: float
    hit_rate: float
    hit_rate_class_prior: float


@dataclass
class ModelBundle:
    model_version: str
    feature_version: str
    artifact_dir: str
    per_horizon: dict[int, HorizonArtifact]


def train_all(
    conn: duckdb.DuckDBPyConnection,
    horizons: list[int],
    feature_version: str,
    artifacts_root: Path = ARTIFACTS_ROOT,
    current_symlink: Path = CURRENT_SYMLINK,
    random_state: int = RANDOM_STATE,
    now: datetime | None = None,
    lgbm_params: dict[str, Any] | None = None,
) -> ModelBundle:
    """Train one model per horizon; atomically promote if Brier does not regress."""
    now_utc = now if now is not None else datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    model_version = f"lgb_v1_{feature_version}_{now_utc.strftime('%Y%m%dT%H%M%S')}"
    artifact_dir = Path(artifacts_root) / model_version
    artifact_dir.mkdir(parents=True, exist_ok=True)

    params = {**_DEFAULT_LGBM_PARAMS, **(lgbm_params or {})}

    per_horizon: dict[int, HorizonArtifact] = {}
    slice_counts: dict[int, tuple] = {}
    min_ts_all: list[datetime] = []
    scaler_saved = False

    for h in horizons:
        art, scaler, min_ts, sc = _train_horizon(
            conn, h, feature_version, now_utc, artifact_dir, random_state, params
        )
        per_horizon[h] = art
        slice_counts[h] = sc
        if scaler is not None and not scaler_saved:
            with open(artifact_dir / "scaler.pkl", "wb") as f:
                pickle.dump(scaler, f)
            scaler_saved = True
        if min_ts is not None:
            min_ts_all.append(min_ts)

    if not scaler_saved:
        with open(artifact_dir / "scaler.pkl", "wb") as f:
            pickle.dump(None, f)

    non_nan = [a.brier for a in per_horizon.values() if not math.isnan(a.brier)]
    new_mean = float(np.mean(non_nan)) if non_nan else float("nan")
    prior_mean = _read_prior_mean_brier(current_symlink)
    promoted = not math.isnan(new_mean) and new_mean <= prior_mean + PROMOTION_BRIER_TOLERANCE
    if promoted:
        _atomic_symlink(current_symlink, artifact_dir)

    def _nan_to_none(v: float) -> float | None:
        return None if math.isnan(v) else v

    eval_data: dict[str, Any] = {"promoted": promoted}
    for h, art in per_horizon.items():
        eval_data[str(h)] = {
            "brier": _nan_to_none(art.brier),
            "brier_class_prior": _nan_to_none(art.brier_class_prior),
            "hit_rate": _nan_to_none(art.hit_rate),
            "hit_rate_class_prior": _nan_to_none(art.hit_rate_class_prior),
        }
    with open(artifact_dir / "eval.json", "w") as f:
        json.dump(eval_data, f, indent=2)

    manifest: dict[str, Any] = {
        "model_version": model_version,
        "feature_version": feature_version,
        "train_window_start": min(min_ts_all).isoformat() if min_ts_all else None,
        "train_window_end": now_utc.isoformat(),
        "random_state": random_state,
        "promoted": promoted,
        "hyperparams": params,
        "per_horizon": {},
    }
    for h, art in per_horizon.items():
        n_tr, n_is, n_cf = slice_counts.get(h, (None, None, None))
        manifest["per_horizon"][str(h)] = {
            "cold_start": art.booster_path is None,
            "brier": _nan_to_none(art.brier),
            "brier_class_prior": _nan_to_none(art.brier_class_prior),
            "hit_rate": _nan_to_none(art.hit_rate),
            "hit_rate_class_prior": _nan_to_none(art.hit_rate_class_prior),
            "n_train": n_tr, "n_iso": n_is, "n_conf": n_cf,
        }
    with open(artifact_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    return ModelBundle(model_version, feature_version, str(artifact_dir), per_horizon)


def _train_horizon(
    conn: duckdb.DuckDBPyConnection,
    h: int,
    feature_version: str,
    until_ts: datetime,
    artifact_dir: Path,
    random_state: int,
    params: dict[str, Any],
) -> tuple[HorizonArtifact, Scaler | None, datetime | None, tuple]:
    X, y, meta = build_matrix(conn, h, feature_version, until_ts=until_ts)

    if len(y) < COLD_START_MIN_ROWS:
        logger.info("horizon=%dd: %d rows < %d — cold-start skip", h, len(y), COLD_START_MIN_ROWS)
        nan = float("nan")
        return (
            HorizonArtifact(None, None, None, nan, nan, nan, nan),
            None, None, (None, None, None),
        )

    # Time-ordered 60/20/20 split
    ts_arr = meta.ts_emitted
    sort_idx = sorted(range(len(ts_arr)), key=lambda i: ts_arr[i])
    n = len(sort_idx)
    n_train = int(n * SPLIT_TRAIN)
    n_iso = int(n * SPLIT_ISOTONIC)
    n_conf = n - n_train - n_iso

    idx_train = sort_idx[:n_train]
    idx_iso   = sort_idx[n_train:n_train + n_iso]
    idx_conf  = sort_idx[n_train + n_iso:]

    X_train, y_train = X[idx_train], y[idx_train]
    X_iso,   y_iso   = X[idx_iso],   y[idx_iso]
    X_conf,  y_conf  = X[idx_conf],  y[idx_conf]

    # Z-norm: fit on training slice only
    train_meta = MatrixMeta(
        signal_ids=[meta.signal_ids[i] for i in idx_train],
        feature_columns=meta.feature_columns,
        feature_version=feature_version,
        horizon_days=h,
        until_ts=until_ts,
        n_rows=n_train,
        n_dropped_for_missing=0,
        ts_emitted=[ts_arr[i] for i in idx_train],
    )
    X_train_z, scaler = fit_transform(conn, X_train, train_meta)
    X_iso_z  = transform(X_iso,  scaler)
    X_conf_z = transform(X_conf, scaler)

    # Fit LGBMClassifier
    rs = params.get("random_state", random_state)
    fit_params = {k: v for k, v in params.items() if k != "random_state"}
    base = lgb.LGBMClassifier(random_state=rs, **fit_params)
    base.fit(X_train_z, y_train)
    booster_path = str(artifact_dir / f"{h}d.lgb")
    base.booster_.save_model(booster_path)

    # Per-class isotonic calibration (always 3 outputs regardless of y_iso classes)
    raw_iso = base.predict_proba(X_iso_z)  # (n_iso, 3) always
    n_cls = 3
    iso_regs: list[IsotonicRegression | None] = []
    for c in range(n_cls):
        y_bin = (y_iso == c).astype(float)
        if y_bin.sum() == 0:
            iso_regs.append(None)
        else:
            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(raw_iso[:, c], y_bin)
            iso_regs.append(ir)
    isotonic_path = str(artifact_dir / f"{h}d_isotonic.pkl")
    with open(isotonic_path, "wb") as f:
        pickle.dump((base, iso_regs), f)

    def _calibrate(X_z: np.ndarray) -> np.ndarray:
        raw = base.predict_proba(X_z)
        cal = np.empty_like(raw)
        for c in range(n_cls):
            cal[:, c] = iso_regs[c].predict(raw[:, c]) if iso_regs[c] else raw[:, c]
        row_sums = cal.sum(axis=1, keepdims=True)
        return cal / np.where(row_sums == 0, 1.0, row_sums)

    # Split-conformal (spec §7): s_i = 1 - p_hat(true_class); q = quantile(s, 1-alpha)
    proba_conf = _calibrate(X_conf_z)
    nc = np.array([1.0 - proba_conf[i, int(y_conf[i])] for i in range(len(y_conf))])
    q = float(np.quantile(nc, 1 - CONFORMAL_ALPHA))
    conformal_path = str(artifact_dir / f"{h}d_conformal.pkl")
    with open(conformal_path, "wb") as f:
        pickle.dump(q, f)

    # Eval metrics on conformal slice (never seen by booster or isotonic)
    brier = _mean_ovr_brier(proba_conf, y_conf)
    class_prior = _class_prior(y_train)
    brier_base = _mean_ovr_brier(np.tile(class_prior, (len(y_conf), 1)), y_conf)
    preds = np.argmax(proba_conf, axis=1)
    hit_rate = float(np.mean(preds == y_conf))
    hit_rate_base = float(np.mean(y_conf == int(np.argmax(class_prior))))

    min_ts = min(ts_arr[i] for i in idx_train)
    art = HorizonArtifact(booster_path, isotonic_path, conformal_path,
                          brier, brier_base, hit_rate, hit_rate_base)
    return art, scaler, min_ts, (n_train, n_iso, n_conf)


def _mean_ovr_brier(proba: np.ndarray, y: np.ndarray) -> float:
    n_cls = proba.shape[1]
    return sum(brier_score_loss((y == c).astype(float), proba[:, c]) for c in range(n_cls)) / n_cls


def _class_prior(y_train: np.ndarray) -> np.ndarray:
    counts = np.bincount(y_train.astype(int), minlength=3).astype(float)
    total = counts.sum()
    return counts / total if total > 0 else np.full(3, 1.0 / 3)


def _read_prior_mean_brier(current_symlink: Path) -> float:
    try:
        if not current_symlink.exists():
            return float("inf")
        target = Path(os.readlink(str(current_symlink)))
        if not target.is_absolute():
            target = current_symlink.parent / target
        eval_path = target / "eval.json"
        if not eval_path.exists():
            return float("inf")
        eval_data = json.loads(eval_path.read_text())
        briers = [float(v["brier"]) for k, v in eval_data.items()
                  if isinstance(v, dict) and v.get("brier") is not None]
        return float(np.mean(briers)) if briers else float("inf")
    except Exception as exc:
        logger.warning("Could not read prior eval.json: %s", exc)
        return float("inf")


def _atomic_symlink(symlink_path: Path, target: Path) -> None:
    """Atomically replace symlink via temp path + os.replace (no race window)."""
    tmp = symlink_path.with_suffix(".tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    os.symlink(str(target), str(tmp))
    os.replace(str(tmp), str(symlink_path))
