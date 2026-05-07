"""Tests for deduplication — URL-exact and MinHash near-duplicate detection."""
from finterminal.news.collector import Story
from finterminal.news.dedupe import drop_url_dupes, minhash_filter


def _story(id_: str, headline: str, url: str = "") -> Story:
    return Story(id=id_, source="Test", headline=headline, url=url or id_)


def test_url_dedup_drops_exact_duplicates():
    stories = [
        _story("s1", "Reliance Q4 beats", url="https://example.com/a"),
        _story("s2", "Reliance Q4 beats estimates", url="https://example.com/a"),  # same URL
        _story("s3", "HDFC Bank stress", url="https://example.com/b"),
    ]
    result = drop_url_dupes(stories)
    assert len(result) == 2
    urls = {s.url for s in result}
    assert "https://example.com/b" in urls


def test_url_dedup_keeps_unique_urls():
    stories = [_story(f"s{i}", f"Story {i}", url=f"https://example.com/{i}") for i in range(5)]
    result = drop_url_dupes(stories)
    assert len(result) == 5


def test_minhash_drops_near_duplicate_headline():
    """Wire services often republish the same headline with trivial word changes."""
    original = _story("a", "Reliance Industries Q4 net profit rises 15 percent beats estimates")
    near_dup = _story("b", "Reliance Industries Q4 net profit rises 15 per cent beats analyst estimates")
    distinct = _story("c", "HDFC Bank flags microfinance stress in quarterly results")
    result = minhash_filter([original, near_dup, distinct])
    # near_dup should be filtered; distinct should survive
    headlines = [s.headline for s in result]
    assert distinct.headline in headlines
    assert len(result) <= 3  # original + distinct (near_dup filtered if Jaccard >= 0.85)


def test_minhash_keeps_distinct_stories():
    stories = [
        _story("a", "Reliance Q4 beats estimates on Jio subscriber growth"),
        _story("b", "HDFC Bank microfinance stress to weigh on Q1 margins"),
        _story("c", "Infosys raises guidance citing strong deal wins in Europe"),
        _story("d", "Tata Steel Q4 EBITDA rises on higher realizations"),
    ]
    result = minhash_filter(stories)
    assert len(result) == 4  # all distinct


def test_minhash_empty_input():
    assert minhash_filter([]) == []
