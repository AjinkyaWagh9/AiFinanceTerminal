"""Day-over-day cluster lineage matching.

Matches today's clusters to yesterday's via centroid cosine similarity.
Computes story_count_delta for each matched pair.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from .cluster import Cluster, LINEAGE_CENTROID_THRESHOLD


@dataclass
class LineageLink:
    parent_id: str
    child_id: str
    day: date
    similarity: float
    story_count_delta: int


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def match_clusters(
    yesterday: list[Cluster],
    today: list[Cluster],
    day: date,
) -> list[LineageLink]:
    """For each today cluster, find best-matching yesterday cluster (cosine >= threshold).

    Returns LineageLink for each matched pair. Unmatched today clusters are new (day_n=1).
    Each yesterday cluster can only be matched once (greedy, best-similarity-first).
    """
    if not yesterday or not today:
        return []

    links: list[LineageLink] = []
    used_parents: set[str] = set()

    for child in today:
        best_sim = LINEAGE_CENTROID_THRESHOLD - 1e-9
        best_parent: Cluster | None = None
        for parent in yesterday:
            if parent.id in used_parents:
                continue
            sim = _cosine(child.centroid, parent.centroid)
            if sim > best_sim:
                best_sim = sim
                best_parent = parent
        if best_parent is not None and best_sim >= LINEAGE_CENTROID_THRESHOLD:
            delta = child.story_count - best_parent.story_count
            links.append(LineageLink(
                parent_id=best_parent.id,
                child_id=child.id,
                day=day,
                similarity=best_sim,
                story_count_delta=delta,
            ))
            used_parents.add(best_parent.id)

    return links
