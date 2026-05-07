from __future__ import annotations
from enum import Enum

class Engine(str, Enum):
    MISPRICING  = "mispricing"
    QUALITY     = "quality"
    REGIME      = "regime"
    REFLEXIVITY = "reflexivity"
    RISK        = "risk"

class SignalType(str, Enum):
    CLUSTER_MOMENTUM     = "cluster_momentum"
    DIVERGENCE           = "divergence"
    SENTIMENT_DELTA      = "sentiment_delta"
    CLAIM_RECONCILIATION = "claim_reconciliation"
    REGIME_SHIFT         = "regime_shift"
    RISK_TRIGGER         = "risk_trigger"

SIGNAL_REGISTRY: dict[SignalType, Engine] = {
    SignalType.CLUSTER_MOMENTUM:     Engine.REFLEXIVITY,
    SignalType.DIVERGENCE:           Engine.MISPRICING,
    SignalType.SENTIMENT_DELTA:      Engine.REFLEXIVITY,
    SignalType.CLAIM_RECONCILIATION: Engine.QUALITY,
    SignalType.REGIME_SHIFT:         Engine.REGIME,
    SignalType.RISK_TRIGGER:         Engine.RISK,
}

HORIZONS_DAYS: tuple[int, ...] = (1, 7, 30, 90, 365)

MACRO_TICKER = "_MACRO"
NIFTY_TICKER = "_NIFTY50"

REGIME_FIELDS: tuple[str, ...] = (
    "regime_nifty_close",
    "regime_nifty_pct_50d",
    "regime_india_vix",
    "regime_inr_usd",
    "regime_brent_usd",
    "regime_india_10y_yield",
)
