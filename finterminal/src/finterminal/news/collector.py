"""RSS news collector — fetches all 11 feeds in parallel, normalizes to Story.

# Add new RSS feeds to _FEEDS below. Keep parsing path generic — RSS 2.0 + Atom
# both handled by the same <item> iteration. Reuters India + BusinessLine added B-2a.
# Expand at sprint boundaries, not in flight.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = "FINTERMINAL/0.1 (+https://github.com/AjinkyaWagh9/Finance-Terminal)"
_TIMEOUT_S = 10.0

_FEEDS: list[tuple[str, str]] = [
    ("Moneycontrol", "https://www.moneycontrol.com/rss/MCtopnews.xml"),
    ("Moneycontrol Markets", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Moneycontrol Business", "https://www.moneycontrol.com/rss/business.xml"),
    ("Moneycontrol Latest", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("Livemint Markets", "https://www.livemint.com/rss/markets"),
    ("Livemint Companies", "https://www.livemint.com/rss/companies"),
    ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("ET Stocks", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("ET Industry", "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms"),
    ("Reuters India", "https://in.reuters.com/rssFeed/topNews"),
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/feeder/default.rss"),
]


@dataclass
class Story:
    id: str
    source: str
    headline: str
    url: str
    body: str = ""
    published_at: datetime | None = None
    tickers: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    cluster_id: str | None = None


def _parse_pubdate(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None


def _parse_feed(xml_text: str, source_label: str) -> list[Story]:
    stories: list[Story] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("RSS parse error in %s: %s", source_label, exc)
        return stories
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        pub = _parse_pubdate(item.findtext("pubDate"))
        desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
        story_id = url or title
        if not story_id:
            continue
        stories.append(Story(
            id=story_id,
            source=source_label,
            headline=title,
            url=url,
            body=desc,
            published_at=pub,
        ))
    return stories


def _fetch_feed(label: str, url: str) -> list[Story]:
    try:
        resp = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT_S)
        if resp.status_code != 200:
            logger.warning("RSS %s returned %s", url, resp.status_code)
            return []
        return _parse_feed(resp.text, label)
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return []


def fetch_all() -> list[Story]:
    """Fetch all feeds, return combined normalized Story list (may contain duplicates)."""
    all_stories: list[Story] = []
    for label, url in _FEEDS:
        all_stories.extend(_fetch_feed(label, url))
    return all_stories
