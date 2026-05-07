# tests/market_data/test_ingestion.py
from datetime import date
from unittest.mock import patch
from finterminal.data.duckdb_store import connect
from finterminal.market_data.ingestion import refresh_prices
from finterminal.market_data._http import Http404

def _bhav_blob():  # reuse fixture
    from pathlib import Path
    p = Path(__file__).parents[1] / "fixtures" / "market_data" / "cm29APR2026bhav.csv.zip"
    return p.read_bytes()

def _idx_blob():
    from pathlib import Path
    p = Path(__file__).parents[1] / "fixtures" / "market_data" / "ind_close_all_29042026.csv"
    return p.read_bytes()

def test_refresh_prices_walks_window_and_skips_holidays(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))

    def fake_fetch(url):
        if "cm29APR2026" in url: return _bhav_blob()
        if "29042026" in url:    return _idx_blob()
        raise Http404(url)

    with patch("finterminal.market_data.ingestion._http.fetch", side_effect=fake_fetch):
        result = refresh_prices(conn,
                                start=date(2026, 4, 28),  # Tue
                                end=date(2026, 5, 1))      # Fri (Maharashtra Day = holiday)

    assert result["dates_attempted"] == [date(2026, 4, 28), date(2026, 4, 29), date(2026, 4, 30)]
    assert date(2026, 5, 1) in result["dates_skipped_holiday"]

    log_rows = conn.execute(
        "SELECT target_date, status FROM ingestion_log ORDER BY target_date"
    ).fetchall()
    statuses = {(d, s) for d, s in log_rows}
    assert (date(2026, 5, 1), "skipped_holiday") in statuses

def test_refresh_prices_handles_404_per_date(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    with patch("finterminal.market_data.ingestion._http.fetch", side_effect=Http404("x")):
        refresh_prices(conn, start=date(2026, 4, 29), end=date(2026, 4, 29))
    rows = conn.execute(
        "SELECT status FROM ingestion_log WHERE target_date = ?", [date(2026, 4, 29)]
    ).fetchall()
    statuses = {r[0] for r in rows}
    assert statuses == {"skipped_holiday"}  # 404 → treated as holiday

def test_refresh_prices_skips_already_ingested_days(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    calls: list[str] = []

    def fake_fetch(url):
        calls.append(url)
        if "cm29APR2026" in url: return _bhav_blob()
        if "29042026" in url:    return _idx_blob()
        raise Http404(url)

    with patch("finterminal.market_data.ingestion._http.fetch", side_effect=fake_fetch):
        first = refresh_prices(conn, start=date(2026, 4, 29), end=date(2026, 4, 29))
        first_calls = len(calls)
        second = refresh_prices(conn, start=date(2026, 4, 29), end=date(2026, 4, 29))

    assert first["dates_attempted"] == [date(2026, 4, 29)]
    assert second["dates_attempted"] == []
    assert second["dates_already_ingested"] == [date(2026, 4, 29)]
    assert len(calls) == first_calls  # no extra HTTP on the second pass
