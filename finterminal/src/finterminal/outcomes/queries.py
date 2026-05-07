# src/finterminal/outcomes/queries.py
from __future__ import annotations
import duckdb
from .schema import SignalType, Engine


def predictive_power(conn: duckdb.DuckDBPyConnection, *,
                     signal_type: SignalType, horizon: int) -> dict:
    row = conn.execute(
        """
        SELECT COUNT(*),
               AVG(o.ret_pct),
               AVG(o.ret_pct_vs_nifty)
        FROM signals s
        JOIN signal_outcomes o USING (signal_id)
        WHERE s.signal_type = ?
          AND o.horizon_days = ?
          AND o.resolved_at IS NOT NULL
        """,
        [signal_type.value, horizon],
    ).fetchone()
    return {"n": row[0], "mean_ret": row[1], "mean_alpha": row[2]}


def engine_summary(conn: duckdb.DuckDBPyConnection, *,
                   engine: Engine, horizon: int) -> dict:
    row = conn.execute(
        """
        SELECT COUNT(*),
               AVG(o.ret_pct),
               AVG(o.ret_pct_vs_nifty)
        FROM signals s
        JOIN signal_outcomes o USING (signal_id)
        WHERE s.engine = ?
          AND o.horizon_days = ?
          AND o.resolved_at IS NOT NULL
        """,
        [engine.value, horizon],
    ).fetchone()
    return {"n": row[0], "mean_ret": row[1], "mean_alpha": row[2]}
