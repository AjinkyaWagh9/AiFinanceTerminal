"""OllamaProvider unit tests (mocked HTTP) + a gated live smoke test.

The unit tests run without Ollama present — they mock httpx responses to
verify the request shape, response parsing, and error mapping.

The live smoke test is `skipif`-gated on the Ollama daemon being reachable
AND `qwen3:8b` being pulled, so it runs locally for the developer who has
Ollama set up but stays silent in CI / on machines without it.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import httpx
import pytest

from finterminal.llm.base import Message, ModelMetadata, ProviderError
from finterminal.llm.providers.ollama import OllamaProvider, _resolve_base_url


_QWEN_META = ModelMetadata(
    name="qwen3:8b",
    provider="ollama",
    api_id="qwen3:8b",
    context_window=32768,
    cost_per_mtok_in=0.0,
    cost_per_mtok_out=0.0,
    capabilities=["reasoning"],
    tags=["local"],
)


# ---------------- url resolution ----------------

def test_default_base_url_is_localhost():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OLLAMA_BASE_URL", None)
        assert _resolve_base_url() == "http://localhost:11434"


def test_base_url_env_override_strips_trailing_slash():
    with patch.dict(os.environ, {"OLLAMA_BASE_URL": "https://ollama.example.com/"}):
        assert _resolve_base_url() == "https://ollama.example.com"


# ---------------- mocked HTTP success path ----------------

class _MockResp:
    def __init__(self, status_code: int, json_body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_body
        self.text = text

    def json(self) -> dict:
        if self._json is None:
            raise ValueError("not json")
        return self._json


def _make_async_post(captured: dict, resp: _MockResp):
    """Returns an async-context-manager-compatible mock for httpx.AsyncClient."""

    async def _post(self, url, json=None, headers=None):  # noqa: ARG001
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        return resp

    return _post


def test_complete_happy_path_request_shape_and_response_parse():
    """Verify request payload + that we extract text / token counts."""
    captured: dict = {}
    resp = _MockResp(
        200,
        json_body={
            "model": "qwen3:8b",
            "message": {"role": "assistant", "content": "Hello from Qwen."},
            "prompt_eval_count": 42,
            "eval_count": 7,
            "done": True,
        },
    )

    with patch("httpx.AsyncClient.post", _make_async_post(captured, resp)):
        prov = OllamaProvider(_QWEN_META)
        result = asyncio.run(
            prov.complete(
                system="be terse",
                messages=[Message(role="user", content="hi")],
                temperature=0.5,
                max_tokens=128,
            )
        )

    # Request shape
    assert captured["url"] == "http://localhost:11434/api/chat"
    p = captured["payload"]
    assert p["model"] == "qwen3:8b"
    assert p["stream"] is False
    assert p["options"]["temperature"] == 0.5
    assert p["options"]["num_predict"] == 128
    assert p["messages"][0] == {"role": "system", "content": "be terse"}
    assert p["messages"][1] == {"role": "user", "content": "hi"}

    # Response parse
    assert result.text == "Hello from Qwen."
    assert result.tokens_in == 42
    assert result.tokens_out == 7
    assert result.model == "qwen3:8b"
    assert result.provider == "ollama"


def test_complete_accepts_cache_system_kwarg():
    """Required by Phase-2 protocol — accept it, no-op for Ollama."""
    captured: dict = {}
    resp = _MockResp(
        200,
        json_body={
            "message": {"content": "ok"},
            "prompt_eval_count": 1,
            "eval_count": 1,
        },
    )
    with patch("httpx.AsyncClient.post", _make_async_post(captured, resp)):
        prov = OllamaProvider(_QWEN_META)
        result = asyncio.run(
            prov.complete(system="x", messages=[Message("user", "y")], cache_system=True)
        )
    assert result.text == "ok"
    # No "cache_system" key should leak into the Ollama payload:
    assert "cache_system" not in captured["payload"]
    assert "cache_system" not in captured["payload"].get("options", {})


def test_auth_token_sent_as_bearer_when_set():
    captured: dict = {}
    resp = _MockResp(
        200,
        json_body={"message": {"content": "x"}, "prompt_eval_count": 0, "eval_count": 0},
    )
    with (
        patch.dict(os.environ, {"OLLAMA_API_KEY": "secret-tok"}),
        patch("httpx.AsyncClient.post", _make_async_post(captured, resp)),
    ):
        prov = OllamaProvider(_QWEN_META)
        asyncio.run(prov.complete(system="x", messages=[Message("user", "y")]))
    assert captured["headers"]["Authorization"] == "Bearer secret-tok"


def test_no_auth_header_when_token_unset():
    captured: dict = {}
    resp = _MockResp(
        200,
        json_body={"message": {"content": "x"}, "prompt_eval_count": 0, "eval_count": 0},
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OLLAMA_API_KEY", None)
        with patch("httpx.AsyncClient.post", _make_async_post(captured, resp)):
            prov = OllamaProvider(_QWEN_META)
            asyncio.run(prov.complete(system="x", messages=[Message("user", "y")]))
    assert "Authorization" not in captured["headers"]


# ---------------- mocked HTTP error paths ----------------

def test_404_means_model_not_pulled():
    resp = _MockResp(404, text='{"error":"model not found"}')
    captured: dict = {}
    with patch("httpx.AsyncClient.post", _make_async_post(captured, resp)):
        prov = OllamaProvider(_QWEN_META)
        with pytest.raises(ProviderError, match="not found locally"):
            asyncio.run(prov.complete(system="x", messages=[Message("user", "y")]))


def test_5xx_raises_with_status():
    resp = _MockResp(503, text="server overloaded")
    captured: dict = {}
    with patch("httpx.AsyncClient.post", _make_async_post(captured, resp)):
        prov = OllamaProvider(_QWEN_META)
        with pytest.raises(ProviderError, match="HTTP 503"):
            asyncio.run(prov.complete(system="x", messages=[Message("user", "y")]))


def test_connect_error_explains_daemon_check():
    async def _fail(self, url, json=None, headers=None):  # noqa: ARG001
        raise httpx.ConnectError("connection refused")

    with patch("httpx.AsyncClient.post", _fail):
        prov = OllamaProvider(_QWEN_META)
        with pytest.raises(ProviderError, match="Cannot reach Ollama"):
            asyncio.run(prov.complete(system="x", messages=[Message("user", "y")]))


def test_timeout_explains_cold_start():
    async def _slow(self, url, json=None, headers=None):  # noqa: ARG001
        raise httpx.ReadTimeout("too slow")

    with patch("httpx.AsyncClient.post", _slow):
        prov = OllamaProvider(_QWEN_META)
        with pytest.raises(ProviderError, match="cold-start"):
            asyncio.run(prov.complete(system="x", messages=[Message("user", "y")]))


def test_non_json_response_raises():
    resp = _MockResp(200, json_body=None, text="<html>oops</html>")
    captured: dict = {}
    with patch("httpx.AsyncClient.post", _make_async_post(captured, resp)):
        prov = OllamaProvider(_QWEN_META)
        with pytest.raises(ProviderError, match="non-JSON"):
            asyncio.run(prov.complete(system="x", messages=[Message("user", "y")]))


# ---------------- live smoke (gated) ----------------

def _pulled_qwen_model() -> str | None:
    """Return the name of any pulled qwen-class model, or None.

    Used to gate the live smoke test on whichever qwen variant the
    developer has pulled (qwen3:8b, qwen3.5:9b, qwen2.5:7b, etc.).
    """
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if r.status_code != 200:
            return None
        names = [m.get("name", "") for m in r.json().get("models", [])]
        for n in names:
            if "qwen" in n.lower():
                return n
    except Exception:  # noqa: BLE001
        return None
    return None


_PULLED_QWEN = _pulled_qwen_model()


@pytest.mark.skipif(
    _PULLED_QWEN is None,
    reason="No qwen-class model pulled; run `ollama pull qwen3.5:9b` to enable.",
)
def test_live_smoke_qwen_completes():
    """End-to-end: real Ollama daemon, real qwen-class model.

    Skipped unless any qwen* model is pulled. Times out generously
    (cold-start on M4 ~20-40s; warm calls ~1-3s).
    """
    meta = ModelMetadata(
        name=_PULLED_QWEN,
        provider="ollama",
        api_id=_PULLED_QWEN,
        context_window=32768,
        cost_per_mtok_in=0.0,
        cost_per_mtok_out=0.0,
        capabilities=["reasoning"],
        tags=["local"],
    )
    prov = OllamaProvider(meta)
    # qwen3.x are reasoning-tier — they spend tokens on internal thought
    # before visible output. max_tokens=256 is the floor; smaller values
    # return empty text because the budget is consumed by reasoning.
    result = asyncio.run(
        prov.complete(
            system="Reply briefly.",
            messages=[Message(role="user", content="Say the word: ok")],
            temperature=0.1,
            max_tokens=256,
        )
    )
    assert result.text, f"empty completion (tokens_in={result.tokens_in}, tokens_out={result.tokens_out})"
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    assert result.provider == "ollama"
    assert result.model == _PULLED_QWEN
