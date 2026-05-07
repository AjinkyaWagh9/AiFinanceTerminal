# src/finterminal/outcomes/backfill.py
from __future__ import annotations
from datetime import date, datetime, timedelta
import duckdb

from finterminal.market_data.store import last_close_on_or_before
from .schema import MACRO_TICKER, NIFTY_TICKER


def resolve_pending(conn: duckdb.DuckDBPyConnection, *,
                    today: date | None = None) -> int:
    """Fill ret_pct + ret_pct_vs_nifty for every (signal, horizon) where
    today >= ts_emitted + horizon_days AND prices exist for both endpoints.
    Returns count of rows resolved."""
    today = today or date.today()
    pending = conn.execute(
        """
        SELECT s.signal_id, s.ticker, s.ts_emitted, o.horizon_days
        FROM signals s
        JOIN signal_outcomes o USING (signal_id)
        WHERE o.resolved_at IS NULL
          AND DATE(s.ts_emitted) + INTERVAL (o.horizon_days) DAY <= ?
        """,
        [today],
    ).fetchall()

    resolved = 0
    for signal_id, ticker, ts_emitted, horizon in pending:
        emit_date = ts_emitted.date() if isinstance(ts_emitted, datetime) else ts_emitted
        target_date = emit_date + timedelta(days=horizon)

        price_ticker = NIFTY_TICKER if ticker == MACRO_TICKER else ticker
        c_then = last_close_on_or_before(conn, price_ticker, emit_date)
        c_thN  = last_close_on_or_before(conn, price_ticker, target_date)
        n_then = last_close_on_or_before(conn, NIFTY_TICKER, emit_date)
        n_thN  = last_close_on_or_before(conn, NIFTY_TICKER, target_date)
        if None in (c_then, c_thN, n_then, n_thN) or c_then == 0 or n_then == 0:
            continue

        ret = (c_thN / c_then) - 1.0
        nifty_ret = (n_thN / n_then) - 1.0
        alpha = ret - nifty_ret

        conn.execute(
            "UPDATE signal_outcomes SET ret_pct=?, ret_pct_vs_nifty=?, resolved_at=? "
            "WHERE signal_id=? AND horizon_days=?",
            [ret, alpha, datetime.now(), signal_id, horizon],
        )
        resolved += 1
    return resolved
