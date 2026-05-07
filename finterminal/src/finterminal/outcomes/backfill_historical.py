# src/finterminal/outcomes/backfill_historical.py
from __future__ import annotations
from datetime import date, timedelta
import duckdb

from .ledger import emit_signal
from .schema import SignalType, MACRO_TICKER

_CUTOFF_DAYS = 7

def backfill_from_news_clusters(conn: duckdb.DuckDBPyConnection) -> int:
    """One-shot replay of `news_clusters` rows where first_seen <= today - 7d.
    For each, emits a cluster_momentum signal. Idempotent via signals UNIQUE constraint."""
    cutoff = date.today() - timedelta(days=_CUTOFF_DAYS)
    rows = conn.execute(
        """
        SELECT id, top_tickers, story_count, first_seen
        FROM news_clusters
        WHERE DATE(first_seen) <= ?
        """,
        [cutoff],
    ).fetchall()

    emitted = 0
    for cluster_id, top_tickers, story_count, first_seen in rows:
        ticker = (top_tickers[0] if top_tickers else MACRO_TICKER) or MACRO_TICKER
        # Historical clusters don't carry a delta — use story_count as a proxy
        # (won't compute alpha differently; just metadata). Confidence = story_count clamp.
        sid = emit_signal(
            conn,
            signal_type=SignalType.CLUSTER_MOMENTUM,
            ticker=ticker,
            ts_emitted=first_seen,
            payload={"cluster_id": cluster_id, "story_count": story_count,
                     "historical_replay": True},
            confidence=min(1.0, story_count / 10.0),
            why=f"historical replay of cluster {cluster_id}",
            source_ref=cluster_id,
        )
        if sid is not None:
            emitted += 1
    return emitted
