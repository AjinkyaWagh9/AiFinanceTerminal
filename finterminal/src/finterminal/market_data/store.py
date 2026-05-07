# src/finterminal/market_data/store.py
from __future__ import annotations
import uuid
from datetime import date, datetime
from typing import Iterable

import duckdb

def upsert_prices_eod(conn: duckdb.DuckDBPyConnection,
                      rows: Iterable[dict], *, source: str) -> int:
    """Insert rows; rows whose (ticker, trade_date) already exist are skipped.
    Returns count of NEW rows inserted."""
    rows = list(rows)
    if not rows:
        return 0
    now = datetime.now()
    before = conn.execute("SELECT COUNT(*) FROM prices_eod").fetchone()[0]
    conn.executemany(
        """
        INSERT INTO prices_eod
            (trade_date, ticker, open, high, low, close, volume, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (ticker, trade_date) DO NOTHING
        """,
        [(r["trade_date"], r["ticker"],
          r.get("open"), r.get("high"), r.get("low"), r["close"], r.get("volume"),
          source, now) for r in rows],
    )
    after = conn.execute("SELECT COUNT(*) FROM prices_eod").fetchone()[0]
    return after - before

def last_close_on_or_before(conn: duckdb.DuckDBPyConnection,
                            ticker: str, target: date) -> float | None:
    row = conn.execute(
        """
        SELECT close FROM prices_eod
        WHERE ticker = ? AND trade_date <= ?
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        [ticker, target],
    ).fetchone()
    return row[0] if row else None

def has_ok_ingestion(conn: duckdb.DuckDBPyConnection, *,
                     source: str, target_date: date) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ingestion_log "
        "WHERE source = ? AND target_date = ? AND status = 'ok' LIMIT 1",
        [source, target_date],
    ).fetchone()
    return row is not None

def log_start(conn: duckdb.DuckDBPyConnection, *,
              source: str, target_date: date) -> str:
    log_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO ingestion_log (id, source, target_date, started_at, status) "
        "VALUES (?, ?, ?, ?, 'started')",
        [log_id, source, target_date, datetime.now()],
    )
    return log_id

def log_finish(conn: duckdb.DuckDBPyConnection, log_id: str, *,
               status: str, rows_written: int | None = None,
               http_code: int | None = None, note: str | None = None) -> None:
    conn.execute(
        "UPDATE ingestion_log SET finished_at=?, status=?, rows_written=?, "
        "http_code=?, note=? WHERE id=?",
        [datetime.now(), status, rows_written, http_code, note, log_id],
    )
