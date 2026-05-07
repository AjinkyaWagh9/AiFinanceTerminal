"""Ticker normalization across exchanges.

Phase 1: NSE / BSE / US (bare). Phase 2.5 grows this with corporate-filings
RSS feeds and ISIN lookup.

Accepted input forms (caller-friendly):
  RELIANCE          → RELIANCE.NS    (default NSE — Indian-first)
  RELIANCE.NS       → RELIANCE.NS    (idempotent)
  NSE:RELIANCE      → RELIANCE.NS
  BSE:RELIANCE      → RELIANCE.BO
  US:AAPL           → AAPL           (no suffix — yfinance/FMP/Benzinga expect bare US)
  AAPL              → AAPL.NS        (still defaults to NSE — use US:AAPL to disambiguate)
"""

from __future__ import annotations


def normalize_ticker(symbol: str, exchange: str = "NSE") -> str:
    """Maps a user-typed symbol to the OpenBB-friendly form.

    Use the `EXCHANGE:SYMBOL` prefix (NSE:, BSE:, US:) to disambiguate; bare
    symbols default to the `exchange` arg (NSE by default — Indian markets first).
    """
    symbol = symbol.upper().strip()

    if ":" in symbol:
        prefix, _, rest = symbol.partition(":")
        if prefix == "US":
            return rest.split(".")[0]  # strip any suffix; US symbols are bare
        if prefix == "NSE":
            return rest if "." in rest else f"{rest}.NS"
        if prefix == "BSE":
            return rest if "." in rest else f"{rest}.BO"
        # Unknown prefix — fall through and treat as bare symbol with default exchange

    if "." in symbol:
        return symbol

    suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    return f"{symbol}{suffix}"
