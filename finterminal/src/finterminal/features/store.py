from __future__ import annotations
from typing import TypedDict
import duckdb


class FeatureCell(TypedDict, total=False):
    value: float | None
    is_missing: bool
    n_samples: int | None
    confidence: float | None
    feature_version: str | None
    normalized: bool


def upsert_features(conn: duckdb.DuckDBPyConnection,
                    signal_id: str,
                    features: dict[str, FeatureCell]) -> None:
    """Version-aware upsert with FREEZE-ON-WRITE semantics.

    Rule: if a row with matching (signal_id, feature_name, feature_version)
    already exists, this call is a no-op for that feature. A *different*
    feature_version overwrites — that is the model-evolution path.
    Cells without a feature_version (legacy / non-reflexivity features)
    overwrite as before.
    """
    if not features:
        return
    rows = [
        (
            signal_id,
            name,
            cell.get("value"),
            cell.get("is_missing", True),
            cell.get("n_samples"),
            cell.get("confidence"),
            cell.get("feature_version"),
            cell.get("normalized", False),
        )
        for name, cell in features.items()
    ]
    # Freeze-on-write is enforced via WHERE clause on UPDATE: only allow
    # overwrite when the existing row has NULL feature_version (legacy)
    # or a DIFFERENT feature_version (evolution). Same version → no-op.
    conn.executemany(
        """
        INSERT INTO signal_features
            (signal_id, feature_name, feature_value, is_missing,
             n_samples, confidence, feature_version, normalized)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (signal_id, feature_name) DO UPDATE SET
            feature_value   = EXCLUDED.feature_value,
            is_missing      = EXCLUDED.is_missing,
            n_samples       = EXCLUDED.n_samples,
            confidence      = EXCLUDED.confidence,
            feature_version = EXCLUDED.feature_version,
            normalized      = EXCLUDED.normalized
        WHERE EXCLUDED.feature_version IS NULL
           OR signal_features.feature_version IS DISTINCT FROM EXCLUDED.feature_version
        """,
        rows,
    )
