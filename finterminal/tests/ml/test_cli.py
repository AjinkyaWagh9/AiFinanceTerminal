"""Tests for `finterminal ml train` and `finterminal ml backfill` CLI subcommands.

TDD: these tests are written before the implementation and are expected to
fail until commands_ml.py + the /ml dispatch wiring in commands.py exist.

Spec §6 cadence + §4.4 + §4.5 public surfaces.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from finterminal.data.duckdb_store import connect
from finterminal.features.compute_reflexivity import FEATURE_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn(tmp_path):
    return connect(str(tmp_path / "t.duckdb"))


def _invoke_ml_train(conn):
    """Call the ml_train handler directly (as the CLI dispatch does)."""
    from finterminal.commands_ml import ml_train
    ml_train(conn)


def _invoke_ml_backfill(conn, since: str | None = None):
    """Call the ml_backfill handler directly.

    since: ISO date string like '2026-04-25', or None for default (yesterday).
    Returns the result dict from ml_backfill.
    """
    from finterminal.commands_ml import ml_backfill
    return ml_backfill(conn, since_str=since)


# ---------------------------------------------------------------------------
# Test: ml train subcommand invokes trainer with v1 horizons
# ---------------------------------------------------------------------------

def test_ml_train_subcommand_invokes_trainer_with_v1_horizons(tmp_path):
    """patch ml.trainer.train_all; invoke CLI handler; assert called with
    horizons=[7, 30, 90] and the live FEATURE_VERSION."""
    conn = _make_conn(tmp_path)

    mock_bundle = MagicMock()
    mock_bundle.model_version = "lgb_v1_test_20260501T000000"
    mock_bundle.per_horizon = {7: MagicMock(brier=0.22), 30: MagicMock(brier=float("nan")), 90: MagicMock(brier=float("nan"))}

    with patch("finterminal.ml.trainer.train_all", return_value=mock_bundle) as mock_train:
        result = _invoke_ml_train(conn)

    mock_train.assert_called_once()
    call_kwargs = mock_train.call_args

    # Must be called with conn as first positional or keyword arg
    assert call_kwargs.args[0] is conn or call_kwargs.kwargs.get("conn") is conn

    # horizons=[7, 30, 90]
    called_horizons = (
        call_kwargs.kwargs.get("horizons")
        or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    )
    assert called_horizons == [7, 30, 90], (
        f"Expected horizons=[7, 30, 90], got {called_horizons!r}"
    )

    # feature_version must equal the live FEATURE_VERSION constant
    called_fv = (
        call_kwargs.kwargs.get("feature_version")
        or (call_kwargs.args[2] if len(call_kwargs.args) > 2 else None)
    )
    assert called_fv == FEATURE_VERSION, (
        f"Expected feature_version={FEATURE_VERSION!r}, got {called_fv!r}"
    )


# ---------------------------------------------------------------------------
# Test: ml backfill default since is yesterday
# ---------------------------------------------------------------------------

def test_ml_backfill_default_since_is_yesterday(tmp_path):
    """patch ml.predictor.batch_backfill; invoke CLI with no --since;
    assert since_ts is within 2 seconds of (now - 1 day)."""
    conn = _make_conn(tmp_path)

    with patch("finterminal.ml.predictor.batch_backfill", return_value=0) as mock_backfill:
        _invoke_ml_backfill(conn, since=None)

    mock_backfill.assert_called_once()
    call_args = mock_backfill.call_args
    since_ts = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("since_ts")

    assert since_ts is not None, "since_ts must be passed to batch_backfill"

    # Strip tz for comparison if needed
    now = datetime.now(timezone.utc)
    expected = now - timedelta(days=1)

    # Allow the implementation to use naive or aware datetime; normalise for comparison
    if since_ts.tzinfo is not None:
        delta = abs((since_ts - expected).total_seconds())
    else:
        expected_naive = expected.replace(tzinfo=None)
        delta = abs((since_ts - expected_naive).total_seconds())

    assert delta < 60, (
        f"since_ts should be approximately (now - 1 day); delta={delta:.1f}s"
    )


# ---------------------------------------------------------------------------
# Test: ml backfill accepts ISO date --since
# ---------------------------------------------------------------------------

def test_ml_backfill_accepts_iso_date_since(tmp_path):
    """Invoke CLI with --since 2026-04-25; assert parsed correctly."""
    conn = _make_conn(tmp_path)

    with patch("finterminal.ml.predictor.batch_backfill", return_value=5) as mock_backfill:
        _invoke_ml_backfill(conn, since="2026-04-25")

    mock_backfill.assert_called_once()
    call_args = mock_backfill.call_args
    since_ts = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("since_ts")

    assert since_ts is not None
    # The parsed date must be 2026-04-25
    assert since_ts.year == 2026
    assert since_ts.month == 4
    assert since_ts.day == 25
