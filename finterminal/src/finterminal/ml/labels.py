"""ml/labels.py — vol-scaled bull/base/bear labelling.

Public surface:
    label_outcomes(conn, horizon_days: int) -> polars.DataFrame

Returns columns: signal_id (str), label (str), sigma_used (float).

Algorithm (spec §4.1):
  - Join signal_outcomes × signals on signal_id, filter by horizon_days.
  - Exclude unresolved rows (resolved_at IS NULL).
  - Exclude rows whose signals.ts_emitted is NULL.
  - For each row compute σ = stdev of daily Nifty log returns over the
    252 trading days *strictly preceding* signal.ts_emitted.
    Source: prices_eod WHERE ticker = '_NIFTY50'.
  - Label rule: bull if ret_pct_vs_nifty > +σ; bear if < −σ; base otherwise.
  - If fewer than 252 Nifty days precede ts_emitted, exclude that row.
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime

import duckdb
import polars as pl

# Nifty ticker — same convention as compute_regime.py and outcomes schema.
_NIFTY = "_NIFTY50"
_WINDOW = 252  # trading days


def _nifty_log_ret_stdev(
    conn: duckdb.DuckDBPyConnection,
    before_date,  # date or datetime; strictly-preceding boundary
) -> float | None:
    """Return stdev of daily Nifty log returns over the 252 days strictly
    preceding *before_date*.  Returns None when fewer than 252 days exist."""
    # We need 253 closes to produce 252 log-return observations.
    rows = conn.execute(
        """
        SELECT close
        FROM   prices_eod
        WHERE  ticker = ?
          AND  trade_date < ?
        ORDER  BY trade_date DESC
        LIMIT  253
        """,
        [_NIFTY, before_date],
    ).fetchall()

    if len(rows) < _WINDOW + 1:
        return None

    closes = [r[0] for r in rows][::-1]  # chronological order (oldest first)

    log_rets: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev == 0:
            continue
        log_rets.append(math.log(closes[i] / prev))

    if len(log_rets) < _WINDOW:
        return None

    # statistics.stdev requires >= 2 values (guaranteed here since _WINDOW=252)
    return statistics.stdev(log_rets)


def label_outcomes(
    conn: duckdb.DuckDBPyConnection,
    horizon_days: int,
) -> pl.DataFrame:
    """Return a Polars DataFrame with columns (signal_id, label, sigma_used).

    Unresolved outcomes and signals without sufficient Nifty history are
    excluded from the output.
    """
    # Pull resolved outcomes for this horizon, joined with ts_emitted.
    rows = conn.execute(
        """
        SELECT so.signal_id,
               so.ret_pct_vs_nifty,
               s.ts_emitted
        FROM   signal_outcomes AS so
        JOIN   signals          AS s  USING (signal_id)
        WHERE  so.horizon_days  = ?
          AND  so.resolved_at  IS NOT NULL
          AND  s.ts_emitted    IS NOT NULL
        """,
        [horizon_days],
    ).fetchall()

    out_signal_ids: list[str] = []
    out_labels: list[str] = []
    out_sigmas: list[float] = []

    for signal_id, ret_pct_vs_nifty, ts_emitted in rows:
        # ts_emitted may be a datetime or a string depending on DuckDB version;
        # normalise to a date for the SQL boundary.
        if isinstance(ts_emitted, str):
            ts_emitted = datetime.fromisoformat(ts_emitted)
        target_date = ts_emitted.date() if hasattr(ts_emitted, "date") else ts_emitted

        sigma = _nifty_log_ret_stdev(conn, target_date)
        if sigma is None:
            continue  # insufficient history — exclude

        # Apply label rule
        if ret_pct_vs_nifty > sigma:
            label = "bull"
        elif ret_pct_vs_nifty < -sigma:
            label = "bear"
        else:
            label = "base"

        out_signal_ids.append(signal_id)
        out_labels.append(label)
        out_sigmas.append(sigma)

    return pl.DataFrame(
        {
            "signal_id": out_signal_ids,
            "label": out_labels,
            "sigma_used": out_sigmas,
        },
        schema={
            "signal_id": pl.Utf8,
            "label": pl.Utf8,
            "sigma_used": pl.Float64,
        },
    )
