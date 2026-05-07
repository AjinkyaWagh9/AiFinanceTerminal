# src/finterminal/market_data/macro.py
from __future__ import annotations
from datetime import date, timedelta
import duckdb

from .store import last_close_on_or_before

def snapshot_regime(conn: duckdb.DuckDBPyConnection, *, as_of: date) -> dict:
    """Returns the regime_* fields for a signals row, computed at as_of date.
    Missing data → field is None. INR/Brent/10y stay None in v1 (no source yet)."""
    nifty_now  = last_close_on_or_before(conn, "_NIFTY50", as_of)
    nifty_50dB = last_close_on_or_before(conn, "_NIFTY50", as_of - timedelta(days=50))

    pct_50d = None
    if nifty_now is not None and nifty_50dB not in (None, 0):
        pct_50d = (nifty_now / nifty_50dB) - 1.0

    vix = last_close_on_or_before(conn, "_INDIAVIX", as_of)  # populated when added later

    return {
        "regime_nifty_close":      nifty_now,
        "regime_nifty_pct_50d":    pct_50d,
        "regime_india_vix":        vix,
        "regime_inr_usd":          None,
        "regime_brent_usd":        None,
        "regime_india_10y_yield":  None,
    }
