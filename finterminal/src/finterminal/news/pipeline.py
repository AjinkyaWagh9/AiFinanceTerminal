"""News pipeline orchestrator. Runs all steps and persists to DuckDB."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import duckdb

from .collector import fetch_all
from .dedupe import drop_url_dupes, minhash_filter
from .embedder import embed
from .cluster import cluster_stories
from .lineage import match_clusters
from .tagger import tag
from ..data import news_store
from ..outcomes import ledger as _ledger
from ..outcomes.schema import SignalType, MACRO_TICKER

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    as_of: date
    n_stories: int
    n_clusters: int
    n_lineage_links: int
    runtime_s: float


def run(conn: duckdb.DuckDBPyConnection) -> PipelineResult:
    """Run the full news pipeline and persist results. Returns PipelineResult."""
    t0 = time.monotonic()
    today = date.today()

    # 1. Collect
    raw_stories = fetch_all()
    logger.info("collected %d raw stories", len(raw_stories))

    if not raw_stories:
        return PipelineResult(
            as_of=today, n_stories=0, n_clusters=0,
            n_lineage_links=0, runtime_s=time.monotonic() - t0,
        )

    # 2. Recency filter — drop stories older than 7 days (some feeds include ancient articles)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    def _is_fresh(s) -> bool:
        if s.published_at is None:
            return True
        dt = s.published_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    fresh = [s for s in raw_stories if _is_fresh(s)]
    stale_count = len(raw_stories) - len(fresh)
    if stale_count:
        logger.info("dropped %d stale stories (older than 7 days)", stale_count)

    # 3. Dedupe
    stories = drop_url_dupes(fresh)
    stories = minhash_filter(stories)
    logger.info("%d stories after dedupe", len(stories))

    # 4. Tag
    stories = tag(stories)

    # 5. Embed
    headlines = [s.headline for s in stories]
    embeddings = embed(headlines)
    for s, emb in zip(stories, embeddings):
        s.embedding = emb.tolist()

    # 6. Cluster
    clusters = cluster_stories(stories)
    logger.info("%d clusters formed", len(clusters))

    # 7. Persist stories + clusters
    news_store.upsert_stories(conn, stories)
    news_store.upsert_clusters(conn, clusters, today)

    # 8. Lineage — match today's clusters to yesterday's
    yesterday = today - timedelta(days=1)
    yesterday_clusters = news_store.clusters_for_as_of(conn, yesterday)
    links = match_clusters(yesterday_clusters, clusters, today)
    news_store.upsert_lineage(conn, links)
    logger.info("%d lineage links created", len(links))

    # Build cluster dicts with story_count_delta for emission
    delta_by_child: dict[str, int] = {lk.child_id: lk.story_count_delta for lk in links}
    clusters_with_delta = []
    for cl in clusters:
        clusters_with_delta.append({
            "cluster_id": cl.id,
            "top_tickers": cl.top_tickers,
            "story_count": cl.story_count,
            "story_count_delta": delta_by_child.get(cl.id, 0),
            "first_seen": cl.first_seen,
        })
    _emit_cluster_momentum_signals(conn, clusters_with_delta)

    return PipelineResult(
        as_of=today,
        n_stories=len(stories),
        n_clusters=len(clusters),
        n_lineage_links=len(links),
        runtime_s=time.monotonic() - t0,
    )


def _emit_cluster_momentum_signals(conn: duckdb.DuckDBPyConnection, clusters: list[dict]) -> None:
    """Fail-safe: emit cluster_momentum signals after a /refresh-news run.
    Any exception in emission is swallowed so the news pipeline keeps working."""
    if os.environ.get("OUTCOMES_LEDGER_ENABLED") != "1":
        return
    for c in clusters:
        delta = c.get("story_count_delta", 0)
        if not delta:
            continue
        ticker = (c.get("top_tickers") or [None])[0] or MACRO_TICKER
        try:
            _ledger.emit_signal(
                conn,
                signal_type=SignalType.CLUSTER_MOMENTUM,
                ticker=ticker,
                ts_emitted=c["first_seen"],
                payload={"cluster_id": c["cluster_id"],
                         "story_count_delta": delta,
                         "story_count": c.get("story_count")},
                confidence=min(1.0, abs(delta) / 10.0),
                why=(f"cluster {c['cluster_id']} "
                     f"{'grew' if delta > 0 else 'shrank'} {abs(delta)} stories d/d"),
                source_ref=c["cluster_id"],
            )
        except Exception as e:
            logger.warning("emit_signal failed for cluster %s: %s",
                           c.get("cluster_id"), e)
