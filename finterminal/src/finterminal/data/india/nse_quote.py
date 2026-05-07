"""NSE direct quote API. Fallback for yfinance throttle (Q-5).

NSE's public API requires a session cookie before serving quote JSON.
The standard pattern: GET nseindia.com/get-quotes/equity?symbol=X first
to seed cookies, then GET /api/quote-equity?symbol=X.

NSE blocks default httpx User-Agent — must look like a browser.

Returns the same dict shape as openbb_client.fetch_quote so the
upstream caller can use the result interchangeably.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nseindia.com"
_WARMUP_PATH = "/get-quotes/equity"
_API_PATH = "/api/quote-equity"
_REQUEST_TIMEOUT_S = 15.0

# Browser-like User-Agent. NSE blocks default `python-httpx/...` UA.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/get-quotes/equity",
}


class NSEQuoteError(Exception):
    """Raised when NSE direct quote fetch fails (HTTP / parse / shape)."""


def _strip_exchange_suffix(symbol: str) -> str:
    """RELIANCE.NS -> RELIANCE; reliance.bo -> RELIANCE."""
    s = symbol.upper().strip()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s[:-3]
    return s


def fetch_nse_quote(ticker: str) -> dict:
    """Fetch a quote from NSE's public API.

    Two-step: warmup GET (seeds session cookies) → API GET (returns JSON).
    Raises NSEQuoteError on any failure path.

    Returns dict with the same shape as openbb_client.fetch_quote:
      ticker, as_of, last_price, change_pct, volume, market_cap, provider, raw.
    """
    symbol = _strip_exchange_suffix(ticker)

    try:
        with httpx.Client(
            timeout=_REQUEST_TIMEOUT_S,
            headers=_BROWSER_HEADERS,
            follow_redirects=True,
        ) as client:
            # Step 1: warmup — seeds session cookies
            warmup_url = f"{_BASE_URL}{_WARMUP_PATH}?symbol={symbol}"
            client.get(warmup_url)

            # Step 2: actual API call (cookies travel automatically on the same client)
            api_url = f"{_BASE_URL}{_API_PATH}?symbol={symbol}"
            resp = client.get(api_url)
    except httpx.ConnectError as e:
        raise NSEQuoteError(f"Cannot reach NSE ({_BASE_URL}): connect error: {e}") from e
    except httpx.TimeoutException as e:
        raise NSEQuoteError(f"NSE request timed out after {_REQUEST_TIMEOUT_S}s: {e}") from e

    if resp.status_code == 429:
        raise NSEQuoteError(f"NSE returned 429 (throttle); retry later. Body: {resp.text[:200]}")
    if resp.status_code == 404:
        raise NSEQuoteError(f"NSE returned 404 for symbol {symbol!r} (not listed?)")
    if resp.status_code >= 400:
        raise NSEQuoteError(f"NSE returned HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as e:
        raise NSEQuoteError(f"NSE returned non-JSON body: {resp.text[:200]}") from e

    price_info = data.get("priceInfo")
    if not price_info or not isinstance(price_info, dict):
        raise NSEQuoteError(
            f"NSE response missing priceInfo block for {symbol!r}; got keys: {list(data.keys())}"
        )

    last_price = price_info.get("lastPrice")
    change_pct = price_info.get("pChange")
    volume = price_info.get("totalTradedVolume")
    if volume is None:
        # Fallback: marketDeptOrderBook.tradeInfo.totalTradedVolume
        trade_info = (data.get("marketDeptOrderBook") or {}).get("tradeInfo") or {}
        volume = trade_info.get("totalTradedVolume")

    # market_cap: prefer the totalMarketCap field (in lakhs) when present;
    # else compute from issuedSize × lastPrice
    market_cap = None
    trade_info = (data.get("marketDeptOrderBook") or {}).get("tradeInfo") or {}
    raw_mcap = trade_info.get("totalMarketCap")
    if raw_mcap is not None:
        # NSE reports totalMarketCap in lakhs (1 lakh = 100,000)
        try:
            market_cap = float(raw_mcap) * 100_000
        except (TypeError, ValueError):
            market_cap = None
    if market_cap is None:
        issued = (data.get("securityInfo") or {}).get("issuedSize")
        if issued is not None and last_price is not None:
            try:
                market_cap = float(issued) * float(last_price)
            except (TypeError, ValueError):
                market_cap = None

    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc),
        "last_price": float(last_price) if last_price is not None else None,
        "change_pct": float(change_pct) if change_pct is not None else None,
        "volume": int(volume) if volume is not None else None,
        "market_cap": market_cap,
        "provider": "nse",
        "raw": data,
    }
