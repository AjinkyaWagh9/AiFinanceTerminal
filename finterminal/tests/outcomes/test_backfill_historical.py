# tests/outcomes/test_backfill_historical.py
from datetime import datetime, date, timedelta
from finterminal.data.duckdb_store import connect
from finterminal.outcomes.backfill_historical import backfill_from_news_clusters

def _insert_cluster(conn, cluster_id, first_seen, tickers, story_count):
    conn.execute(
        """INSERT INTO news_clusters (id, as_of, story_count, source_count,
           top_tickers, dominant_sector, representative_id, centroid, first_seen)
           VALUES (?, ?, ?, 1, ?, NULL, 'rep', NULL, ?)""",
        [cluster_id, first_seen.date(), story_count, tickers, first_seen],
    )

def test_old_clusters_are_replayed_recent_skipped(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _insert_cluster(conn, "old", datetime.now() - timedelta(days=30), ["TCS"], 5)
    _insert_cluster(conn, "new", datetime.now() - timedelta(days=2),  ["TCS"], 5)
    n = backfill_from_news_clusters(conn)
    assert n == 1  # only "old" was emitted
    rows = conn.execute(
        "SELECT source_ref FROM signals WHERE signal_type='cluster_momentum'"
    ).fetchall()
    assert {r[0] for r in rows} == {"old"}
