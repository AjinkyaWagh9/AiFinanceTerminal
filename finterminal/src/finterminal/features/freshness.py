from __future__ import annotations
from datetime import date, datetime, timedelta
import duckdb

from .registry import MAX_PRICE_STALENESS_DAYS, MAX_NIFTY_STALENESS_DAYS, MAX_FUNDAMENTALS_STALENESS_DAYS
from finterminal.outcomes.schema import NIFTY_TICKER

def last_prices_date(conn: duckdb.DuckDBPyConnection,
                     ticker: str, *, as_of: date) -> date | None:
    """Most recent trade_date for `ticker` with trade_date <= as_of, or None."""
    row = conn.execute(
        "SELECT MAX(trade_date) FROM prices_eod "
        "WHERE ticker = ? AND trade_date <= ?",
        [ticker, as_of],
    ).fetchone()
    return row[0] if row and row[0] is not None else None

def _fresh(conn, ticker: str, *, ts_emitted: datetime,
           max_staleness_days: int) -> bool:
    last = last_prices_date(conn, ticker, as_of=ts_emitted.date())
    if last is None:
        return False
    return (ts_emitted.date() - last) <= timedelta(days=max_staleness_days)

def is_prices_data_fresh(conn: duckdb.DuckDBPyConnection,
                         ticker: str, *, ts_emitted: datetime) -> bool:
    return _fresh(conn, ticker, ts_emitted=ts_emitted,
                  max_staleness_days=MAX_PRICE_STALENESS_DAYS)

def is_nifty_data_fresh(conn: duckdb.DuckDBPyConnection, *,
                        ts_emitted: datetime) -> bool:
    return _fresh(conn, NIFTY_TICKER, ts_emitted=ts_emitted,
                  max_staleness_days=MAX_NIFTY_STALENESS_DAYS)

def last_fundamentals_date(conn: duckdb.DuckDBPyConnection,
                           ticker: str, *, as_of: date) -> date | None:
    """Most recent fundamentals as_of for `ticker` with as_of <= as_of, or None."""
    row = conn.execute(
        "SELECT MAX(as_of) FROM fundamentals "
        "WHERE ticker = ? AND as_of <= ?",
        [ticker, as_of],
    ).fetchone()
    return row[0] if row and row[0] is not None else None

def is_fundamentals_data_fresh(conn: duckdb.DuckDBPyConnection,
                               ticker: str, *, ts_emitted: datetime) -> bool:
    last = last_fundamentals_date(conn, ticker, as_of=ts_emitted.date())
    if last is None:
        return False
    return (ts_emitted.date() - last) <= timedelta(days=MAX_FUNDAMENTALS_STALENESS_DAYS)
