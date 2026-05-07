"""Tests for news collector — mocks httpx, verifies normalization + resilience."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from finterminal.news.collector import Story, fetch_all


_SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Reliance Q4 beats estimates</title>
      <link>https://example.com/story1</link>
      <pubDate>Tue, 29 Apr 2026 06:00:00 +0000</pubDate>
      <description>Reliance Industries reported strong Q4 results.</description>
    </item>
    <item>
      <title>HDFC Bank flags MFI stress</title>
      <link>https://example.com/story2</link>
      <pubDate>Tue, 29 Apr 2026 07:00:00 +0000</pubDate>
      <description>HDFC Bank management flagged microfinance stress in earnings call.</description>
    </item>
  </channel>
</rss>"""


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


def test_fetch_all_returns_stories(monkeypatch):
    with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
        stories = fetch_all()
    assert len(stories) >= 2
    assert all(isinstance(s, Story) for s in stories)


def test_story_has_required_fields(monkeypatch):
    with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
        stories = fetch_all()
    s = stories[0]
    assert s.id
    assert s.source
    assert s.headline
    assert s.url


def test_one_feed_failure_does_not_crash(monkeypatch):
    """A timeout on one feed should not prevent other feeds from being returned."""
    import httpx
    call_count = 0

    def flaky_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.TimeoutException("timeout")
        return _mock_response(_SAMPLE_RSS)

    with patch("httpx.get", side_effect=flaky_get):
        stories = fetch_all()
    assert len(stories) >= 2  # remaining feeds still returned


def test_pubdate_parsed_to_datetime(monkeypatch):
    with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
        stories = fetch_all()
    for s in stories:
        if s.published_at is not None:
            assert isinstance(s.published_at, datetime)


def test_non_200_feed_skipped(monkeypatch):
    with patch("httpx.get", return_value=_mock_response("", status=403)):
        stories = fetch_all()
    assert stories == []
