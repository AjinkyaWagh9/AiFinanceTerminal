from __future__ import annotations
from datetime import datetime
import duckdb

from .freshness import is_fundamentals_data_fresh

Result = tuple[float | None, bool]   # (value, is_missing)

MIN_CROSS_SECTION_COUNT = 3   # minimum tickers needed for quality_score z-scoring


def compute_roe(conn: duckdb.DuckDBPyConnection, *,
                ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_fundamentals_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    row = conn.execute(
        "SELECT roe FROM fundamentals "
        "WHERE ticker = ? AND as_of <= ? ORDER BY as_of DESC LIMIT 1",
        [ticker, ts_emitted.date()],
    ).fetchone()
    if row is None or row[0] is None:
        return None, True
    return row[0], False


def compute_leverage(conn: duckdb.DuckDBPyConnection, *,
                     ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_fundamentals_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    row = conn.execute(
        "SELECT debt_to_equity FROM fundamentals "
        "WHERE ticker = ? AND as_of <= ? ORDER BY as_of DESC LIMIT 1",
        [ticker, ts_emitted.date()],
    ).fetchone()
    if row is None or row[0] is None:
        return None, True
    return row[0], False


def compute_earnings_growth(conn: duckdb.DuckDBPyConnection, *,
                            ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_fundamentals_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    rows = conn.execute(
        "SELECT as_of, net_income_ttm FROM fundamentals "
        "WHERE ticker = ? AND as_of <= ? ORDER BY as_of DESC LIMIT 2",
        [ticker, ts_emitted.date()],
    ).fetchall()
    if len(rows) < 2:
        return None, True
    curr, prev = rows[0][1], rows[1][1]
    if curr is None or prev is None or prev == 0:
        return None, True
    return (curr - prev) / abs(prev), False


def _zscore(value: float, mean: float | None, std: float | None) -> float:
    """Z-score a value; returns 0.0 if std is None or zero (can't discriminate)."""
    if mean is None or std is None or std == 0:
        return 0.0
    return (value - mean) / std


def compute_quality_score(
    conn: duckdb.DuckDBPyConnection, *,
    ticker: str,
    ts_emitted: datetime,
    roe_value: float | None,
    leverage_value: float | None,
    earnings_growth_value: float | None,
    **_,
) -> Result:
    """Cross-sectional equal-weighted z-score of (roe, -leverage, earnings_growth).

    Requires all three input values non-None and >= MIN_CROSS_SECTION_COUNT tickers
    with roe + debt_to_equity data in fundamentals as_of ts_emitted.
    """
    if roe_value is None or leverage_value is None or earnings_growth_value is None:
        return None, True

    as_of = ts_emitted.date()

    # Cross-sectional stats for roe and leverage (latest row per ticker)
    cs_row = conn.execute(
        """
        WITH latest AS (
            SELECT ticker, MAX(as_of) AS latest_as_of
            FROM fundamentals
            WHERE as_of <= ?
            GROUP BY ticker
        )
        SELECT
            AVG(f.roe),              STDDEV_SAMP(f.roe),
            AVG(f.debt_to_equity),   STDDEV_SAMP(f.debt_to_equity),
            COUNT(*)
        FROM latest l
        JOIN fundamentals f ON f.ticker = l.ticker AND f.as_of = l.latest_as_of
        WHERE f.roe IS NOT NULL AND f.debt_to_equity IS NOT NULL
        """,
        [as_of],
    ).fetchone()

    if cs_row is None or cs_row[4] is None or cs_row[4] < MIN_CROSS_SECTION_COUNT:
        return None, True

    mean_roe, std_roe, mean_lev, std_lev, _ = cs_row

    # Cross-sectional earnings growth stats (requires 2 rows per ticker)
    eg_row = conn.execute(
        """
        WITH ranked AS (
            SELECT ticker, as_of, net_income_ttm,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY as_of DESC) AS rn
            FROM fundamentals
            WHERE as_of <= ?
        ),
        growth AS (
            SELECT (c.net_income_ttm - p.net_income_ttm)
                       / NULLIF(ABS(p.net_income_ttm), 0) AS eg
            FROM ranked c
            JOIN ranked p ON c.ticker = p.ticker AND p.rn = 2
            WHERE c.rn = 1
              AND c.net_income_ttm IS NOT NULL
              AND p.net_income_ttm IS NOT NULL
        )
        SELECT AVG(eg), STDDEV_SAMP(eg)
        FROM growth
        """,
        [as_of],
    ).fetchone()

    mean_eg = eg_row[0] if eg_row else None
    std_eg  = eg_row[1] if eg_row else None

    z_roe = _zscore(roe_value, mean_roe, std_roe)
    z_lev = -_zscore(leverage_value, mean_lev, std_lev)   # lower leverage → better
    z_eg  = _zscore(earnings_growth_value, mean_eg, std_eg)

    return (z_roe + z_lev + z_eg) / 3.0, False
