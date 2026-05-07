"""DuckDB read/write for news pipeline tables: news_stories, news_clusters, cluster_lineage."""
from __future__ import annotations

from datetime import date, datetime, timezone

import duckdb

from ..news.cluster import Cluster
from ..news.lineage import LineageLink


def upsert_stories(conn: duckdb.DuckDBPyConnection, stories: list) -> None:
    """Insert stories; skip on conflict (id is primary key)."""
    for s in stories:
        emb = s.embedding if s.embedding else None
        conn.execute(
            """
            INSERT OR IGNORE INTO news_stories
                (id, url, source, headline, body, published_at, fetched_at,
                 tickers, sectors, embedding, cluster_id)
            VALUES (?, ?, ?, ?, ?, ?, now(), ?, ?, ?, ?)
            """,
            [
                s.id, s.url, s.source, s.headline, s.body, s.published_at,
                s.tickers or [], s.sectors or [],
                emb, s.cluster_id,
            ],
        )


def upsert_clusters(conn: duckdb.DuckDBPyConnection, clusters: list[Cluster], as_of: date) -> None:
    """Upsert cluster rows for the given run date."""
    for c in clusters:
        first_seen = c.first_seen if c.first_seen is not None else datetime.now(timezone.utc)
        conn.execute(
            """
            INSERT OR REPLACE INTO news_clusters
                (id, as_of, story_count, source_count, top_tickers,
                 dominant_sector, representative_id, centroid, first_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                c.id, as_of, c.story_count, c.source_count,
                c.top_tickers, c.dominant_sector, c.representative_id,
                c.centroid, first_seen,
            ],
        )
        for story_id in c.story_ids:
            conn.execute(
                "UPDATE news_stories SET cluster_id = ? WHERE id = ?",
                [c.id, story_id],
            )


def upsert_lineage(conn: duckdb.DuckDBPyConnection, links: list[LineageLink]) -> None:
    for link in links:
        conn.execute(
            """
            INSERT OR REPLACE INTO cluster_lineage
                (parent_id, child_id, day, similarity, story_count_delta)
            VALUES (?, ?, ?, ?, ?)
            """,
            [link.parent_id, link.child_id, link.day, link.similarity, link.story_count_delta],
        )


def latest_clusters(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Return all clusters for the most recent as_of date, with lineage info."""
    rows = conn.execute(
        """
        WITH latest_date AS (
            SELECT MAX(as_of) AS as_of FROM news_clusters
        ),
        lineage_agg AS (
            SELECT
                child_id,
                SUM(story_count_delta) AS total_delta,
                COUNT(*) AS parent_count
            FROM cluster_lineage
            GROUP BY child_id
        )
        SELECT
            c.id, c.as_of, c.story_count, c.source_count,
            c.top_tickers, c.dominant_sector,
            COALESCE(s.headline, c.representative_id) AS headline,
            c.first_seen,
            COALESCE(l.total_delta, 0) AS story_count_delta,
            COALESCE(l.parent_count, 0) AS day_n
        FROM news_clusters c
        CROSS JOIN latest_date ld
        LEFT JOIN news_stories s ON s.id = c.representative_id
        LEFT JOIN lineage_agg l ON l.child_id = c.id
        WHERE c.as_of = ld.as_of
        ORDER BY c.story_count DESC
        """,
    ).fetchall()
    cols = ["id", "as_of", "story_count", "source_count", "top_tickers",
            "dominant_sector", "headline", "first_seen", "story_count_delta", "day_n"]
    return [dict(zip(cols, row)) for row in rows]


def clusters_for_as_of(conn: duckdb.DuckDBPyConnection, as_of: date) -> list[Cluster]:
    """Return Cluster objects for a specific date (used by lineage matching)."""
    rows = conn.execute(
        "SELECT id, story_count, centroid FROM news_clusters WHERE as_of = ?",
        [as_of],
    ).fetchall()
    clusters = []
    for row in rows:
        c = Cluster(id=row[0], story_ids=[], centroid=list(row[2] or []), story_count=row[1], source_count=0)
        clusters.append(c)
    return clusters
