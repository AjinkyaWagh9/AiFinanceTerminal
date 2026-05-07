"""Sentence embedding via sentence-transformers/all-MiniLM-L6-v2.

Lazy-loads on first call; caches model in memory.
Expected wall-clock: first run approx 8-12s (model download + encoding ~150 headlines);
subsequent runs < 4s (model already in memory / disk cache).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_MODEL_CACHE_DIR = Path("./data/models")
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("loading embedding model %s (first call — may take ~10s)", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME, cache_folder=str(_MODEL_CACHE_DIR))
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """Return shape (n, 384) float32 embeddings. Empty input → shape (0, 384)."""
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False).astype(np.float32)
