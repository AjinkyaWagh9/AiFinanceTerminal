"""Tests for cluster lineage — centroid cosine matching + story_count_delta."""
from datetime import date
import numpy as np
from finterminal.news.cluster import Cluster
from finterminal.news.lineage import match_clusters, LineageLink


def _cluster(id_: str, centroid: list[float], story_count: int = 5) -> Cluster:
    c = Cluster(id=id_, story_ids=[], centroid=centroid, story_count=story_count, source_count=1)
    return c


def test_similar_clusters_linked():
    dim = 384
    yesterday = [_cluster("y1", [1.0] + [0.0] * (dim - 1), story_count=4)]
    today = [_cluster("t1", [1.0] + [0.0] * (dim - 1), story_count=6)]
    links = match_clusters(yesterday, today, date(2026, 4, 30))
    assert len(links) == 1
    assert links[0].parent_id == "y1"
    assert links[0].child_id == "t1"
    assert links[0].story_count_delta == 2  # 6 - 4


def test_dissimilar_clusters_not_linked():
    dim = 384
    yesterday = [_cluster("y1", [1.0] + [0.0] * (dim - 1))]
    today = [_cluster("t1", [0.0, 1.0] + [0.0] * (dim - 2))]
    links = match_clusters(yesterday, today, date(2026, 4, 30))
    assert links == []


def test_story_count_delta_negative():
    dim = 384
    yesterday = [_cluster("y1", [1.0] + [0.0] * (dim - 1), story_count=10)]
    today = [_cluster("t1", [1.0] + [0.0] * (dim - 1), story_count=6)]
    links = match_clusters(yesterday, today, date(2026, 4, 30))
    assert links[0].story_count_delta == -4


def test_no_yesterday_returns_empty():
    dim = 384
    today = [_cluster("t1", [1.0] + [0.0] * (dim - 1))]
    links = match_clusters([], today, date(2026, 4, 30))
    assert links == []


def test_lineage_link_fields():
    dim = 384
    yesterday = [_cluster("y1", [1.0] + [0.0] * (dim - 1), story_count=3)]
    today = [_cluster("t1", [1.0] + [0.0] * (dim - 1), story_count=5)]
    links = match_clusters(yesterday, today, date(2026, 4, 30))
    link = links[0]
    assert isinstance(link, LineageLink)
    assert link.similarity >= 0.9
    assert link.day == date(2026, 4, 30)
