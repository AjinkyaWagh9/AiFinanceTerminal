"""Finnhub direct HTTP client.

OpenBB v4.7 does not ship a finnhub extension, so we call the REST API
directly. Free tier: 60 calls/min, covers Indian + US markets, returns
quotes + company news + basic fundamentals.

API key flow:
  1. Sign up free at https://finnhub.io
  2. Add to .env:   FINNHUB_API_KEY=...
  3. Restart the terminal — pickup is automatic.

Indian tickers on Finnhub use a `.NS` suffix (same as yfinance), so our
existing normalize_ticker output works directly.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_USER_AGENT = "FINTERMINAL/0.1"
_TIMEOUT_S = 10.0


def _api_key() -> str | None:
    return os.environ.get("FINNHUB_API_KEY") or None


def is_available() -> bool:
    return _api_key() is not None


def fetch_quote(ticker: str) -> dict | None:
    """Returns a normalized quote dict, or None if Finnhub is unavailable / fails."""
    key = _api_key()
    if not key:
        return None
    try:
        resp = httpx.get(
            f"{_BASE}/quote",
            params={"symbol": ticker, "token": key},
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_S,
        )
        if resp.status_code != 200:
            logger.warning("finnhub quote %s returned %s", ticker, resp.status_code)
            return None
        d = resp.json()
        # Finnhub free returns: c (current), d (change), dp (change%), h, l, o, pc, t (epoch)
        if not d or d.get("c") in (None, 0):
            return None
        return {
            "ticker": ticker,
            "as_of": datetime.now(timezone.utc),
            "last_price": d.get("c"),
            "change_pct": d.get("dp"),
            "volume": None,  # not in /quote — would need /stock/candle
            "market_cap": None,  # /stock/profile2 endpoint
            "provider": "finnhub",
            "raw": d,
        }
    except httpx.HTTPError as exc:
        logger.warning("finnhub quote failed for %s: %s", ticker, exc)
        return None


def fetch_news(ticker: str, limit: int = 20, days_back: int = 14) -> list[dict]:
    """Returns recent company news items, or [] if unavailable."""
    key = _api_key()
    if not key:
        return []
    try:
        # Finnhub company-news requires a date range; default last 14 days
        from datetime import timedelta

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days_back)
        resp = httpx.get(
            f"{_BASE}/company-news",
            params={
                "symbol": ticker,
                "from": start.isoformat(),
                "to": today.isoformat(),
                "token": key,
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_S,
        )
        if resp.status_code != 200:
            logger.warning("finnhub news %s returned %s", ticker, resp.status_code)
            return []
        items = resp.json() or []
        out: list[dict] = []
        for n in items[:limit]:
            ts = n.get("datetime")
            published = (
                datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else None
            )
            out.append({
                "id": str(n.get("id") or n.get("url") or n.get("headline")),
                "ticker": ticker,
                "source": n.get("source") or "Finnhub",
                "headline": n.get("headline"),
                "url": n.get("url"),
                "published_at": published,
                "body": n.get("summary"),
            })
        return out
    except httpx.HTTPError as exc:
        logger.warning("finnhub news failed for %s: %s", ticker, exc)
        return []
