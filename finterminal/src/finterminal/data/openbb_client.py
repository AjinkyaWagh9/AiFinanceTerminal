"""Thin wrapper around OpenBB SDK. Defensive — providers vary in field names.

Phase 1 uses yfinance (free, no PAT required). Phase 3 will add Finnhub
for US fundamentals via env-var-keyed config.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

# yfinance computes its default range from the system clock; if that clock is
# ahead of where real market data ends, the default window slides into the future
# and the response is empty. Always pass an explicit start_date 2 years back so
# the request window overlaps available data.
_HISTORICAL_LOOKBACK_DAYS = 730

logger = logging.getLogger(__name__)

# Provider chains, tried in order; failures fall through silently to the next.
# - Quotes & fundamentals: yfinance covers India + US for free with clean
#   pe_ttm / eps_ttm fields. FMP free tier blocks .NS (Premium endpoint)
#   AND its `metrics` returns derived ratios but not raw PE/EPS — adding it
#   to fundamentals chain produces None for headline numbers. Defer FMP
#   enrichment to a Phase 3 multi-endpoint US strategy.
# - News: Benzinga gives high-quality US-equity headlines; .NS / .BO will
#   fail and degrade to yfinance automatically.
_QUOTE_PROVIDERS = ["yfinance", "nse"]
_FUNDAMENTAL_PROVIDERS = ["yfinance"]
_NEWS_PROVIDERS = ["benzinga", "yfinance"]


def _to_dict(obj: Any) -> dict:
    """OpenBB v4 returns Pydantic models; normalize to dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return dict(obj)


def _first_present(d: dict, *keys: str, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _fetch_via_yfinance(ticker: str) -> dict:
    """Fetch quote via OpenBB's yfinance provider.

    Tries the live quote endpoint first; on empty/failure, falls back to
    the historical bars endpoint (more stable under Yahoo's cookie/crumb
    auth flakiness) and synthesizes a quote from the last two closes.

    Raises RuntimeError on all-paths-failed.
    """
    from openbb import obb  # imported lazily — OpenBB has slow cold start

    provider = "yfinance"
    last_err: Exception | None = None

    try:
        resp = obb.equity.price.quote(ticker, provider=provider)
        results = resp.results or []
        if results:
            d = _to_dict(results[0])
            return {
                "ticker": ticker,
                "as_of": datetime.now(timezone.utc),
                "last_price": _first_present(d, "last_price", "price", "close", "regular_market_price"),
                "change_pct": _first_present(d, "change_percent", "regular_market_change_percent"),
                "volume": _first_present(d, "volume", "regular_market_volume"),
                "market_cap": _first_present(d, "market_cap"),
                "provider": provider,
                "raw": d,
            }
        last_err = ValueError(f"empty quote from {provider}")
    except Exception as exc:  # noqa: BLE001
        last_err = exc
        logger.warning("quote fetch via %s failed for %s: %s", provider, ticker, exc)

    # Historical bars fallback for Yahoo flakiness.
    try:
        start = (datetime.now(timezone.utc).date() - timedelta(days=_HISTORICAL_LOOKBACK_DAYS)).isoformat()
        hist = obb.equity.price.historical(ticker, provider=provider, start_date=start)
        rows = hist.results or []
        if rows:
            last = _to_dict(rows[-1])
            prev = _to_dict(rows[-2]) if len(rows) >= 2 else None
            last_close = last.get("close")
            prev_close = prev.get("close") if prev else None
            change_pct = (
                (last_close - prev_close) / prev_close * 100
                if last_close is not None and prev_close
                else None
            )
            return {
                "ticker": ticker,
                "as_of": datetime.now(timezone.utc),
                "last_price": last_close,
                "change_pct": change_pct,
                "volume": last.get("volume"),
                "market_cap": None,
                "provider": f"{provider}/historical",
                "raw": last,
            }
        last_err = ValueError(f"empty historical from {provider}")
    except Exception as exc:  # noqa: BLE001
        last_err = exc
        logger.warning("historical fallback via %s failed for %s: %s", provider, ticker, exc)

    raise RuntimeError(f"yfinance failed for {ticker}: {last_err!r}")


def fetch_quote(ticker: str) -> dict:
    """Returns latest quote: ticker, as_of, last_price, change_pct, volume, market_cap, raw.

    Provider chain (Q-5):
      1. yfinance — universal coverage (India + US + EU); flaky under throttle
      2. nse — direct NSE API; .NS / .BO only; no auth, used as fallback
    """
    last_err: Exception | None = None
    for provider in _QUOTE_PROVIDERS:
        if provider == "yfinance":
            try:
                return _fetch_via_yfinance(ticker)
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue

        if provider == "nse":
            if not _is_indian_ticker(ticker):
                continue
            try:
                from .india.nse_quote import fetch_nse_quote
                logger.info("falling through to NSE direct API for %s", ticker)
                return fetch_nse_quote(ticker)
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("NSE direct fetch failed for %s: %s", ticker, exc)
                continue

    raise RuntimeError(f"All providers failed for {ticker}: {last_err!r}")


def _is_indian_ticker(ticker: str) -> bool:
    return ticker.upper().endswith((".NS", ".BO"))


def fetch_fundamentals(ticker: str) -> dict:
    """Returns key ratios. Field availability varies by provider.

    Indian tickers (.NS / .BO) try screener.in first — clean PE/ROCE/ROE/D-E
    coverage that yfinance lacks. yfinance is the universal fallback.
    """
    last_err: Exception | None = None

    # India-specific path: try screener.in scraper first
    if _is_indian_ticker(ticker):
        try:
            from .india.screener_in import fetch_fundamentals as fetch_screener

            symbol_bare = ticker.upper().rsplit(".", 1)[0]
            data = fetch_screener(symbol_bare)
            # If at least PE or ROE came back, treat as success; supervisor
            # always benefits from partial data.
            if data.get("pe_ttm") is not None or data.get("roe") is not None:
                # Restore the .NS/.BO suffix on the ticker field for downstream consistency
                data["ticker"] = ticker
                return data
            last_err = ValueError("screener.in returned no usable fields")
        except Exception as exc:  # noqa: BLE001 — fall through to yfinance
            last_err = exc
            logger.warning("screener.in fundamentals failed for %s: %s", ticker, exc)

    from openbb import obb

    for provider in _FUNDAMENTAL_PROVIDERS:
        try:
            resp = obb.equity.fundamental.metrics(ticker, provider=provider)
            results = resp.results or []
            if not results:
                last_err = ValueError(f"empty fundamentals from {provider}")
                continue
            d = _to_dict(results[0])
            return {
                "ticker": ticker,
                "as_of": datetime.now(timezone.utc).date(),
                "pe_ttm": _first_present(d, "pe_ratio", "trailing_pe", "price_to_earnings"),
                "eps_ttm": _first_present(d, "eps", "trailing_eps"),
                "roe": _first_present(d, "return_on_equity", "roe"),
                "roce": _first_present(d, "return_on_capital_employed", "roce"),
                "debt_to_equity": _first_present(d, "debt_to_equity"),
                "revenue_ttm": _first_present(d, "revenue", "trailing_revenue"),
                "net_income_ttm": _first_present(d, "net_income"),
                "provider": provider,
                "raw": d,
            }
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning("fundamentals fetch via %s failed for %s: %s", provider, ticker, exc)
    raise RuntimeError(f"All providers failed for {ticker}: {last_err!r}")


def fetch_news(ticker: str, limit: int = 20) -> list[dict]:
    """Returns recent news items normalized to our schema.

    Indian tickers (.NS / .BO) try the india_news_rss aggregator first
    (Moneycontrol + Livemint + ET feeds, alias-matched). Falls back to
    OpenBB providers (Benzinga → yfinance) if RSS yields nothing.
    """
    if _is_indian_ticker(ticker):
        try:
            from .india.news_rss import fetch_news as fetch_india_rss

            items = fetch_india_rss(ticker, limit=limit)
            if items:
                return items
            logger.info("india RSS yielded no matches for %s; trying Finnhub/OpenBB", ticker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("india RSS failed for %s: %s", ticker, exc)

    # Finnhub (free, optional) — if FINNHUB_API_KEY is set; covers India + US
    try:
        from . import finnhub_client

        if finnhub_client.is_available():
            items = finnhub_client.fetch_news(ticker, limit=limit)
            if items:
                return items
    except Exception as exc:  # noqa: BLE001
        logger.warning("finnhub news failed for %s: %s", ticker, exc)

    from openbb import obb

    # Most providers don't tag news items with their own brand name in a
    # `source` field — Benzinga is all "Benzinga", yfinance carries the
    # underlying publisher. Use a per-provider default when the payload omits it.
    _provider_default_source = {
        "benzinga": "Benzinga",
        "tiingo": "Tiingo",
    }

    last_err: Exception | None = None
    for provider in _NEWS_PROVIDERS:
        try:
            resp = obb.news.company(symbol=ticker, limit=limit, provider=provider)
            results = resp.results or []
            items = []
            for n in results:
                d = _to_dict(n)
                items.append({
                    "id": _first_present(d, "id", "url", "title"),
                    "ticker": ticker,
                    "source": _first_present(
                        d, "source", "publisher",
                        default=_provider_default_source.get(provider, provider),
                    ),
                    "headline": _first_present(d, "title", "headline"),
                    "url": _first_present(d, "url"),
                    "published_at": _first_present(d, "date", "published", "published_at"),
                    "body": _first_present(d, "text", "summary", "body"),
                })
            return items
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning("news fetch via %s failed for %s: %s", provider, ticker, exc)
    raise RuntimeError(f"All providers failed for {ticker}: {last_err!r}")
