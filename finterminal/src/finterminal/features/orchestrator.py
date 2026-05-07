# src/finterminal/features/orchestrator.py
from __future__ import annotations
from datetime import datetime
from typing import Any
import duckdb

from .registry import V1_FEATURES
from . import compute_price, compute_regime, compute_news, compute_quality, compute_reflexivity
from finterminal.outcomes.schema import SignalType

def compute_for_signal(conn: duckdb.DuckDBPyConnection, *,
                       signal_id: str,
                       signal_type: SignalType,
                       ticker: str,
                       ts_emitted: datetime,
                       payload: dict[str, Any]) -> dict[str, dict]:
    """Compute the v1 feature vector. Returns {name: {value, is_missing}} for
    every name in V1_FEATURES. Placeholders are emitted as is_missing=True."""
    ctx = dict(ticker=ticker, ts_emitted=ts_emitted,
               signal_type=signal_type, payload=payload)

    out: dict[str, dict] = {}

    # Price block (mom_7d feeds mom_7d_z and narrative_price_divergence)
    mom_7d_v, mom_7d_m  = compute_price.compute_mom_7d(conn, **ctx)
    out["mom_7d"]  = {"value": mom_7d_v,  "is_missing": mom_7d_m}
    mom_30d_v, mom_30d_m = compute_price.compute_mom_30d(conn, **ctx)
    out["mom_30d"] = {"value": mom_30d_v, "is_missing": mom_30d_m}
    vol_v, vol_m   = compute_price.compute_vol_20d(conn, **ctx)
    out["vol_20d"] = {"value": vol_v, "is_missing": vol_m}
    mom_7d_z_v, mom_7d_z_m = compute_price.compute_mom_7d_z(
        conn, mom_7d_value=mom_7d_v, **ctx)
    out["mom_7d_z"] = {"value": mom_7d_z_v, "is_missing": mom_7d_z_m}

    # Regime block
    nr_v, nr_m = compute_regime.compute_nifty_return_50d(conn, **ctx)
    out["nifty_return_50d"] = {"value": nr_v, "is_missing": nr_m}
    nv_v, nv_m = compute_regime.compute_nifty_vol_20d(conn, **ctx)
    out["nifty_vol_20d"] = {"value": nv_v, "is_missing": nv_m}
    bull_v, bull_m = compute_regime.compute_regime_bull(conn, **ctx)
    out["regime_bull"] = {"value": bull_v, "is_missing": bull_m}
    bear_v, bear_m = compute_regime.compute_regime_bear(conn, **ctx)
    out["regime_bear"] = {"value": bear_v, "is_missing": bear_m}
    vol2_v, vol2_m = compute_regime.compute_regime_volatile(conn, **ctx)
    out["regime_volatile"] = {"value": vol2_v, "is_missing": vol2_m}

    # News block
    cmz_v, cmz_m = compute_news.compute_cluster_momentum_z(conn, **ctx)
    out["cluster_momentum_z"] = {"value": cmz_v, "is_missing": cmz_m}
    div_v, div_m = compute_news.compute_narrative_price_divergence(
        cluster_momentum_z=cmz_v, mom_7d_z=mom_7d_z_v)
    out["narrative_price_divergence"] = {"value": div_v, "is_missing": div_m}

    # Quality block (#3)
    roe_v, roe_m = compute_quality.compute_roe(conn, **ctx)
    out["roe"] = {"value": roe_v, "is_missing": roe_m}
    lev_v, lev_m = compute_quality.compute_leverage(conn, **ctx)
    out["leverage"] = {"value": lev_v, "is_missing": lev_m}
    eg_v, eg_m = compute_quality.compute_earnings_growth(conn, **ctx)
    out["earnings_growth"] = {"value": eg_v, "is_missing": eg_m}
    qs_v, qs_m = compute_quality.compute_quality_score(
        conn, roe_value=roe_v, leverage_value=lev_v,
        earnings_growth_value=eg_v, **ctx)
    out["quality_score"] = {"value": qs_v, "is_missing": qs_m}

    # Reflexivity block (#4) — DB-backed first, then meta-signal
    sl_cell = compute_reflexivity.compute_sentiment_level(conn, **ctx)
    out["sentiment_level"] = sl_cell
    out["sentiment_delta"] = compute_reflexivity.compute_sentiment_delta(conn, **ctx)
    es_cell = compute_reflexivity.compute_entropy_sentiment(conn, **ctx)
    out["entropy_sentiment"] = es_cell
    out["entropy_change"]    = compute_reflexivity.compute_entropy_change(conn, **ctx)
    # feature_health: meta-signal over already-computed cells, no extra DB hit
    out["feature_health"] = compute_reflexivity.compute_feature_health(
        sentiment_level=sl_cell,
        entropy_sentiment=es_cell,
    )

    # Invariant: every registered feature is materialized for every signal.
    # Use raise (not assert) so `python -O` cannot silently strip the check.
    expected = {f.name for f in V1_FEATURES}
    if set(out.keys()) != expected:
        raise RuntimeError(
            f"orchestrator missing features: {expected - set(out.keys())}"
        )
    return out
