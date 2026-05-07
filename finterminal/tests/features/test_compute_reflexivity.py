from __future__ import annotations
import math
from datetime import datetime, timedelta

import pytest

from finterminal.data.duckdb_store import connect

TS = datetime(2026, 5, 1, 10, 0)
EXPECTED_VERSION = "reflexivity_v1_vader_decay_0.5"


def _seed_story(conn, headline: str, pub_at: datetime,
                ticker: str = "TCS", fetched_at: datetime | None = None) -> None:
    import uuid
    story_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT OR IGNORE INTO news_stories
            (id, url, source, headline, body, published_at, fetched_at, tickers, sectors)
        VALUES (?, ?, 'test', ?, NULL, ?, ?, ?, [])
        """,
        [story_id, f"http://x/{headline[:30]}", headline, pub_at,
         fetched_at if fetched_at is not None else pub_at, [ticker]],
    )


# ── sentiment_level ──────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import (
    compute_sentiment_level,
    FEATURE_VERSION,
)


def test_sentiment_level_version_constant_matches_expected():
    assert FEATURE_VERSION == EXPECTED_VERSION


def test_sentiment_level_missing_when_no_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True and cell["value"] is None
    assert cell["feature_version"] == FEATURE_VERSION


def test_sentiment_level_missing_when_fewer_than_5_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    for i in range(4):
        _seed_story(conn, f"good news {i}", TS - timedelta(days=i))
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_sentiment_level_returns_value_with_5_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    positive_headlines = [
        "strong profit growth rally",
        "company posts record earnings beat",
        "shares surge on upbeat outlook",
        "revenue jumps as demand stays robust",
        "management raises guidance for the year",
        "stock soars after blowout quarter",
    ]
    for i in range(5):
        _seed_story(conn, positive_headlines[i % len(positive_headlines)], TS - timedelta(hours=i * 12))
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is False
    assert isinstance(cell["value"], float)
    assert cell["n_samples"] == 5
    assert cell["confidence"] == pytest.approx(0.5)
    assert cell["feature_version"] == FEATURE_VERSION
    assert cell["normalized"] is False
    assert "debug" in cell


def test_sentiment_level_confidence_caps_at_1(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    positive_headlines = [
        "strong profit growth rally",
        "company posts record earnings beat",
        "shares surge on upbeat outlook",
        "revenue jumps as demand stays robust",
        "management raises guidance for the year",
        "stock soars after blowout quarter",
        "earnings surprise to the upside today",
        "bullish outlook boosts investor confidence",
        "strong cash flow supports growth plans",
        "acquisition deal unlocks significant value",
        "margin expansion delights wall street",
        "dividend hike signals management confidence",
    ]
    # Use 12 unique headlines so unique_ratio = 12/12 = 1.0
    for i in range(12):
        _seed_story(conn, positive_headlines[i], TS - timedelta(hours=i * 6))
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["confidence"] == pytest.approx(1.0)


def test_sentiment_level_ignores_future_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    positive_headlines = [
        "strong profit growth rally",
        "company posts record earnings beat",
        "shares surge on upbeat outlook",
        "revenue jumps as demand stays robust",
        "management raises guidance for the year",
        "stock soars after blowout quarter",
    ]
    for i in range(5):
        _seed_story(conn, positive_headlines[i % len(positive_headlines)], TS - timedelta(hours=i * 12))
    cell_before = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    for i in range(10):
        _seed_story(conn, f"crash bankruptcy crisis {i}", TS + timedelta(days=i + 1))
    cell_after = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell_before["value"] == pytest.approx(cell_after["value"])


def test_sentiment_level_excludes_late_arriving_articles(tmp_path):
    """Article published BEFORE ts but FETCHED AFTER ts must be excluded.
    Without this, ingestion-time leakage poisons replay."""
    conn = connect(str(tmp_path / "t.duckdb"))
    # 5 valid articles (published+fetched before ts)
    positive_headlines = [
        "strong profit growth rally",
        "company posts record earnings beat",
        "shares surge on upbeat outlook",
        "revenue jumps as demand stays robust",
        "management raises guidance for the year",
        "stock soars after blowout quarter",
    ]
    for i in range(5):
        _seed_story(conn, positive_headlines[i % len(positive_headlines)], TS - timedelta(hours=i * 12))
    cell_clean = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)

    # Now insert "late-arriving" articles: published BEFORE ts (eligible by
    # naive snapshot) but fetched AFTER ts. They must NOT change the value.
    for i in range(20):
        _seed_story(
            conn,
            f"hidden disaster bankruptcy crash {i}",
            pub_at=TS - timedelta(hours=1),
            fetched_at=TS + timedelta(days=1 + i),
        )
    cell_with_late = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell_clean["value"] == pytest.approx(cell_with_late["value"]), (
        "late-arriving articles leaked into snapshot — fetched_at filter missing")


def test_sentiment_level_ignores_other_tickers(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    positive_headlines = [
        "strong profit growth rally",
        "company posts record earnings beat",
        "shares surge on upbeat outlook",
        "revenue jumps as demand stays robust",
        "management raises guidance for the year",
        "stock soars after blowout quarter",
    ]
    for i in range(5):
        _seed_story(conn, positive_headlines[i % len(positive_headlines)], TS - timedelta(hours=i * 12), ticker="INFY")
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


# ── sentiment_delta ──────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import compute_sentiment_delta


def _seed_positive_window(conn, ts_anchor, ticker="TCS", count=6):
    positive_headlines = [
        "strong profit growth rally",
        "company posts record earnings beat",
        "shares surge on upbeat outlook",
        "revenue jumps as demand stays robust",
        "management raises guidance for the year",
        "stock soars after blowout quarter",
    ]
    for i in range(count):
        _seed_story(conn, positive_headlines[i % len(positive_headlines)],
                    ts_anchor - timedelta(hours=i * 10), ticker=ticker)


def _seed_negative_window(conn, ts_anchor, ticker="TCS", count=6):
    negative_headlines = [
        "loss widens as costs rise sharply",
        "shares plunge on weak guidance",
        "company faces bankruptcy risk amid debt crisis",
        "revenue collapses missing all forecasts",
        "stock crashes after dismal quarter",
        "credit downgrade deepens default fears",
    ]
    for i in range(count):
        _seed_story(conn, negative_headlines[i % len(negative_headlines)],
                    ts_anchor - timedelta(hours=i * 10), ticker=ticker)


def test_sentiment_delta_missing_when_current_window_fails(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_positive_window(conn, TS - timedelta(days=7))
    cell = compute_sentiment_delta(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_sentiment_delta_missing_when_prior_window_fails(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_positive_window(conn, TS)
    cell = compute_sentiment_delta(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_sentiment_delta_positive_when_sentiment_improves(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_negative_window(conn, TS - timedelta(days=7))
    _seed_positive_window(conn, TS)
    cell = compute_sentiment_delta(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is False
    assert cell["value"] > 0
    assert cell["feature_version"] == FEATURE_VERSION


def test_sentiment_delta_negative_when_sentiment_deteriorates(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_positive_window(conn, TS - timedelta(days=7))
    _seed_negative_window(conn, TS)
    cell = compute_sentiment_delta(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is False
    assert cell["value"] < 0


# ── entropy_sentiment ────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import compute_entropy_sentiment


def test_entropy_missing_when_insufficient_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    cell = compute_entropy_sentiment(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_entropy_max_when_three_equal_bins(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    pos = ["record profits soar strong earnings growth rally",
           "outstanding revenue beats expectations significantly higher"]
    neu = ["company held annual general meeting today",
           "board approved routine agenda items quarterly"]
    neg = ["massive loss debt default bankruptcy crisis collapse",
           "severe decline revenue miss disappointing earnings crash"]
    for h in pos + neu + neg:
        _seed_story(conn, h, TS - timedelta(hours=1))
    cell = compute_entropy_sentiment(conn, ticker="TCS", ts_emitted=TS)
    if not cell["is_missing"]:
        assert cell["value"] <= math.log(3) + 0.01
        assert cell["n_samples"] == 6
        assert cell["feature_version"] == FEATURE_VERSION


def test_entropy_is_deterministic(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    pos = ["record profits soar strong earnings growth rally",
           "outstanding revenue beats expectations significantly higher"]
    neg = ["massive loss debt default bankruptcy crisis collapse",
           "severe decline revenue miss disappointing earnings crash"]
    neu = ["company held annual general meeting today",
           "board approved routine agenda items quarterly"]
    for h in pos + neg + neu:
        _seed_story(conn, h, TS - timedelta(hours=1))
    a = compute_entropy_sentiment(conn, ticker="TCS", ts_emitted=TS)
    for i in range(5):
        _seed_story(conn, f"future news {i}", TS + timedelta(days=i + 1))
    b = compute_entropy_sentiment(conn, ticker="TCS", ts_emitted=TS)
    assert a["value"] == b["value"]
    assert a["is_missing"] == b["is_missing"]


# ── entropy_change ───────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import compute_entropy_change


def test_entropy_change_missing_when_either_window_fails(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    headlines = ["record profits soar strong earnings growth rally x",
                 "outstanding revenue beats expectations significantly x",
                 "massive loss debt default bankruptcy crisis x",
                 "severe decline miss disappointing earnings x",
                 "mixed results moderate neutral report x",
                 "company board meeting schedule x"]
    for h in headlines:
        _seed_story(conn, h, TS - timedelta(hours=1))
    cell = compute_entropy_change(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_entropy_change_is_deterministic(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    boundary = TS - timedelta(days=7)
    base = [
        ("record profits soar strong growth A", boundary - timedelta(hours=2)),
        ("outstanding revenue beats B",          boundary - timedelta(hours=4)),
        ("massive loss default C",               boundary - timedelta(hours=6)),
        ("severe decline miss D",                boundary - timedelta(hours=8)),
        ("company held meeting E",               boundary - timedelta(hours=10)),
        ("board approved agenda F",              boundary - timedelta(hours=12)),
        ("record profits soar strong 1",         TS - timedelta(hours=2)),
        ("outstanding revenue beats 2",          TS - timedelta(hours=4)),
        ("strong profit growth 3",               TS - timedelta(hours=6)),
        ("earnings beat forecast 4",             TS - timedelta(hours=8)),
        ("market rally strong 5",                TS - timedelta(hours=10)),
        ("revenue surge targets 6",              TS - timedelta(hours=12)),
    ]
    for h, ts in base:
        _seed_story(conn, h, ts)
    a = compute_entropy_change(conn, ticker="TCS", ts_emitted=TS)
    for i in range(5):
        _seed_story(conn, f"future {i}", TS + timedelta(days=i + 1))
    b = compute_entropy_change(conn, ticker="TCS", ts_emitted=TS)
    assert a["value"] == b["value"]
    assert a["is_missing"] == b["is_missing"]


# ── feature_health ───────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import compute_feature_health


def test_feature_health_missing_when_inputs_missing():
    sl = {"value": None, "is_missing": True, "confidence": 0.0,
          "feature_version": EXPECTED_VERSION}
    es = {"value": None, "is_missing": True, "confidence": 0.0,
          "feature_version": EXPECTED_VERSION}
    cell = compute_feature_health(sentiment_level=sl, entropy_sentiment=es)
    assert cell["is_missing"] is True
    assert cell["value"] is None


def test_feature_health_high_when_high_confidence_low_entropy():
    sl = {"value": 0.6, "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    es = {"value": 0.0, "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    cell = compute_feature_health(sentiment_level=sl, entropy_sentiment=es)
    assert cell["is_missing"] is False
    assert cell["value"] == pytest.approx(1.0)


def test_feature_health_zero_when_max_entropy():
    sl = {"value": 0.6, "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    es = {"value": math.log(3), "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    cell = compute_feature_health(sentiment_level=sl, entropy_sentiment=es)
    assert cell["value"] == pytest.approx(0.0, abs=1e-9)


def test_feature_health_zero_when_zero_confidence():
    sl = {"value": 0.6, "is_missing": False, "confidence": 0.0,
          "feature_version": EXPECTED_VERSION}
    es = {"value": 0.0, "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    cell = compute_feature_health(sentiment_level=sl, entropy_sentiment=es)
    assert cell["value"] == pytest.approx(0.0)
