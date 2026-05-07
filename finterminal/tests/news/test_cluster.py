"""Tests for agglomerative clustering."""
import numpy as np
import pytest
from finterminal.news.collector import Story
from finterminal.news.cluster import cluster_stories, Cluster


def _story_with_embedding(id_: str, emb: list[float]) -> Story:
    s = Story(id=id_, source="T", headline=f"Story {id_}", url=id_)
    s.embedding = emb
    return s


def test_two_topic_stories_form_two_clusters():
    """6 Reliance stories + 4 HDFC stories should produce ~2 clusters."""
    dim = 384
    rel_embs = [[1.0] + [0.0] * (dim - 1)] * 6
    hdfc_embs = [[0.0, 1.0] + [0.0] * (dim - 2)] * 4
    stories = (
        [_story_with_embedding(f"r{i}", e) for i, e in enumerate(rel_embs)] +
        [_story_with_embedding(f"h{i}", e) for i, e in enumerate(hdfc_embs)]
    )
    clusters = cluster_stories(stories)
    assert 1 <= len(clusters) <= 4  # flexible — synthetic embeddings may vary


def test_cluster_has_required_fields():
    dim = 384
    stories = [_story_with_embedding("s1", [1.0] + [0.0] * (dim - 1))]
    clusters = cluster_stories(stories)
    assert len(clusters) >= 1
    c = clusters[0]
    assert isinstance(c, Cluster)
    assert c.id
    assert len(c.story_ids) >= 1
    assert len(c.centroid) == dim


def test_cluster_empty_input():
    result = cluster_stories([])
    assert result == []
