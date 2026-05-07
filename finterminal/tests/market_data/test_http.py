import pytest
from unittest.mock import patch, Mock
from finterminal.market_data._http import fetch, Http404, Http429

def _resp(status, content=b"x"):
    r = Mock()
    r.status_code = status
    r.content = content
    return r

def test_fetch_returns_bytes_on_200():
    with patch("finterminal.market_data._http.requests.get",
               return_value=_resp(200, b"hello")):
        assert fetch("http://x") == b"hello"

def test_fetch_raises_404():
    with patch("finterminal.market_data._http.requests.get",
               return_value=_resp(404)):
        with pytest.raises(Http404):
            fetch("http://x")

def test_fetch_retries_once_on_429_then_raises():
    calls = [_resp(429), _resp(429)]
    with patch("finterminal.market_data._http.requests.get",
               side_effect=calls), \
         patch("finterminal.market_data._http.time.sleep") as sleep:
        with pytest.raises(Http429):
            fetch("http://x")
        sleep.assert_called()  # backoff happened

def test_fetch_recovers_after_one_429():
    with patch("finterminal.market_data._http.requests.get",
               side_effect=[_resp(429), _resp(200, b"ok")]), \
         patch("finterminal.market_data._http.time.sleep"):
        assert fetch("http://x") == b"ok"
