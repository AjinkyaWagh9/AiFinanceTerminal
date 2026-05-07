"""Tests for tagger — alias matching, rapidfuzz fallback, sector lookup."""
from finterminal.news.collector import Story
from finterminal.news.tagger import tag


def _story(headline: str, body: str = "") -> Story:
    return Story(id="x", source="Test", headline=headline, body=body, url="x")


def test_reliance_tagged_by_alias():
    stories = [_story("Reliance Industries Q4 beats estimates")]
    result = tag(stories)
    assert "RELIANCE" in result[0].tickers
    assert "Energy" in result[0].sectors


def test_hdfc_bank_tagged():
    stories = [_story("HDFC Bank microfinance stress weighs on margins")]
    result = tag(stories)
    assert "HDFCBANK" in result[0].tickers
    assert "Banking" in result[0].sectors


def test_rapidfuzz_catches_misspelling():
    """'Hindustan Unliever' (typo) should still tag HINDUNILVR."""
    stories = [_story("Hindustan Unliever sales growth disappoints")]
    result = tag(stories, min_score=85)
    assert "HINDUNILVR" in result[0].tickers


def test_cap_five_tickers():
    """A headline mentioning 7+ companies should not tag more than 5 tickers."""
    headline = (
        "Reliance HDFC Bank TCS Infosys Wipro HCL Bajaj Finance all report Q4 results"
    )
    stories = [_story(headline)]
    result = tag(stories)
    assert len(result[0].tickers) <= 5


def test_unrelated_headline_no_crash():
    stories = [_story("RBI keeps repo rate unchanged at 6.5 percent")]
    result = tag(stories)
    assert isinstance(result[0].tickers, list)


def test_returns_same_count():
    stories = [_story(f"Story {i}") for i in range(5)]
    result = tag(stories)
    assert len(result) == 5
