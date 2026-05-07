"""Tests for the embedder — shape, determinism, lazy load."""
import numpy as np
import pytest
from finterminal.news.embedder import embed


def test_embed_returns_correct_shape():
    headlines = ["Reliance Q4 beats", "HDFC Bank stress"]
    result = embed(headlines)
    assert result.shape == (2, 384)


def test_embed_deterministic():
    headlines = ["Reliance Q4 beats estimates"]
    a = embed(headlines)
    b = embed(headlines)
    assert np.allclose(a, b)


def test_embed_empty_input():
    result = embed([])
    assert result.shape[0] == 0


def test_embed_single():
    result = embed(["one story"])
    assert result.shape == (1, 384)
