"""Two-stage deduplication for news stories.

Stage 1 (URL): exact URL match — fast, O(n).
Stage 2 (MinHash): Jaccard similarity on headline shingles — catches wire-service
republications of the same story with minor wording changes.

Thresholds live in cluster.py so all three can be tuned together.
"""
from __future__ import annotations

import logging

from datasketch import MinHash, MinHashLSH

from .cluster import MINHASH_JACCARD_THRESHOLD
from .collector import Story

logger = logging.getLogger(__name__)

_SHINGLE_SIZE = 3  # character-level 3-grams on lowercased headline


def _shingles(text: str) -> set[bytes]:
    t = text.lower()
    return {t[i:i + _SHINGLE_SIZE].encode() for i in range(max(1, len(t) - _SHINGLE_SIZE + 1))}


def _make_minhash(story: Story, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for s in _shingles(story.headline):
        m.update(s)
    return m


def drop_url_dupes(stories: list[Story]) -> list[Story]:
    """Keep first occurrence of each URL; drop subsequent exact-URL matches."""
    seen: set[str] = set()
    result: list[Story] = []
    for s in stories:
        key = s.url or s.id
        if key in seen:
            continue
        seen.add(key)
        result.append(s)
    return result


def minhash_filter(stories: list[Story], num_perm: int = 128) -> list[Story]:
    """Drop near-duplicate stories (Jaccard >= threshold on headline shingles).

    Keeps the first story in each near-duplicate group (publication order).
    """
    if not stories:
        return []

    lsh = MinHashLSH(threshold=MINHASH_JACCARD_THRESHOLD, num_perm=num_perm)
    kept: list[Story] = []

    for i, story in enumerate(stories):
        mh = _make_minhash(story, num_perm)
        key = f"s{i}"
        try:
            result = lsh.query(mh)
        except Exception:
            result = []
        if result:
            logger.debug("near-dup dropped: '%s'", story.headline[:60])
            continue
        lsh.insert(key, mh)
        kept.append(story)

    return kept
