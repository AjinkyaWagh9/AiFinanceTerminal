# src/finterminal/market_data/ingestion.py
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Any

import duckdb

from . import _http, calendar, nse_bhavcopy, nse_indices, normalize, store

log = logging.getLogger(__name__)

_SOURCES: list[tuple[str, Any, Any]] = [
    ("nse_bhavcopy", nse_bhavcopy.url_for, nse_bhavcopy.parse_zip),
    ("nse_indices",  nse_indices.url_for,  nse_indices.parse_csv),
]

def refresh_prices(conn: duckdb.DuckDBPyConnection, *,
                   start: date, end: date) -> dict[str, list[date]]:
    attempted: list[date] = []
    skipped:   list[date] = []
    cached:    list[date] = []
    d = start
    while d <= end:
        if not calendar.is_trading_day(d):
            for source, _, _ in _SOURCES:
                if store.has_ok_ingestion(conn, source=source, target_date=d):
                    continue
                log_id = store.log_start(conn, source=source, target_date=d)
                store.log_finish(conn, log_id, status="skipped_holiday")
            skipped.append(d)
        else:
            all_cached = all(
                store.has_ok_ingestion(conn, source=source, target_date=d)
                for source, _, _ in _SOURCES
            )
            if all_cached:
                cached.append(d)
                d += timedelta(days=1)
                continue
            attempted.append(d)
            for source, url_for, parse in _SOURCES:
                if store.has_ok_ingestion(conn, source=source, target_date=d):
                    continue
                log_id = store.log_start(conn, source=source, target_date=d)
                try:
                    blob = _http.fetch(url_for(d))
                    rows = parse(blob, trade_date=d)
                    rows = normalize.apply(rows)
                    n = store.upsert_prices_eod(conn, rows, source=source)
                    store.log_finish(conn, log_id, status="ok", rows_written=n)
                except _http.Http404:
                    store.log_finish(conn, log_id, status="skipped_holiday", http_code=404)
                except _http.Http429:
                    store.log_finish(conn, log_id, status="http_error", http_code=429)
                except Exception as e:
                    log.exception("ingest %s %s failed", source, d)
                    store.log_finish(conn, log_id, status="parse_error", note=str(e)[:200])
        d += timedelta(days=1)
    return {
        "dates_attempted": attempted,
        "dates_skipped_holiday": skipped,
        "dates_already_ingested": cached,
    }
