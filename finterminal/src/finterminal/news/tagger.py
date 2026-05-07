"""Ticker and sector tagger for news stories.

Uses the NSE universe (alias map) for exact whole-word matching, with a
rapidfuzz fallback for near-misses (e.g., 'Hindustan Unliever' → HINDUNILVR).
min_score (default 85) is configurable; matches in [70, min_score) are logged
at DEBUG to aid threshold tuning across first 3 runs.
"""
from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz

from ..data.india.nse_universe import load_equity_list, load_sector_map
from .collector import Story

logger = logging.getLogger(__name__)

_MAX_TICKERS_PER_STORY = 5


def _whole_word_match(text: str, alias: str) -> bool:
    if " " in alias:
        return alias.lower() in text.lower()
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", text.lower()))


def _score_ticker(blob: str, ticker: str, aliases: list[str], min_score: int) -> float:
    """Return match score [0, 1]. 1.0 = exact alias match; 0.8 = fuzzy near-match; 0 = no match."""
    for alias in aliases + [ticker]:
        if _whole_word_match(blob, alias):
            return 1.0
    # Rapidfuzz fallback on individual aliases
    for alias in aliases:
        if len(alias) < 4:
            continue  # skip very short aliases — too many false positives
        score = fuzz.partial_ratio(alias.lower(), blob.lower())
        if score >= min_score:
            return 0.8
        if score >= 70:
            logger.debug(
                "low-confidence match: '%.60s' ↔ '%s' = %d (below min_score=%d)",
                blob, alias, score, min_score,
            )
    return 0.0


def tag(stories: list[Story], min_score: int = 85) -> list[Story]:
    """Tag each Story in-place with tickers and sectors. Returns the same list."""
    universe = load_equity_list()
    sector_map = load_sector_map()

    for story in stories:
        blob = f"{story.headline} {story.body}"
        scored: list[tuple[float, str]] = []
        for ticker, info in universe.items():
            score = _score_ticker(blob, ticker, info["aliases"], min_score)
            if score > 0:
                scored.append((score, ticker))

        scored.sort(reverse=True)
        top_tickers = [t for _, t in scored[:_MAX_TICKERS_PER_STORY]]
        story.tickers = top_tickers
        story.sectors = list({sector_map[t] for t in top_tickers if t in sector_map})

    return stories
