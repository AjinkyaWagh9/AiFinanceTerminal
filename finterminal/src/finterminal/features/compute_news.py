# src/finterminal/features/compute_news.py
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
import duckdb

from .zscore import rolling_zscore
from .registry import ZSCORE_WINDOW_DAYS, ZSCORE_MIN_OBS
from finterminal.outcomes.schema import SignalType

Result = tuple[float | None, bool]

def compute_cluster_momentum_z(conn: duckdb.DuckDBPyConnection, *,
                               signal_type: SignalType,
                               ticker: str,
                               ts_emitted: datetime,
                               payload: dict[str, Any],
                               **_) -> Result:
    if signal_type != SignalType.CLUSTER_MOMENTUM:
        return None, True
    delta = payload.get("story_count_delta")
    if delta is None:
        return None, True
    cutoff = ts_emitted
    rows = conn.execute(
        """
        SELECT TRY_CAST(payload->>'story_count_delta' AS DOUBLE) AS d
        FROM signals
        WHERE signal_type = ? AND ticker = ?
          AND ts_emitted < ? AND ts_emitted >= ?
          AND payload IS NOT NULL
        ORDER BY ts_emitted DESC
        """,
        [SignalType.CLUSTER_MOMENTUM.value, ticker, cutoff,
         cutoff - timedelta(days=ZSCORE_WINDOW_DAYS)],
    ).fetchall()
    history = [r[0] for r in rows if r[0] is not None]
    return rolling_zscore(float(delta), history, min_obs=ZSCORE_MIN_OBS)

def compute_narrative_price_divergence(*,
                                       cluster_momentum_z: float | None,
                                       mom_7d_z: float | None,
                                       **_) -> Result:
    if cluster_momentum_z is None or mom_7d_z is None:
        return None, True
    return cluster_momentum_z - mom_7d_z, False
