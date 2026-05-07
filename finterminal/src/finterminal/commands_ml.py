"""CLI handlers for `finterminal ml` subcommands.

Mirrors the commands_features.py pattern: standalone functions callable
by the /ml REPL dispatcher and directly by tests.

Public functions:
    ml_train(conn) -> dict   — runs trainer.train_all; returns summary dict
    ml_backfill(conn, since_str) -> dict — runs predictor.batch_backfill
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import duckdb

from .features.compute_reflexivity import FEATURE_VERSION
from .ml import trainer as _trainer
from .ml import predictor as _predictor

logger = logging.getLogger(__name__)

_HORIZONS = [7, 30, 90]


def ml_train(conn: duckdb.DuckDBPyConnection) -> dict:
    """Run full ML training cycle for all horizons.

    Calls trainer.train_all(conn, horizons=[7,30,90], feature_version=FEATURE_VERSION).

    Returns a summary dict:
      {
        "model_version": str,
        "promoted":      bool,
        "mean_brier":    float | None,
        "n_skipped":     int,
      }

    Exit semantics (for CLI callers): this function raises only if training
    itself errors — callers should let exceptions propagate for exit 1.
    Promotion failures are NOT errors; they appear in promoted=False.
    """
    bundle = _trainer.train_all(conn, horizons=_HORIZONS, feature_version=FEATURE_VERSION)

    briers = [
        art.brier
        for art in bundle.per_horizon.values()
        if not math.isnan(art.brier)
    ]
    n_skipped = sum(
        1 for art in bundle.per_horizon.values()
        if math.isnan(art.brier)
    )
    mean_brier = (sum(briers) / len(briers)) if briers else None

    # Infer promotion from eval.json if available, else best-effort from bundle
    # The trainer writes promoted into eval.json; we derive it from whether
    # mean_brier + n_skipped represent a complete run.
    # For simplicity, read promoted from trainer manifest if possible.
    import json
    from pathlib import Path
    promoted = False
    try:
        eval_path = Path(bundle.artifact_dir) / "eval.json"
        if eval_path.exists():
            eval_data = json.loads(eval_path.read_text())
            promoted = bool(eval_data.get("promoted", False))
    except Exception:
        pass

    return {
        "model_version": bundle.model_version,
        "promoted": promoted,
        "mean_brier": mean_brier,
        "n_skipped": n_skipped,
    }


def ml_backfill(
    conn: duckdb.DuckDBPyConnection,
    since_str: str | None = None,
) -> dict:
    """Run nightly prediction backfill.

    since_str: ISO date string 'YYYY-MM-DD' or None for yesterday.

    Calls predictor.batch_backfill(conn, since_ts).

    Returns:
      {"rows_written": int, "since_ts": datetime}

    Raises on predictor errors (exit 1 convention for callers).
    """
    if since_str is None:
        # Default: yesterday (midnight UTC)
        since_ts = datetime.now(timezone.utc) - timedelta(days=1)
        # Use naive datetime consistent with DB convention
        since_ts = since_ts.replace(tzinfo=None)
    else:
        # Parse YYYY-MM-DD
        parsed = datetime.strptime(since_str, "%Y-%m-%d")
        since_ts = parsed  # naive, matches DB convention

    rows_written = _predictor.batch_backfill(conn, since_ts)

    return {"rows_written": rows_written, "since_ts": since_ts}
