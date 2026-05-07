# src/finterminal/features/compute_regime.py
from __future__ import annotations
import math
import statistics
from datetime import datetime, timedelta
import duckdb

from .freshness import is_nifty_data_fresh
from .registry import REGIME_VOL_MEDIAN_LOOKBACK_DAYS

Result = tuple[float | None, bool]
NIFTY = "_NIFTY50"

def _nifty_closes(conn, target_date, n):
    return conn.execute(
        "SELECT trade_date, close FROM prices_eod "
        "WHERE ticker = ? AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT ?",
        [NIFTY, target_date, n],
    ).fetchall()

def compute_nifty_return_50d(conn, *, ts_emitted: datetime, **_) -> Result:
    if not is_nifty_data_fresh(conn, ts_emitted=ts_emitted):
        return None, True
    rows = _nifty_closes(conn, ts_emitted.date(), 51)
    if len(rows) < 51 or rows[50][1] == 0:
        return None, True
    return rows[0][1] / rows[50][1] - 1, False

def compute_nifty_vol_20d(conn, *, ts_emitted: datetime, **_) -> Result:
    if not is_nifty_data_fresh(conn, ts_emitted=ts_emitted):
        return None, True
    rows = _nifty_closes(conn, ts_emitted.date(), 21)
    if len(rows) < 21:
        return None, True
    closes = [r[1] for r in rows][::-1]
    rets = [math.log(closes[i]/closes[i-1]) for i in range(1, len(closes))
            if closes[i-1] != 0]
    if len(rets) < 2:
        return None, True
    if all(r == rets[0] for r in rets):
        return 0.0, False
    return statistics.stdev(rets), False

def _vol_below_median(conn, ts_emitted: datetime, current_vol: float) -> bool:
    """True if current 20d vol is at-or-below the historical median over LOOKBACK days
    of past Nifty 20d-vol windows. Computed inline (no caching) — cheap for v1."""
    today = ts_emitted.date()
    history_rows = _nifty_closes(conn, today, REGIME_VOL_MEDIAN_LOOKBACK_DAYS + 21)
    if len(history_rows) < 41:   # need at least two non-overlapping 20d windows
        return False
    closes = [r[1] for r in history_rows][::-1]
    log_rets = [math.log(closes[i]/closes[i-1]) for i in range(1, len(closes))
                if closes[i-1] != 0]
    vols = [statistics.stdev(log_rets[i-19:i+1]) for i in range(19, len(log_rets))]
    if not vols:
        return False
    return current_vol <= statistics.median(vols)

def compute_regime_bull(conn, *, ts_emitted: datetime, **_) -> Result:
    nr, miss = compute_nifty_return_50d(conn, ts_emitted=ts_emitted)
    nv, miss_v = compute_nifty_vol_20d(conn, ts_emitted=ts_emitted)
    if miss or miss_v:
        return None, True
    return (1.0 if (nr > 0 and _vol_below_median(conn, ts_emitted, nv)) else 0.0), False

def compute_regime_bear(conn, *, ts_emitted: datetime, **_) -> Result:
    nr, miss = compute_nifty_return_50d(conn, ts_emitted=ts_emitted)
    if miss:
        return None, True
    return (1.0 if nr < 0 else 0.0), False

def compute_regime_volatile(conn, *, ts_emitted: datetime, **_) -> Result:
    bull, miss_b = compute_regime_bull(conn, ts_emitted=ts_emitted)
    bear, miss_be = compute_regime_bear(conn, ts_emitted=ts_emitted)
    if miss_b or miss_be:
        return None, True
    return (1.0 if (bull == 0.0 and bear == 0.0) else 0.0), False
