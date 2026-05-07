"""ml/predictor.py — calibrated prediction, cold-start, SHAP, signal_predictions writeback.

Public surface:
    predict(conn, signal_id, *, current_symlink) -> list[dict]
    batch_backfill(conn, since_ts, *, current_symlink) -> int

Spec §4.5 + §4.6 + §7 + §8.
"""
from __future__ import annotations

import json
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import shap

from .normaliser import Scaler, transform
from finterminal.features.compute_reflexivity import FEATURE_VERSION

logger = logging.getLogger(__name__)

CURRENT_SYMLINK = Path("data/ml/current")
COLD_START_THRESHOLD = 100          # min resolved outcomes per horizon
CONFORMAL_ALPHA = 0.10              # must match trainer's value
CLASS_NAMES = ["bear", "base", "bull"]  # idx → name (0/1/2)
_HORIZONS = [7, 30, 90]


# ---------------------------------------------------------------------------
# Cold-start contract (spec §4.6)
# ---------------------------------------------------------------------------

def _cold_start_cell(horizon_days: int, feature_version: str) -> dict:
    return {
        "horizon_days":    horizon_days,
        "p_bull":          1 / 3,
        "p_base":          1 / 3,
        "p_bear":          1 / 3,
        "predicted_class": "cold_start",
        "conformal_set":   ["bull", "base", "bear"],
        "shap_top":        [],
        "model_version":   "cold_start",
        "feature_version": feature_version,
    }


def _cold_start_all(feature_version: str) -> list[dict]:
    return [_cold_start_cell(h, feature_version) for h in _HORIZONS]


# ---------------------------------------------------------------------------
# Bundle loading
# ---------------------------------------------------------------------------

def _load_bundle(current_symlink: Path) -> tuple[dict, Path] | None:
    """Load manifest from current symlink. Returns (manifest, artifact_dir) or None."""
    try:
        if not current_symlink.exists():
            return None
        artifact_dir = current_symlink.resolve()
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        manifest = json.loads(manifest_path.read_text())
        return manifest, artifact_dir
    except Exception as exc:
        logger.warning("Failed to load bundle from %s: %s", current_symlink, exc)
        return None


def _load_horizon(artifact_dir: Path, h: int, scaler: Scaler | None
                  ) -> tuple[lgb.Booster, list, float, Scaler] | None:
    """Load booster, isotonic regs, conformal q, scaler for a horizon. Returns None if missing."""
    try:
        booster_path = artifact_dir / f"{h}d.lgb"
        isotonic_path = artifact_dir / f"{h}d_isotonic.pkl"
        conformal_path = artifact_dir / f"{h}d_conformal.pkl"
        if not (booster_path.exists() and isotonic_path.exists() and conformal_path.exists()):
            return None

        booster = lgb.Booster(model_file=str(booster_path))
        with open(isotonic_path, "rb") as f:
            _lgb_obj, iso_regs = pickle.load(f)   # (LGBMClassifier, [IR×3])
        with open(conformal_path, "rb") as f:
            q = pickle.load(f)

        if scaler is None:
            scaler_path = artifact_dir / "scaler.pkl"
            with open(scaler_path, "rb") as f:
                scaler = pickle.load(f)

        return booster, iso_regs, float(q), scaler
    except Exception as exc:
        logger.warning("Failed to load horizon=%dd artifacts: %s", h, exc)
        return None


# ---------------------------------------------------------------------------
# Feature row builder for a single signal
# ---------------------------------------------------------------------------

# Column order must match dataset.py's feature_columns definition.
from ..features.registry import V1_FEATURES  # noqa: E402

_V1_NAMES = [f.name for f in V1_FEATURES]
_REGIME_COLS = [
    "regime_nifty_close",
    "regime_nifty_pct_50d",
    "regime_india_vix",
    "regime_inr_usd",
    "regime_brent_usd",
    "regime_india_10y_yield",
]


def _build_feature_row(
    conn: duckdb.DuckDBPyConnection,
    signal_id: str,
    feature_version: str,
    feature_columns: list[str],
) -> np.ndarray | None:
    """Build a (1, n_features) float64 array for the given signal.

    Returns None if any V1 feature is is_missing=TRUE or absent.
    Column order: V1_NAMES + _REGIME_COLS + signal_type_id (matches dataset.py).
    """
    # Pull feature values from signal_features
    feat_rows = conn.execute(
        """
        SELECT feature_name, feature_value, is_missing
        FROM   signal_features
        WHERE  signal_id = ?
          AND  feature_version = ?
        """,
        [signal_id, feature_version],
    ).fetchall()

    feat_map: dict[str, tuple[float, bool]] = {}  # name → (value, is_missing)
    for fname, fval, is_missing in feat_rows:
        feat_map[fname] = (float(fval) if fval is not None else float("nan"), bool(is_missing))

    # Check all V1 features are present and non-missing
    for name in _V1_NAMES:
        if name not in feat_map:
            return None
        _, missing = feat_map[name]
        if missing:
            return None

    # Pull signal info (ts_emitted + regime cols + signal_type)
    sig_row = conn.execute(
        f"SELECT signal_type, {', '.join(_REGIME_COLS)} FROM signals WHERE signal_id = ?",
        [signal_id],
    ).fetchone()
    if sig_row is None:
        return None

    signal_type = sig_row[0]
    regime_vals = list(sig_row[1:])

    # Determine signal_type_id via the same sorted-name lookup used in dataset.py
    # We use the type_to_id from the trained model's feature_columns context.
    # For a single signal, we derive signal_type_id as 0 if unknown (best effort).
    # The column "signal_type_id" must map to an integer; use 0 as fallback.
    type_to_id = _infer_signal_type_id(conn, signal_type)

    # Build X row in the expected column order
    n_cols = len(feature_columns)
    X = np.empty((1, n_cols), dtype=np.float64)

    for col_i, col in enumerate(feature_columns):
        if col in _V1_NAMES:
            idx = feature_columns.index(col)
            val, _ = feat_map[col]
            X[0, idx] = val
        elif col in _REGIME_COLS:
            idx = feature_columns.index(col)
            r_idx = _REGIME_COLS.index(col)
            val = regime_vals[r_idx]
            X[0, idx] = float(val) if val is not None else float("nan")
        elif col == "signal_type_id":
            idx = feature_columns.index(col)
            X[0, idx] = float(type_to_id)

    return X


def _infer_signal_type_id(conn: duckdb.DuckDBPyConnection, signal_type: str) -> int:
    """Derive signal_type_id using sorted order of all distinct signal types in DB."""
    all_types = sorted(
        row[0] for row in conn.execute("SELECT DISTINCT signal_type FROM signals").fetchall()
    )
    type_to_id = {t: i for i, t in enumerate(all_types)}
    return type_to_id.get(signal_type, 0)


# ---------------------------------------------------------------------------
# Core predict
# ---------------------------------------------------------------------------

def predict(
    conn: duckdb.DuckDBPyConnection,
    signal_id: str,
    *,
    current_symlink: Path = CURRENT_SYMLINK,
) -> list[dict]:
    """Return one PredictionCell per horizon in {7, 30, 90}.

    Falls back to cold-start whenever: symlink missing, feature_version stale,
    horizon model files absent, or any input feature is missing.
    Never returns None — always returns a list of 3 dicts.
    """
    bundle_result = _load_bundle(current_symlink)
    if bundle_result is None:
        return _cold_start_all(FEATURE_VERSION)

    manifest, artifact_dir = bundle_result
    manifest_fv = manifest.get("feature_version", "")

    # Stale-model guard (spec §8)
    if manifest_fv != FEATURE_VERSION:
        logger.warning(
            "model_stale; retrain required (manifest.feature_version=%r, live=%r)",
            manifest_fv, FEATURE_VERSION,
        )
        return _cold_start_all(FEATURE_VERSION)

    # Load scaler once (shared across horizons)
    scaler: Scaler | None = None
    scaler_path = artifact_dir / "scaler.pkl"
    if scaler_path.exists():
        with open(scaler_path, "rb") as f:
            scaler = pickle.load(f)

    feature_columns: list[str] = manifest.get("feature_columns", [])
    if not feature_columns:
        # Derive from dataset ordering when not stored in manifest
        feature_columns = _V1_NAMES + _REGIME_COLS + ["signal_type_id"]

    cells: list[dict] = []
    for h in _HORIZONS:
        horizon_result = _load_horizon(artifact_dir, h, scaler)
        if horizon_result is None:
            cells.append(_cold_start_cell(h, FEATURE_VERSION))
            continue

        booster, iso_regs, q, loaded_scaler = horizon_result
        if scaler is None:
            scaler = loaded_scaler

        # Build feature row
        X_raw = _build_feature_row(conn, signal_id, manifest_fv, feature_columns)
        if X_raw is None:
            cells.append(_cold_start_cell(h, FEATURE_VERSION))
            continue

        # Apply scaler
        X_z = transform(X_raw, loaded_scaler)

        # Raw class probabilities from booster
        raw_probs = booster.predict(X_z)  # shape (1, 3) for multiclass

        # Per-class isotonic calibration + renormalize
        p_cal = np.empty(3, dtype=np.float64)
        for c in range(3):
            if iso_regs[c] is not None:
                p_cal[c] = float(iso_regs[c].predict(raw_probs[:, c])[0])
            else:
                p_cal[c] = float(raw_probs[0, c])

        total = p_cal.sum()
        if total > 0:
            p_cal = p_cal / total
        else:
            p_cal = np.full(3, 1 / 3)

        pred_idx = int(np.argmax(p_cal))
        predicted_class = CLASS_NAMES[pred_idx]

        # Conformal prediction set: {c : 1 - p_cal[c] <= q}
        conformal_set = sorted(
            CLASS_NAMES[c] for c in range(3) if 1.0 - p_cal[c] <= q
        )

        # SHAP top-5 (signed) for predicted class
        shap_top = _compute_shap(booster, X_z, pred_idx, feature_columns)

        cells.append({
            "horizon_days":    h,
            "p_bull":          float(p_cal[2]),
            "p_base":          float(p_cal[1]),
            "p_bear":          float(p_cal[0]),
            "predicted_class": predicted_class,
            "conformal_set":   conformal_set,
            "shap_top":        shap_top,
            "model_version":   manifest["model_version"],
            "feature_version": manifest_fv,
        })

    return cells


def _compute_shap(
    booster: lgb.Booster,
    X_z: np.ndarray,
    pred_idx: int,
    feature_columns: list[str],
) -> list[list]:
    """Return top-5 SHAP features as [[name, signed_value], ...]."""
    try:
        explainer = shap.TreeExplainer(booster)
        shap_values = explainer.shap_values(X_z)
        # For multiclass, shap_values is a list of arrays (one per class)
        if isinstance(shap_values, list):
            sv = shap_values[pred_idx][0]   # shape (n_features,)
        else:
            sv = shap_values[0]             # fallback for binary
        n = min(5, len(sv))
        top_indices = np.argsort(np.abs(sv))[::-1][:n]
        return [[feature_columns[i], float(sv[i])] for i in top_indices]
    except Exception as exc:
        logger.warning("SHAP computation failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# batch_backfill
# ---------------------------------------------------------------------------

def batch_backfill(
    conn: duckdb.DuckDBPyConnection,
    since_ts: datetime,
    *,
    current_symlink: Path = CURRENT_SYMLINK,
) -> int:
    """Predict for every signal with ts_emitted >= since_ts that lacks a prediction row.

    Guards against duplicates via (signal_id, horizon_days, model_version) PK.
    Returns the number of new rows written.
    """
    # Normalise since_ts to naive for comparison with DB values
    if since_ts.tzinfo is not None:
        since_ts_naive = since_ts.replace(tzinfo=None)
    else:
        since_ts_naive = since_ts

    signal_rows = conn.execute(
        "SELECT signal_id FROM signals WHERE ts_emitted >= ?",
        [since_ts_naive],
    ).fetchall()

    total_written = 0

    for (sid,) in signal_rows:
        cells = predict(conn, sid, current_symlink=current_symlink)
        for cell in cells:
            mv = cell["model_version"]
            h = cell["horizon_days"]

            # Check PK guard
            exists = conn.execute(
                """
                SELECT 1 FROM signal_predictions
                WHERE signal_id = ? AND horizon_days = ? AND model_version = ?
                """,
                [sid, h, mv],
            ).fetchone()
            if exists:
                continue

            conformal_str = ",".join(sorted(cell["conformal_set"]))
            shap_json = json.dumps(cell["shap_top"])
            predicted_at = datetime.now()  # naive IST per project convention

            conn.execute(
                """
                INSERT INTO signal_predictions
                    (signal_id, horizon_days, p_bull, p_base, p_bear,
                     predicted_class, conformal_set, shap_top,
                     model_version, feature_version, predicted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    sid, h,
                    cell["p_bull"], cell["p_base"], cell["p_bear"],
                    cell["predicted_class"],
                    conformal_str,
                    shap_json,
                    mv,
                    cell["feature_version"],
                    predicted_at,
                ],
            )
            total_written += 1

    return total_written
