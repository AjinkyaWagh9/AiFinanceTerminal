"""Agglomerative clustering of embedded news stories.

# Tune these based on manual inspection of the first 3 runs.
# CLUSTER_DISTANCE_THRESHOLD: lower → more smaller clusters; higher → fewer bigger clusters.
# MINHASH_JACCARD_THRESHOLD: imported by dedupe.py — set here so all thresholds are together.
# LINEAGE_CENTROID_THRESHOLD: imported by lineage.py.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

from .collector import Story

logger = logging.getLogger(__name__)

# Tune these based on manual inspection of the first 3 runs.
CLUSTER_DISTANCE_THRESHOLD: float = 0.55
MINHASH_JACCARD_THRESHOLD: float = 0.85
LINEAGE_CENTROID_THRESHOLD: float = 0.70


@dataclass
class Cluster:
    id: str
    story_ids: list[str]
    centroid: list[float]
    top_tickers: list[str] = field(default_factory=list)
    dominant_sector: str | None = None
    representative_id: str | None = None
    first_seen: object = None  # datetime | None
    story_count: int = 0
    source_count: int = 0


def _centroid(embeddings: np.ndarray) -> list[float]:
    c = embeddings.mean(axis=0)
    norm = np.linalg.norm(c)
    return (c / norm if norm > 0 else c).tolist()


def _representative(embeddings: np.ndarray, story_ids: list[str], centroid: list[float]) -> str:
    """Return the story_id closest to the centroid."""
    c = np.array(centroid)
    sims = embeddings @ c / (np.linalg.norm(embeddings, axis=1) * np.linalg.norm(c) + 1e-9)
    return story_ids[int(np.argmax(sims))]


def cluster_stories(stories: list[Story]) -> list[Cluster]:
    """Cluster stories by embedding similarity. Returns list of Cluster objects."""
    if not stories:
        return []

    valid = [s for s in stories if s.embedding]
    if not valid:
        return []

    embs = np.array([s.embedding for s in valid], dtype=np.float32)

    if len(valid) == 1:
        c_id = str(uuid.uuid4())
        s = valid[0]
        cluster = Cluster(
            id=c_id,
            story_ids=[s.id],
            centroid=s.embedding,
            top_tickers=s.tickers[:3],
            dominant_sector=(s.sectors[0] if s.sectors else None),
            representative_id=s.id,
            first_seen=s.published_at,
            story_count=1,
            source_count=1,
        )
        return [cluster]

    # Cosine distance matrix
    dist_matrix = pdist(embs, metric="cosine")
    Z = linkage(dist_matrix, method="single")
    labels = fcluster(Z, t=CLUSTER_DISTANCE_THRESHOLD, criterion="distance")

    clusters: list[Cluster] = []
    for label in sorted(set(labels)):
        indices = [i for i, l in enumerate(labels) if l == label]
        cluster_stories_list = [valid[i] for i in indices]
        cluster_embs = embs[indices]

        tickers_flat = [t for s in cluster_stories_list for t in s.tickers]
        ticker_counts: dict[str, int] = {}
        for t in tickers_flat:
            ticker_counts[t] = ticker_counts.get(t, 0) + 1
        top_tickers = sorted(ticker_counts, key=ticker_counts.get, reverse=True)[:3]  # type: ignore[arg-type]

        sectors_flat = [sec for s in cluster_stories_list for sec in s.sectors]
        dominant_sector = max(set(sectors_flat), key=sectors_flat.count) if sectors_flat else None

        centroid = _centroid(cluster_embs)
        ids = [s.id for s in cluster_stories_list]
        rep_id = _representative(cluster_embs, ids, centroid)

        pub_dates = [s.published_at for s in cluster_stories_list if s.published_at]
        first_seen = min(pub_dates) if pub_dates else None

        sources = {s.source for s in cluster_stories_list}

        clusters.append(Cluster(
            id=str(uuid.uuid4()),
            story_ids=ids,
            centroid=centroid,
            top_tickers=top_tickers,
            dominant_sector=dominant_sector,
            representative_id=rep_id,
            first_seen=first_seen,
            story_count=len(cluster_stories_list),
            source_count=len(sources),
        ))

    return clusters
