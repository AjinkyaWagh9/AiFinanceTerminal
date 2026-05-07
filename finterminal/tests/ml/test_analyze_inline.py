"""Tests for the ML inline badge in /analyze output.

TDD: tests written before implementation.

Spec §3 architecture + §10 testing strategy.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from finterminal.data.duckdb_store import connect, get_conn
from finterminal.agents.analyze_flow import (
    _build_registry_with_overrides,
    run_analyze,
    AnalysisResult,
)
from finterminal.agents.data import DataAgent
from finterminal.llm.base import Completion, ProviderError


# ---------------------------------------------------------------------------
# Shared fixtures / helpers (mirrors test_analyze_flow.py style)
# ---------------------------------------------------------------------------

_BASELINE = Path(__file__).parent.parent / "agents" / "fixtures" / "analyst_baseline_RELIANCE.json"
_RAW_ANALYST = json.loads(_BASELINE.read_text())["raw_response"]
_RAW_CRITIC = """## Issues
- none

## Missing Data
- none

## Confidence Adjustment
0.55

## Verdict
OK
"""


def _quote(t):
    return {
        "ticker": t, "as_of": datetime.now(timezone.utc),
        "last_price": 100.0, "change_pct": 0.0,
        "volume": 1, "market_cap": 1, "provider": "stub",
    }


def _fund(t):
    return {
        "ticker": t, "as_of": datetime.now(timezone.utc).date(),
        "pe_ttm": 20.0, "eps_ttm": None, "roe": 0.1, "roce": None,
        "debt_to_equity": 0.5, "revenue_ttm": None, "net_income_ttm": None,
        "provider": "stub",
    }


def _news(t, limit=10):
    return [{"id": "n1", "ticker": t, "source": "Mint",
             "headline": "x", "url": "u", "published_at": "2026-04-26",
             "body": ""}]


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    os.environ["DUCKDB_PATH"] = db_path
    c = connect(db_path)
    yield c
    c.close()


class _MockProvider:
    def __init__(self, text: str, model: str = "mock"):
        self._text = text
        self._model = model
        self.calls = 0

    async def complete(self, **kwargs):
        self.calls += 1
        return Completion(text=self._text, tokens_in=100, tokens_out=80,
                          model=self._model, provider="mock")


def _registry(*, analyst_provider, critic_primary, critic_fallback=None):
    data_agent = DataAgent(_quote, _fund, _news)
    return _build_registry_with_overrides(
        data_agent=data_agent,
        analyst_provider=lambda: analyst_provider,
        critic_primary=lambda: critic_primary,
        critic_fallback=(lambda: critic_fallback) if critic_fallback else None,
    )


def _seed_signal(conn, ticker: str = "RELIANCE.NS") -> str:
    """Seed a signal row for ticker; return signal_id."""
    sig_id = str(uuid.uuid4())
    ts = datetime(2026, 5, 1, 10, 0, 0)
    conn.execute(
        """
        INSERT OR IGNORE INTO signals
            (signal_id, signal_type, engine, ticker, ts_emitted, payload)
        VALUES (?, 'cluster_momentum', 'test', ?, ?, '{}')
        """,
        [sig_id, ticker, ts],
    )
    return sig_id


def _make_cold_start_cell(horizon_days: int) -> dict:
    return {
        "horizon_days": horizon_days,
        "p_bull": 1 / 3, "p_base": 1 / 3, "p_bear": 1 / 3,
        "predicted_class": "cold_start",
        "conformal_set": ["bull", "base", "bear"],
        "shap_top": [],
        "model_version": "cold_start",
        "feature_version": "reflexivity_v1_vader_decay_0.5",
    }


def _make_real_cell(horizon_days: int) -> dict:
    return {
        "horizon_days": horizon_days,
        "p_bull": 0.25, "p_base": 0.62, "p_bear": 0.13,
        "predicted_class": "base",
        "conformal_set": ["base", "bull"],
        "shap_top": [["sentiment_level", 0.13], ["momentum_5d", -0.07]],
        "model_version": "lgb_v1_reflexivity_v1_20260501T030000",
        "feature_version": "reflexivity_v1_vader_decay_0.5",
    }


# ---------------------------------------------------------------------------
# Test 1: predictor.predict is called after the analyst step
# ---------------------------------------------------------------------------

def test_analyze_calls_predictor_after_compute_for_signal(conn):
    """patch predictor.predict; run an analyze flow; assert called once
    with a signal_id string. The signal must be seeded first so the
    flow can find it via the latest-signal lookup."""
    sig_id = _seed_signal(conn, "RELIANCE.NS")

    cells = [_make_cold_start_cell(h) for h in [7, 30, 90]]

    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )

    with patch("finterminal.agents.analyze_flow.predictor") as mock_pred_module:
        mock_pred_module.predict.return_value = cells
        result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg, fresh=True))

    mock_pred_module.predict.assert_called_once()
    call_args = mock_pred_module.predict.call_args
    # First positional arg is conn, second is signal_id
    called_signal_id = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("signal_id")
    assert called_signal_id == sig_id, (
        f"Expected signal_id={sig_id!r}, got {called_signal_id!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: non-cold-start cells render inline badge with horizon markers
# ---------------------------------------------------------------------------

def test_analyze_renders_inline_badge_for_non_cold_start_cells(conn):
    """predictor.predict returns 3 real cells; analyze result should carry
    ml_cells; the rendered badge text must contain 'Model · 7d', '30d', '90d'."""
    _seed_signal(conn, "RELIANCE.NS")

    cells = [_make_real_cell(h) for h in [7, 30, 90]]

    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )

    with patch("finterminal.agents.analyze_flow.predictor") as mock_pred_module:
        mock_pred_module.predict.return_value = cells
        result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg, fresh=True))

    assert result.ml_cells is not None, "ml_cells should be populated for non-cold-start"
    assert len(result.ml_cells) == 3

    badge_text = result.ml_badge_text or ""
    assert "Model" in badge_text, f"Expected 'Model' in badge, got: {badge_text!r}"
    assert "7d" in badge_text, f"Expected '7d' in badge, got: {badge_text!r}"
    assert "30d" in badge_text, f"Expected '30d' in badge, got: {badge_text!r}"
    assert "90d" in badge_text, f"Expected '90d' in badge, got: {badge_text!r}"


# ---------------------------------------------------------------------------
# Test 3: cold-start cells render 'cold_start' badge
# ---------------------------------------------------------------------------

def test_analyze_renders_cold_start_badge(conn):
    """predictor.predict returns 3 cold-start cells; badge must contain
    'cold_start' and the '≥100 resolved outcomes' hint."""
    _seed_signal(conn, "RELIANCE.NS")

    cells = [_make_cold_start_cell(h) for h in [7, 30, 90]]

    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )

    with patch("finterminal.agents.analyze_flow.predictor") as mock_pred_module:
        mock_pred_module.predict.return_value = cells
        result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg, fresh=True))

    assert result.ml_cells is not None
    badge_text = result.ml_badge_text or ""
    assert "cold_start" in badge_text, (
        f"Expected 'cold_start' in badge, got: {badge_text!r}"
    )
    assert "100" in badge_text, (
        f"Expected '≥100 resolved outcomes' hint in badge, got: {badge_text!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: predictor error must not break analyze flow
# ---------------------------------------------------------------------------

def test_analyze_does_not_fail_when_predictor_raises(conn):
    """predictor.predict raises; analyze should complete normally; ml_cells
    should be None (badge absent); warning logged but no exception raised."""
    _seed_signal(conn, "RELIANCE.NS")

    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )

    with patch("finterminal.agents.analyze_flow.predictor") as mock_pred_module:
        mock_pred_module.predict.side_effect = RuntimeError("model exploded")
        result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg, fresh=True))

    # Analyze must still return a valid result
    assert isinstance(result, AnalysisResult), "run_analyze should return AnalysisResult"
    assert result.analyst_payload, "Analyst payload must be present"

    # ML badge must be absent
    assert result.ml_cells is None, "ml_cells should be None when predictor raises"
    badge_text = result.ml_badge_text or ""
    assert "Model" not in badge_text, (
        f"Badge text should be empty when predictor raises, got: {badge_text!r}"
    )
