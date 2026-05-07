"""Indian financial news via RSS feeds — Moneycontrol + Livemint.

RSS is the right move for Indian news: feeds are stable, public, no scraping,
no API key, no rate-limit concerns. Yahoo / Benzinga simply don't index Indian
business press deeply.

Strategy:
- Pull feeds in parallel (Moneycontrol Top News + Markets, Livemint Markets +
  Companies, Business Standard Markets).
- Filter items by case-insensitive substring match on company name.
- Need a ticker → company-name map; we keep a small curated table here for
  the Phase-1 watchlist scope. Phase 2 will swap this to NSE's official
  symbol list (`EQUITY_L.csv` from nseindia.com).
- Returns items normalized to the same shape as `openbb_client.fetch_news`.

Input: bare symbol (e.g. "RELIANCE") OR with .NS/.BO suffix — both handled.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = "FINTERMINAL/0.1 (+https://github.com/AjinkyaWagh9/Finance-Terminal)"
_TIMEOUT_S = 10.0
_FEED_TTL_S = 600.0  # cache feed payload for 10 min — feeds update every 5-15min anyway

# Public Indian financial RSS feeds. Add more here as needed.
_FEEDS = [
    ("Moneycontrol", "https://www.moneycontrol.com/rss/MCtopnews.xml"),
    ("Moneycontrol Markets", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Moneycontrol Business", "https://www.moneycontrol.com/rss/business.xml"),
    ("Moneycontrol LatestNews", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("Livemint Markets", "https://www.livemint.com/rss/markets"),
    ("Livemint Companies", "https://www.livemint.com/rss/companies"),
    # Economic Times feeds — high volume, per-stock mentions in market columns
    ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("ET Stocks", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("ET Earnings", "https://economictimes.indiatimes.com/markets/earnings/rssfeeds/8125277.cms"),
    ("ET Industry", "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms"),
    # Business Standard — disabled by default; SSL handshake times out from
    # this network. Re-enable if reachability is restored.
    # ("Business Standard Markets", "https://www.business-standard.com/rss/markets-106.rss"),
]

# Ticker → list of name aliases. Match if any alias is a case-insensitive
# whole-word substring of the headline. Phase 1: curated watchlist.
# Phase 2 swaps to nse EQUITY_L.csv autoload.
_TICKER_ALIASES: dict[str, list[str]] = {
    "RELIANCE": ["Reliance", "RIL", "Reliance Industries"],
    "INFY": ["Infosys", "Infy"],
    "TCS": ["TCS", "Tata Consultancy"],
    "HDFCBANK": ["HDFC Bank", "HDFCBank"],
    "ICICIBANK": ["ICICI Bank", "ICICI"],
    "SBIN": ["SBI", "State Bank of India", "State Bank"],
    "ITC": ["ITC"],
    "HINDUNILVR": ["HUL", "Hindustan Unilever"],
    "LT": ["L&T", "Larsen", "Larsen & Toubro"],
    "AXISBANK": ["Axis Bank"],
    "KOTAKBANK": ["Kotak Mahindra Bank", "Kotak Bank", "Kotak"],
    "BAJFINANCE": ["Bajaj Finance"],
    "ASIANPAINT": ["Asian Paints"],
    "MARUTI": ["Maruti Suzuki", "Maruti"],
    "TATASTEEL": ["Tata Steel"],
    "HCLTECH": ["HCL Tech", "HCLTech"],
    "WIPRO": ["Wipro"],
    "ADANIENT": ["Adani Enterprises", "Adani"],
    "NTPC": ["NTPC"],
    "ONGC": ["ONGC", "Oil and Natural Gas"],
}


def _bare_symbol(ticker: str) -> str:
    return ticker.upper().rsplit(".", 1)[0]


def _aliases_for(ticker: str) -> list[str]:
    """Return aliases for a ticker, falling back to the bare symbol itself."""
    sym = _bare_symbol(ticker)
    aliases = _TICKER_ALIASES.get(sym, [])
    if not aliases:
        # Use the bare symbol as a last resort. Imperfect (e.g. INFY can match
        # incidental words) but better than nothing for tickers not curated.
        return [sym]
    return aliases + [sym]


@lru_cache(maxsize=8)
def _cached_feed(url: str, _bucket: int) -> str | None:
    """Fetch a feed; cache by URL + 10-min bucket so we don't refetch within TTL."""
    try:
        resp = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT_S)
        if resp.status_code == 200:
            return resp.text
        logger.warning("RSS %s returned %s", url, resp.status_code)
    except httpx.HTTPError as exc:
        logger.warning("RSS fetch failed for %s: %s", url, exc)
    return None


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


def _parse_feed(xml_text: str, source_label: str) -> list[dict]:
    """Parse an RSS 2.0 feed; return normalized items."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("RSS parse error in %s: %s", source_label, exc)
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        pub = _parse_pubdate(item.findtext("pubDate"))
        desc = (item.findtext("description") or "").strip()
        # Strip HTML from description (RSS often has CDATA wrapped HTML)
        desc_clean = re.sub(r"<[^>]+>", "", desc).strip()
        items.append({
            "id": url or title,
            "source": source_label,
            "headline": title,
            "url": url,
            "published_at": pub,
            "body": desc_clean,
        })
    return items


def _matches(text: str, aliases: list[str]) -> bool:
    """Look for any alias in the text (headline + body), case-insensitive.

    Multi-word aliases ("Reliance Industries", "HDFC Bank") use plain substring
    match — punctuation around them is fine. Single-word aliases use word
    boundaries to avoid false positives like 'INFY' matching 'informatics'.
    """
    if not text:
        return False
    h = text.lower()
    for alias in aliases:
        a = alias.lower()
        if " " in a:
            if a in h:
                return True
        else:
            if re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", h):
                return True
    return False


def fetch_news(ticker: str, limit: int = 20) -> list[dict]:
    """Returns recent news items mentioning the given Indian ticker.

    Aggregates Moneycontrol + Livemint + Business Standard RSS feeds, filters
    by company-name aliases, dedupes by URL, sorts newest-first.
    """
    aliases = _aliases_for(ticker)
    bucket = int(time.time() // _FEED_TTL_S)

    seen_urls: set[str] = set()
    matched: list[dict] = []

    for label, url in _FEEDS:
        xml = _cached_feed(url, bucket)
        if xml is None:
            continue
        for item in _parse_feed(xml, label):
            blob = f"{item['headline']} {item.get('body', '')}"
            if not _matches(blob, aliases):
                continue
            url_key = item.get("url") or item["id"]
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)
            item["ticker"] = ticker
            matched.append(item)

    # Newest first
    matched.sort(
        key=lambda x: x["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return matched[:limit]
