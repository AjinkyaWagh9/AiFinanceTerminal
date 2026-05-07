"""Screener.in fundamentals scraper.

Closes the Indian-fundamentals gap that no free OpenBB provider fills.
Returns the same shape as `openbb_client.fetch_fundamentals` so it slots
into the existing fundamentals chain transparently.

Strategy:
- httpx + BeautifulSoup (lxml). Stable HTML; ~80% of pages parse identically.
- Try /consolidated/ first (group accounts, more complete) → fall back to
  bare /company/{symbol}/ (standalone) if 404.
- Per-process rate limit: 1 req/sec; identifies as FINTERMINAL.
- Per-process cache (lru_cache) — same ticker hit twice returns instantly.
- Failures per-field, not per-call: any unparseable field becomes None;
  the call still returns a partial dict so the supervisor has something.

URL pattern: https://www.screener.in/company/RELIANCE/consolidated/
Bare symbols only — strip .NS / .BO before passing in.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.screener.in/company"
_USER_AGENT = "FINTERMINAL/0.1 (+https://github.com/AjinkyaWagh9/Finance-Terminal)"
_TIMEOUT_S = 15.0
_MIN_INTERVAL_S = 1.0  # rate limit: ≤1 request/sec

_last_request_at: float = 0.0


def _rate_limit() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)
    _last_request_at = time.monotonic()


def _parse_number(s: str | None) -> float | None:
    """Parse Indian-formatted numerics into float.

    Conventions:
    - Strip ₹, commas, whitespace
    - Trailing % → divide by 100 (so '9.25%' → 0.0925, matching yfinance ratio convention)
    - Trailing 'Cr.' / 'Cr' → multiply by 10^7 (one crore)
    - Trailing 'L' / 'Lac' / 'Lakh' → multiply by 10^5 (one lakh)
    - '-' or empty → None
    """
    if s is None:
        return None
    s = s.strip().replace("₹", "").replace(",", "").strip()
    if not s or s == "-":
        return None
    if s.endswith("%"):
        try:
            return float(s.rstrip("%").strip()) / 100.0
        except ValueError:
            return None
    multiplier = 1.0
    if s.endswith("Cr."):
        s, multiplier = s[:-3].strip(), 1e7
    elif s.endswith("Cr"):
        s, multiplier = s[:-2].strip(), 1e7
    elif s.endswith("Lakh"):
        s, multiplier = s[:-4].strip(), 1e5
    elif s.endswith("Lac"):
        s, multiplier = s[:-3].strip(), 1e5
    try:
        return float(s) * multiplier
    except ValueError:
        return None


def _fetch_html(symbol_bare: str) -> tuple[str, str] | None:
    """Returns (html, url_used) or None if both consolidated + standalone 404."""
    for path in ("consolidated/", ""):
        url = f"{_BASE_URL}/{symbol_bare}/{path}"
        _rate_limit()
        try:
            resp = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT_S)
            if resp.status_code == 200:
                return resp.text, url
            if resp.status_code in (301, 302):
                # Screener occasionally redirects consolidated → standalone
                continue
            if resp.status_code == 404:
                continue
            logger.warning("screener.in %s returned %s", url, resp.status_code)
        except httpx.HTTPError as exc:
            logger.warning("screener.in fetch failed for %s: %s", url, exc)
    return None


def _parse_top_ratios(soup: BeautifulSoup) -> dict[str, Any]:
    """Returns the labelled <li> entries inside #top-ratios as raw strings."""
    out: dict[str, str] = {}
    block = soup.find(id="top-ratios")
    if not block:
        return out
    for li in block.find_all("li"):
        name = li.find("span", class_="name")
        val = li.find("span", class_="nowrap value")
        if name and val:
            out[name.get_text(strip=True)] = " ".join(val.get_text(strip=True).split())
    return out


def _parse_table_last_column(section: Any, row_label_starts: tuple[str, ...]) -> float | None:
    """Find a row whose first cell starts with any of the given labels and return
    the last numeric cell value parsed.

    Examples: ("Sales", "Sales+") → revenue; ("Net Profit",) → net income;
              ("Borrowings", "Borrowings+") → debt level.
    """
    if section is None:
        return None
    table = section.find("table")
    if table is None:
        return None
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
        if not cells:
            continue
        first = cells[0]
        if any(first.startswith(label) for label in row_label_starts):
            # Walk from the right until we find a parseable number
            for v in reversed(cells[1:]):
                parsed = _parse_number(v)
                if parsed is not None:
                    return parsed
    return None


@lru_cache(maxsize=64)
def fetch_fundamentals(symbol_bare: str) -> dict[str, Any]:
    """Fetch fundamentals for an Indian ticker from screener.in.

    Args:
        symbol_bare: Ticker without exchange suffix, e.g. "RELIANCE", "INFY", "HDFCBANK".

    Returns:
        Dict matching openbb_client.fetch_fundamentals shape:
            ticker, as_of, pe_ttm, eps_ttm, roe, roce, debt_to_equity,
            revenue_ttm, net_income_ttm, provider, raw

    Raises:
        RuntimeError: If both /consolidated/ and standalone pages fail.
    """
    from datetime import datetime, timezone

    fetched = _fetch_html(symbol_bare)
    if fetched is None:
        raise RuntimeError(f"screener.in: no page found for {symbol_bare}")
    html, url_used = fetched

    soup = BeautifulSoup(html, "lxml")

    top = _parse_top_ratios(soup)
    pe_ttm = _parse_number(top.get("Stock P/E"))
    roce = _parse_number(top.get("ROCE"))
    roe = _parse_number(top.get("ROE"))
    market_cap = _parse_number(top.get("Market Cap"))
    current_price = _parse_number(top.get("Current Price"))
    book_value = _parse_number(top.get("Book Value"))

    # Profit & Loss — Sales (revenue) and Net Profit (TTM in the rightmost column)
    pl_section = soup.find("section", id="profit-loss")
    revenue = _parse_table_last_column(pl_section, ("Sales", "Revenue"))
    # Sales row values are reported in ₹ Cr — multiply by 10^7 to get raw INR
    if revenue is not None:
        revenue *= 1e7
    net_profit = _parse_table_last_column(pl_section, ("Net Profit", "Net profit"))
    if net_profit is not None:
        net_profit *= 1e7

    # Balance sheet — for debt/equity
    bs_section = soup.find("section", id="balance-sheet")
    borrowings = _parse_table_last_column(bs_section, ("Borrowings",))
    equity_capital = _parse_table_last_column(bs_section, ("Equity Capital",))
    reserves = _parse_table_last_column(bs_section, ("Reserves",))

    debt_to_equity: float | None = None
    if borrowings is not None and equity_capital is not None and reserves is not None:
        denom = equity_capital + reserves
        if denom > 0:
            debt_to_equity = borrowings / denom

    # EPS = net_profit / shares_outstanding; shares = market_cap / current_price
    eps_ttm: float | None = None
    if net_profit is not None and market_cap and current_price:
        shares = market_cap / current_price
        if shares > 0:
            eps_ttm = net_profit / shares

    return {
        "ticker": symbol_bare,
        "as_of": datetime.now(timezone.utc).date(),
        "pe_ttm": pe_ttm,
        "eps_ttm": eps_ttm,
        "roe": roe,
        "roce": roce,
        "debt_to_equity": debt_to_equity,
        "revenue_ttm": revenue,
        "net_income_ttm": net_profit,
        "provider": "screener.in",
        "raw": {
            "url": url_used,
            "top_ratios": top,
            "market_cap": market_cap,
            "current_price": current_price,
            "book_value": book_value,
            "borrowings": borrowings,
            "equity_capital": equity_capital,
            "reserves": reserves,
        },
    }
