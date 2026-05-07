"""ml/normaliser.py — z-norm with leakage-safe write-back.

Public surface:
    fit_transform(conn, X, meta) -> (X_z, Scaler)
    transform(X, scaler)        -> X_z

Leakage invariant (spec §4.3 + §8):
    fit_transform marks normalized=TRUE ONLY for signal_features rows
    whose signal_id is in meta.signal_ids AND feature_name is in
    meta.feature_columns AND feature_version = meta.feature_version.
    Rows outside the training cut are never touched.
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np

from .dataset import MatrixMeta


@dataclass
class Scaler:
    feature_columns: list[str]   # column order
    means:           np.ndarray  # shape (n_features,)
    stds:            np.ndarray  # shape (n_features,) — never zero (clamped to 1e-9)


def fit_transform(
    conn: duckdb.DuckDBPyConnection,
    X: np.ndarray,
    meta: MatrixMeta,
) -> tuple[np.ndarray, Scaler]:
    """Fit a per-column z-norm on X (training-cut), apply it, AND mark
    the training-cut rows in signal_features as normalized=TRUE.

    Leakage invariant: the write-back UPDATE touches ONLY rows whose
    signal_id is in meta.signal_ids. Rows outside the cut are untouched.
    """
    X = np.asarray(X, dtype=np.float64)

    # Compute per-column statistics on the training cut only
    means = X.mean(axis=0)
    stds = X.std(axis=0, ddof=0)

    # Clamp zero std to 1e-9 to avoid division by zero
    stds = np.where(stds == 0.0, 1e-9, stds)

    # Apply z-normalisation
    X_z = (X - means) / stds

    scaler = Scaler(
        feature_columns=list(meta.feature_columns),
        means=means,
        stds=stds,
    )

    # ------------------------------------------------------------------
    # Leakage-safe write-back: flip normalized=TRUE ONLY for rows in the
    # training cut (meta.signal_ids × meta.feature_columns × meta.feature_version).
    # We issue a single parameterised UPDATE — never touch rows outside
    # the cut.
    # ------------------------------------------------------------------
    if meta.signal_ids and meta.feature_columns:
        # Build IN-list placeholders
        sid_placeholders = ", ".join("?" for _ in meta.signal_ids)
        feat_placeholders = ", ".join("?" for _ in meta.feature_columns)

        params: list = (
            list(meta.signal_ids)
            + list(meta.feature_columns)
            + [meta.feature_version]
        )

        conn.execute(
            f"""
            UPDATE signal_features
               SET normalized = TRUE
             WHERE signal_id    IN ({sid_placeholders})
               AND feature_name IN ({feat_placeholders})
               AND feature_version = ?
            """,
            params,
        )

    return X_z, scaler


def transform(X: np.ndarray, scaler: Scaler) -> np.ndarray:
    """Apply a previously-fit scaler to a new matrix. No DB writes.

    Raises:
        ValueError: if X.shape[1] doesn't match len(scaler.feature_columns).
    """
    X = np.asarray(X, dtype=np.float64)
    n_expected = len(scaler.feature_columns)
    if X.shape[1] != n_expected:
        raise ValueError(
            f"Feature count mismatch: scaler expects {n_expected} features "
            f"but X has {X.shape[1]} columns."
        )
    return (X - scaler.means) / scaler.stds
