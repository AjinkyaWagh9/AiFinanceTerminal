"""Quote-provider fallthrough test (Q-5).

When yfinance throttles for an Indian ticker, fetch_quote() must fall
through to the NSE direct API and return its result without raising.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from finterminal.data import openbb_client


def _yfinance_raises(*_, **__):
    """Stand-in for OpenBB obb.equity.price.quote() under throttle."""
    raise RuntimeError("[Empty] -> No results found. Try adjusting the query parameters.")


_NSE_RESULT = {
    "ticker": "RELIANCE.NS",
    "as_of": "2026-04-29T11:30:00+00:00",
    "last_price": 1421.00,
    "change_pct": 2.27,
    "volume": 8281000,
    "market_cap": 19232845_000_000,
    "provider": "nse",
    "raw": {"priceInfo": {"lastPrice": 1421.00}},
}


def test_fetch_quote_falls_through_to_nse_when_yfinance_throttled():
    """Indian ticker + yfinance failing → NSE result returned."""
    # Patch the yfinance path to always raise.
    with patch("finterminal.data.openbb_client._fetch_via_yfinance", _yfinance_raises):
        with patch(
            "finterminal.data.india.nse_quote.fetch_nse_quote",
            return_value=_NSE_RESULT,
        ):
            result = openbb_client.fetch_quote("RELIANCE.NS")

    assert result["provider"] == "nse"
    assert result["last_price"] == 1421.00
    assert result["ticker"] == "RELIANCE.NS"


def test_fetch_quote_skips_nse_for_non_indian_tickers():
    """NSE only covers .NS / .BO. For US tickers, yfinance failure is final."""
    nse_called = False

    def _nse_should_not_be_called(*_, **__):
        nonlocal nse_called
        nse_called = True
        return _NSE_RESULT

    with patch("finterminal.data.openbb_client._fetch_via_yfinance", _yfinance_raises):
        with patch(
            "finterminal.data.india.nse_quote.fetch_nse_quote",
            _nse_should_not_be_called,
        ):
            with pytest.raises(RuntimeError, match="All providers failed"):
                openbb_client.fetch_quote("AAPL")

    assert not nse_called, "NSE was called for a non-Indian ticker"


def test_fetch_quote_propagates_real_error_when_both_providers_fail():
    """yfinance throttled + NSE down → propagate."""
    def _nse_also_fails(*_, **__):
        from finterminal.data.india.nse_quote import NSEQuoteError
        raise NSEQuoteError("NSE returned 503")

    with patch("finterminal.data.openbb_client._fetch_via_yfinance", _yfinance_raises):
        with patch(
            "finterminal.data.india.nse_quote.fetch_nse_quote",
            _nse_also_fails,
        ):
            with pytest.raises(RuntimeError, match="All providers failed"):
                openbb_client.fetch_quote("RELIANCE.NS")
