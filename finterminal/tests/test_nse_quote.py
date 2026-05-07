"""NSE direct quote API tests (Q-5).

Covers the new fallback path when yfinance throttles. Mocks httpx so
tests run offline. A representative NSE response is in
tests/fixtures/nse_quote_RELIANCE.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from finterminal.data.india.nse_quote import (
    NSEQuoteError,
    fetch_nse_quote,
    _strip_exchange_suffix,
)


_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "nse_quote_RELIANCE.json").read_text()
)


# ---------------- symbol mapping ----------------

def test_strip_exchange_suffix_ns():
    assert _strip_exchange_suffix("RELIANCE.NS") == "RELIANCE"


def test_strip_exchange_suffix_bo():
    assert _strip_exchange_suffix("TATASTEEL.BO") == "TATASTEEL"


def test_strip_exchange_suffix_no_suffix():
    assert _strip_exchange_suffix("RELIANCE") == "RELIANCE"


def test_strip_exchange_suffix_lowercase():
    assert _strip_exchange_suffix("reliance.ns") == "RELIANCE"


# ---------------- happy path ----------------

class _MockResp:
    def __init__(self, status_code: int, json_body=None, text: str = ""):
        self.status_code = status_code
        self._json = json_body
        self.text = text
        self.cookies = httpx.Cookies()

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


def _patched_client_factory(get_responses: list[_MockResp]):
    """Returns a class that mimics httpx.Client behavior across N gets."""

    call_log: list[str] = []

    class _FakeClient:
        def __init__(self, *_, **__):
            self._idx = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, url, **__):
            call_log.append(url)
            resp = get_responses[min(self._idx, len(get_responses) - 1)]
            self._idx += 1
            return resp

    return _FakeClient, call_log


def test_fetch_nse_quote_happy_path_request_shape_and_field_mapping():
    """Verify two-step session warmup → API call, and field extraction
    from the priceInfo / marketDeptOrderBook blocks."""
    fake_cls, log = _patched_client_factory(
        [
            _MockResp(200, text="<html>warmup</html>"),  # warmup page
            _MockResp(200, json_body=_FIXTURE),  # api response
        ]
    )

    with patch("httpx.Client", fake_cls):
        result = fetch_nse_quote("RELIANCE.NS")

    # Two GETs: warmup, then the API
    assert len(log) == 2
    assert "nseindia.com" in log[0]
    assert "/api/quote-equity?symbol=RELIANCE" in log[1]

    # Field mapping
    assert result["ticker"] == "RELIANCE.NS"
    assert result["last_price"] == 1421.00
    assert result["change_pct"] == 2.27
    assert result["volume"] == 8281000
    assert result["provider"] == "nse"
    # market_cap derived from issuedSize × lastPrice OR direct from totalMarketCap
    assert result["market_cap"] is not None
    assert result["market_cap"] > 0
    # raw is the full JSON for downstream debugging
    assert result["raw"]["priceInfo"]["lastPrice"] == 1421.00


def test_fetch_nse_quote_uses_browser_user_agent():
    """NSE blocks default httpx User-Agent. Confirm we send a browser-like UA."""
    captured_headers: dict = {}

    class _FakeClient:
        def __init__(self, *_, **kwargs):
            captured_headers.update(kwargs.get("headers") or {})

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, url, **__):
            if "/api/" in url:
                return _MockResp(200, json_body=_FIXTURE)
            return _MockResp(200, text="ok")

    with patch("httpx.Client", _FakeClient):
        fetch_nse_quote("RELIANCE.NS")

    ua = captured_headers.get("User-Agent", "")
    assert "Mozilla" in ua, f"expected browser-like User-Agent, got {ua!r}"


# ---------------- error paths ----------------

def test_fetch_nse_quote_raises_on_404():
    fake_cls, _ = _patched_client_factory(
        [_MockResp(200, text="ok"), _MockResp(404, text="not found")]
    )
    with patch("httpx.Client", fake_cls):
        with pytest.raises(NSEQuoteError, match="404"):
            fetch_nse_quote("XYZNOTLISTED.NS")


def test_fetch_nse_quote_raises_on_429_throttle():
    fake_cls, _ = _patched_client_factory(
        [_MockResp(200, text="ok"), _MockResp(429, text="rate limited")]
    )
    with patch("httpx.Client", fake_cls):
        with pytest.raises(NSEQuoteError, match="429|throttle"):
            fetch_nse_quote("RELIANCE.NS")


def test_fetch_nse_quote_raises_when_response_lacks_priceinfo():
    """NSE occasionally returns 200 with a stub body for invalid symbols."""
    fake_cls, _ = _patched_client_factory(
        [_MockResp(200, text="ok"), _MockResp(200, json_body={"info": {}, "metadata": {}})]
    )
    with patch("httpx.Client", fake_cls):
        with pytest.raises(NSEQuoteError, match="priceInfo|missing"):
            fetch_nse_quote("RELIANCE.NS")


def test_fetch_nse_quote_raises_on_connect_error():
    class _FailClient:
        def __init__(self, *_, **__): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, url, **__):
            raise httpx.ConnectError("dns")

    with patch("httpx.Client", _FailClient):
        with pytest.raises(NSEQuoteError, match="reach NSE|connect"):
            fetch_nse_quote("RELIANCE.NS")
