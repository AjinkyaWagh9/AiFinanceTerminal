"""Reflexivity feature compute layer.

Architecture notes (from input.md review):
  * `_sentiment_model(text)` is the only callsite that knows about VADER.
    Swap to FinBERT later by replacing the body — zero changes upstream.
  * Every emitted cell carries `feature_version`. The ML layer uses this
    to compare model generations and avoid mixing distributions.
  * Fetch query enforces BOTH `published_at <= ts` AND `fetched_at <= ts`
    to defend against ingestion-time leakage.
  * `normalized` is always False in v1; z-norm activator lives in #5.
"""
from __future__ import annotations
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

import duckdb
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Public — the ML layer reads this for comparability.
FEATURE_VERSION = "reflexivity_v1_vader_decay_0.5"

_vader = SentimentIntensityAnalyzer()

_DECAY_LAMBDA = 0.5
_MIN_ARTICLES = 5
_MIN_UNIQUE_RATIO = 0.7
_MIN_SCORE_STD = 0.05
_MAX_AGE_DAYS = 7
_CONFIDENCE_SCALE = 10
_WINDOW_DAYS = 7


def _sentiment_model(text: str) -> float:
    """Single point of model dependency. Returns a compound score in [-1, 1].

    Today: VADER. Tomorrow: FinBERT / hybrid. To swap, replace this body
    and bump FEATURE_VERSION above. No other code in the project should
    import a sentiment library directly.
    """
    return _vader.polarity_scores(text)["compound"]


@dataclass
class _Article:
    headline: str
    compound: float
    age_days: float


def _fetch_articles(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    start: datetime,
    end: datetime,
) -> list[_Article]:
    """Snapshot + ingestion-safe fetch.

    `published_at <= end` keeps only articles dated in-window.
    `fetched_at  <= end` excludes late-arriving articles whose ingestion
    timestamp is *after* the signal — they didn't exist in the system
    when the signal was emitted, so they cannot inform it.
    """
    rows = conn.execute(
        """
        SELECT headline, published_at
        FROM news_stories
        WHERE list_contains(tickers, ?)
          AND published_at >= ?
          AND published_at <= ?
          AND published_at IS NOT NULL
          AND fetched_at   <= ?
        ORDER BY published_at DESC
        """,
        [ticker, start, end, end],
    ).fetchall()
    out: list[_Article] = []
    for headline, pub_at in rows:
        compound = _sentiment_model(headline)
        age_days = (end - pub_at).total_seconds() / 86400.0
        out.append(_Article(headline=headline, compound=compound,
                            age_days=max(0.0, age_days)))
    return out


def _passes_quality_gate(articles: list[_Article]) -> bool:
    if len(articles) < _MIN_ARTICLES:
        return False
    unique_ratio = len({a.headline.lower() for a in articles}) / len(articles)
    if unique_ratio < _MIN_UNIQUE_RATIO:
        return False
    scores = [a.compound for a in articles]
    if statistics.stdev(scores) < _MIN_SCORE_STD:
        return False
    if any(a.age_days > _MAX_AGE_DAYS for a in articles):
        return False
    return True


def _weighted_mean(articles: list[_Article]) -> float:
    weights = [math.exp(-_DECAY_LAMBDA * a.age_days) for a in articles]
    scores = [a.compound for a in articles]
    total_w = sum(weights)
    return sum(s * w for s, w in zip(scores, weights)) / total_w


def _debug_dict(articles: list[_Article]) -> dict:
    if not articles:
        return {"mean_score": None, "std": None, "unique_ratio": None}
    scores = [a.compound for a in articles]
    return {
        "mean_score":   statistics.fmean(scores),
        "std":          statistics.stdev(scores) if len(scores) > 1 else 0.0,
        "unique_ratio": len({a.headline.lower() for a in articles}) / len(articles),
    }


def _make_cell(value: float | None, is_missing: bool,
               n_samples: int = 0, debug: dict | None = None) -> dict:
    confidence = (min(1.0, n_samples / _CONFIDENCE_SCALE)
                  if not is_missing else 0.0)
    return {
        "value":           value,
        "is_missing":      is_missing,
        "n_samples":       n_samples,
        "confidence":      confidence,
        "feature_version": FEATURE_VERSION,
        "normalized":      False,
        "debug":           debug or {},
    }


def compute_sentiment_level(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    ts_emitted: datetime,
    **_,
) -> dict:
    """Recency-weighted mean sentiment over [ts_emitted-7d, ts_emitted]."""
    start = ts_emitted - timedelta(days=_WINDOW_DAYS)
    articles = _fetch_articles(conn, ticker, start, ts_emitted)
    debug = _debug_dict(articles)
    if not _passes_quality_gate(articles):
        return _make_cell(None, True, debug=debug)
    value = _weighted_mean(articles)
    return _make_cell(value, False, n_samples=len(articles), debug=debug)


def compute_sentiment_delta(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    ts_emitted: datetime,
    **_,
) -> dict:
    """Raw delta between non-overlapping 7-day sentiment windows.

    Window A (current): [ts_emitted - 7d,  ts_emitted]
    Window B (prior):   [ts_emitted - 14d, ts_emitted - 7d)

    Z-normalization deferred — `normalized=False` until #5 activator.
    """
    boundary    = ts_emitted - timedelta(days=_WINDOW_DAYS)
    prior_start = ts_emitted - timedelta(days=2 * _WINDOW_DAYS)

    articles_now  = _fetch_articles(conn, ticker, boundary, ts_emitted)
    articles_prev = _fetch_articles(conn, ticker, prior_start, boundary)

    debug = {"now": _debug_dict(articles_now), "prev": _debug_dict(articles_prev)}

    if not _passes_quality_gate(articles_now) or not _passes_quality_gate(articles_prev):
        return _make_cell(None, True, debug=debug)

    delta = _weighted_mean(articles_now) - _weighted_mean(articles_prev)
    n = len(articles_now) + len(articles_prev)
    return _make_cell(delta, False, n_samples=n, debug=debug)


def _entropy(scores: list[float]) -> float:
    """Shannon entropy over VADER neg/neu/pos bins."""
    n = len(scores)
    if n == 0:
        return 0.0
    counts = {"neg": 0, "neu": 0, "pos": 0}
    for s in scores:
        if s < -0.05:
            counts["neg"] += 1
        elif s > 0.05:
            counts["pos"] += 1
        else:
            counts["neu"] += 1
    h = 0.0
    for c in counts.values():
        if c > 0:
            p = c / n
            h -= p * math.log(p)
    return h


def compute_entropy_sentiment(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    ts_emitted: datetime,
    **_,
) -> dict:
    """Shannon entropy of sentiment-bin distribution over [ts-7d, ts]."""
    start = ts_emitted - timedelta(days=_WINDOW_DAYS)
    articles = _fetch_articles(conn, ticker, start, ts_emitted)
    debug = _debug_dict(articles)
    if not _passes_quality_gate(articles):
        return _make_cell(None, True, debug=debug)
    value = _entropy([a.compound for a in articles])
    return _make_cell(value, False, n_samples=len(articles), debug=debug)


def compute_entropy_change(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    ts_emitted: datetime,
    **_,
) -> dict:
    """Delta of Shannon entropy between non-overlapping 7-day windows."""
    boundary    = ts_emitted - timedelta(days=_WINDOW_DAYS)
    prior_start = ts_emitted - timedelta(days=2 * _WINDOW_DAYS)
    articles_now  = _fetch_articles(conn, ticker, boundary, ts_emitted)
    articles_prev = _fetch_articles(conn, ticker, prior_start, boundary)
    debug = {"now": _debug_dict(articles_now), "prev": _debug_dict(articles_prev)}
    if not _passes_quality_gate(articles_now) or not _passes_quality_gate(articles_prev):
        return _make_cell(None, True, debug=debug)
    h_now  = _entropy([a.compound for a in articles_now])
    h_prev = _entropy([a.compound for a in articles_prev])
    n = len(articles_now) + len(articles_prev)
    return _make_cell(h_now - h_prev, False, n_samples=n, debug=debug)


_LOG3 = math.log(3)


def compute_feature_health(
    *,
    sentiment_level: dict,
    entropy_sentiment: dict,
    **_,
) -> dict:
    """Meta-signal: how trustworthy is this signal's narrative state?

    health = confidence_level * (1 - entropy_norm)
    where entropy_norm = entropy_sentiment / log(3)  ∈ [0, 1]

    High → high-confidence consensus (model can lean on this signal).
    Low  → either thin data or maximally split narrative.
    Missing whenever either input is missing.
    """
    if sentiment_level.get("is_missing") or entropy_sentiment.get("is_missing"):
        return _make_cell(None, True, debug={})
    conf = float(sentiment_level.get("confidence") or 0.0)
    h    = float(entropy_sentiment.get("value") or 0.0)
    h_norm = max(0.0, min(1.0, h / _LOG3))
    health = conf * (1.0 - h_norm)
    n = int(sentiment_level.get("n_samples") or 0)
    return _make_cell(health, False, n_samples=n,
                      debug={"conf": conf, "entropy_norm": h_norm})
