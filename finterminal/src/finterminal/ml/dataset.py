"""ml/dataset.py — leakage-free training matrix builder.

Public surface:
    build_matrix(conn, horizon_days, feature_version, until_ts,
                 extra_feature_builders=None)
    -> tuple[np.ndarray, np.ndarray, MatrixMeta]

Algorithm (spec §4.2 + §8):
  1. label_outcomes(conn, horizon_days) → (signal_id, label, sigma_used).
  2. Pull signal_features rows where feature_version = ? AND is_missing = FALSE.
     Pivot long→wide (one column per feature name).
  3. Join with signals for ts_emitted and inline regime columns.
  4. until_ts cut: keep only rows where ts_emitted + horizon_days <= until_ts.
     (No peeking — only resolved horizons.)
  5. Inner-join with labels on signal_id (drops any signal lacking a label).
  6. Drop rows missing ANY of the 20 V1 feature columns after the pivot.
     Count into n_dropped_for_missing.
  7. Encode label as integer: bull=2, base=1, bear=0.
     LightGBM expects small non-negative integers for multiclass targets.
  8. Encode signal_type as integer via sorted-name lookup (deterministic,
     inspectable: index of signal_type in the sorted list of distinct types).
  9. Apply each extra_feature_builder(conn, signal_id) → dict; merge as columns.
 10. Return (X float64, y int8, MatrixMeta).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import duckdb
import numpy as np
import polars as pl

from .labels import label_outcomes
from ..features.registry import V1_FEATURES

# Stable ordered list of the 20 V1 feature names.
_V1_NAMES: list[str] = [f.name for f in V1_FEATURES]

# Inline regime columns stored directly on the signals table.
_REGIME_COLS = [
    "regime_nifty_close",
    "regime_nifty_pct_50d",
    "regime_india_vix",
    "regime_inr_usd",
    "regime_brent_usd",
    "regime_india_10y_yield",
]

# Label string → integer encoding (bull=2, base=1, bear=0).
_LABEL_INT = {"bull": 2, "base": 1, "bear": 0}


@dataclass
class MatrixMeta:
    signal_ids: list[str]
    feature_columns: list[str]      # names of X's columns in column order
    feature_version: str
    horizon_days: int
    until_ts: datetime
    n_rows: int
    n_dropped_for_missing: int


def build_matrix(
    conn: duckdb.DuckDBPyConnection,
    horizon_days: int,
    feature_version: str,
    until_ts: datetime,
    extra_feature_builders: list[Callable[[duckdb.DuckDBPyConnection, str], dict]] | None = None,
) -> tuple[np.ndarray, np.ndarray, MatrixMeta]:
    """Build a leakage-free training matrix.

    Returns (X, y, meta) where:
      X — float64 array of shape (n_rows, n_features).
      y — int8 array of shape (n_rows,).  bull=2, base=1, bear=0.
      meta — MatrixMeta with signal_ids, feature_columns, counts, etc.
    """
    extra_feature_builders = extra_feature_builders or []

    # ------------------------------------------------------------------ #
    # Step 1: labels                                                       #
    # ------------------------------------------------------------------ #
    df_labels = label_outcomes(conn, horizon_days)
    if df_labels.is_empty():
        return _empty_result(horizon_days, feature_version, until_ts,
                             extra_feature_builders, conn)

    # ------------------------------------------------------------------ #
    # Step 2: pivot signal_features (long → wide)                         #
    # ------------------------------------------------------------------ #
    feat_rows = conn.execute(
        """
        SELECT signal_id, feature_name, feature_value
        FROM   signal_features
        WHERE  feature_version = ?
          AND  is_missing = FALSE
        """,
        [feature_version],
    ).fetchall()

    if not feat_rows:
        return _empty_result(horizon_days, feature_version, until_ts,
                             extra_feature_builders, conn)

    # Build wide dict: signal_id → {feature_name: feature_value}
    wide: dict[str, dict[str, float]] = {}
    for sid, fname, fval in feat_rows:
        wide.setdefault(sid, {})[fname] = float(fval) if fval is not None else float("nan")

    # ------------------------------------------------------------------ #
    # Step 3: pull signals (ts_emitted + regime cols + signal_type)       #
    # ------------------------------------------------------------------ #
    sig_cols = ", ".join(
        ["signal_id", "signal_type", "ts_emitted"] + _REGIME_COLS
    )
    sig_rows = conn.execute(f"SELECT {sig_cols} FROM signals").fetchall()

    sig_info: dict[str, dict] = {}
    for row in sig_rows:
        sid = row[0]
        sig_info[sid] = {
            "signal_type": row[1],
            "ts_emitted": row[2],
            **{col: row[3 + i] for i, col in enumerate(_REGIME_COLS)},
        }

    # ------------------------------------------------------------------ #
    # Step 4: until_ts cut — keep only resolved horizons                  #
    # ------------------------------------------------------------------ #
    cutoff_delta = timedelta(days=horizon_days)
    # Ensure until_ts is a datetime for comparison
    if not isinstance(until_ts, datetime):
        until_ts = datetime.fromisoformat(str(until_ts))

    valid_sids = set()
    for sid, info in sig_info.items():
        ts = info["ts_emitted"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if ts + cutoff_delta <= until_ts:
            valid_sids.add(sid)

    # ------------------------------------------------------------------ #
    # Step 5: inner-join with labels                                       #
    # ------------------------------------------------------------------ #
    label_map: dict[str, str] = {
        row[0]: row[1]
        for row in df_labels.iter_rows()
    }
    # Only keep signals that are in valid_sids AND have a label AND have features
    candidate_sids = (
        set(label_map.keys()) & valid_sids & set(wide.keys())
    )

    # ------------------------------------------------------------------ #
    # Step 6: drop rows missing any of the 20 V1 feature columns          #
    # ------------------------------------------------------------------ #
    complete_sids: list[str] = []
    dropped = 0
    for sid in candidate_sids:
        feats = wide[sid]
        if all(name in feats for name in _V1_NAMES):
            complete_sids.append(sid)
        else:
            dropped += 1

    if not complete_sids:
        return _empty_result(horizon_days, feature_version, until_ts,
                             extra_feature_builders, conn, n_dropped=dropped)

    # Sort for determinism
    complete_sids.sort()

    # ------------------------------------------------------------------ #
    # Step 7 + 8: encode labels and signal_type                           #
    # ------------------------------------------------------------------ #
    # Stable sorted lookup for signal_type encoding
    all_types = sorted({sig_info[sid]["signal_type"] for sid in complete_sids})
    type_to_id = {t: i for i, t in enumerate(all_types)}

    # ------------------------------------------------------------------ #
    # Step 9: extra_feature_builders                                       #
    # ------------------------------------------------------------------ #
    # Collect extra columns per signal
    extra_cols_map: dict[str, dict[str, float]] = {}
    extra_col_names: list[str] = []
    for sid in complete_sids:
        merged: dict[str, float] = {}
        for builder in extra_feature_builders:
            result = builder(conn, sid)
            merged.update(result)
        extra_cols_map[sid] = merged
    # Determine extra column names from first signal (assumes all builders
    # return same keys for every signal in this matrix call)
    if complete_sids and extra_feature_builders:
        # Gather union of all keys in insertion order
        seen: dict[str, None] = {}
        for sid in complete_sids:
            for k in extra_cols_map[sid]:
                seen[k] = None
        extra_col_names = list(seen.keys())

    # ------------------------------------------------------------------ #
    # Assemble X and y                                                     #
    # ------------------------------------------------------------------ #
    # Column order: V1_NAMES + regime_cols + signal_type_id + extra cols
    feature_columns = _V1_NAMES + _REGIME_COLS + ["signal_type_id"] + extra_col_names

    n_rows = len(complete_sids)
    n_cols = len(feature_columns)
    X = np.empty((n_rows, n_cols), dtype=np.float64)
    y = np.empty(n_rows, dtype=np.int8)

    for row_i, sid in enumerate(complete_sids):
        feats = wide[sid]
        info = sig_info[sid]

        # V1 features
        for col_i, name in enumerate(_V1_NAMES):
            X[row_i, col_i] = feats.get(name, float("nan"))

        # Regime columns
        base = len(_V1_NAMES)
        for col_i, col in enumerate(_REGIME_COLS):
            val = info[col]
            X[row_i, base + col_i] = float(val) if val is not None else float("nan")

        # signal_type_id
        X[row_i, base + len(_REGIME_COLS)] = float(type_to_id[info["signal_type"]])

        # Extra feature builders
        extra_base = base + len(_REGIME_COLS) + 1
        for col_i, col_name in enumerate(extra_col_names):
            val = extra_cols_map[sid].get(col_name, float("nan"))
            X[row_i, extra_base + col_i] = float(val)

        # Label
        y[row_i] = _LABEL_INT[label_map[sid]]

    meta = MatrixMeta(
        signal_ids=complete_sids,
        feature_columns=feature_columns,
        feature_version=feature_version,
        horizon_days=horizon_days,
        until_ts=until_ts,
        n_rows=n_rows,
        n_dropped_for_missing=dropped,
    )
    return X, y, meta


def _empty_result(
    horizon_days: int,
    feature_version: str,
    until_ts: datetime,
    extra_feature_builders: list,
    conn: duckdb.DuckDBPyConnection,
    n_dropped: int = 0,
) -> tuple[np.ndarray, np.ndarray, MatrixMeta]:
    """Return empty arrays with the correct column shape."""
    # Derive extra column names if possible (call builders with dummy id)
    extra_col_names: list[str] = []
    if extra_feature_builders:
        dummy_merged: dict[str, None] = {}
        for builder in extra_feature_builders:
            try:
                result = builder(conn, "__empty__")
                for k in result:
                    dummy_merged[k] = None
            except Exception:
                pass
        extra_col_names = list(dummy_merged.keys())

    feature_columns = _V1_NAMES + _REGIME_COLS + ["signal_type_id"] + extra_col_names
    n_cols = len(feature_columns)
    X = np.empty((0, n_cols), dtype=np.float64)
    y = np.empty(0, dtype=np.int8)
    meta = MatrixMeta(
        signal_ids=[],
        feature_columns=feature_columns,
        feature_version=feature_version,
        horizon_days=horizon_days,
        until_ts=until_ts,
        n_rows=0,
        n_dropped_for_missing=n_dropped,
    )
    return X, y, meta
