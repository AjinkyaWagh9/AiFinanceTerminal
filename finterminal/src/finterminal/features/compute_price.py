# src/finterminal/features/compute_price.py
from __future__ import annotations
import math
import statistics
from datetime import datetime, timedelta
import duckdb

from .zscore import rolling_zscore
from .freshness import is_prices_data_fresh
from .registry import ZSCORE_WINDOW_DAYS, ZSCORE_MIN_OBS

Result = tuple[float | None, bool]   # (value, is_missing)

def _last_n_closes_on_or_before(conn: duckdb.DuckDBPyConnection,
                                ticker: str, target_date,
                                n: int) -> list[tuple]:
    return conn.execute(
        """
        SELECT trade_date, close FROM prices_eod
        WHERE ticker = ? AND trade_date <= ?
        ORDER BY trade_date DESC LIMIT ?
        """,
        [ticker, target_date, n],
    ).fetchall()

def _close_n_trading_days_back(conn, ticker, target_date, n):
    # n+1 because index 0 is the as-of close; index n is n trading days back.
    rows = _last_n_closes_on_or_before(conn, ticker, target_date, n + 1)
    if len(rows) < n + 1:
        return None
    return rows[n][1]

def compute_mom_7d(conn, *, ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_prices_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    today = ts_emitted.date()
    rows = _last_n_closes_on_or_before(conn, ticker, today, 8)
    if len(rows) < 8:
        return None, True
    p_now, p_then = rows[0][1], rows[7][1]
    if p_then == 0:
        return None, True
    return p_now / p_then - 1, False

def compute_mom_30d(conn, *, ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_prices_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    today = ts_emitted.date()
    rows = _last_n_closes_on_or_before(conn, ticker, today, 31)
    if len(rows) < 31:
        return None, True
    p_now, p_then = rows[0][1], rows[30][1]
    if p_then == 0:
        return None, True
    return p_now / p_then - 1, False

def compute_vol_20d(conn, *, ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_prices_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    today = ts_emitted.date()
    rows = _last_n_closes_on_or_before(conn, ticker, today, 21)
    if len(rows) < 21:
        return None, True
    closes = [r[1] for r in rows][::-1]   # ascending
    rets = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))
            if closes[i-1] != 0]
    if len(rets) < 2:
        return None, True
    if all(r == rets[0] for r in rets):
        return 0.0, False
    return statistics.stdev(rets), False

def compute_mom_7d_z(conn, *, ticker: str, ts_emitted: datetime,
                     mom_7d_value: float | None, **_) -> Result:
    """z(mom_7d) over the rolling 60d window of mom_7d values for the same ticker."""
    if mom_7d_value is None:
        return None, True
    cutoff = ts_emitted   # exclusive on the right
    history_rows = conn.execute(
        """
        SELECT sf.feature_value
        FROM signal_features sf
        JOIN signals s ON s.signal_id = sf.signal_id
        WHERE sf.feature_name = 'mom_7d'
          AND sf.is_missing = FALSE
          AND s.ticker = ?
          AND s.ts_emitted < ?
          AND s.ts_emitted >= ?
        ORDER BY s.ts_emitted DESC
        """,
        [ticker, cutoff, cutoff - timedelta(days=ZSCORE_WINDOW_DAYS)],
    ).fetchall()
    history = [r[0] for r in history_rows]
    return rolling_zscore(mom_7d_value, history, min_obs=ZSCORE_MIN_OBS)
