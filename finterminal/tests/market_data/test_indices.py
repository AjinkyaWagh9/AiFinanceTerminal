from datetime import date
from pathlib import Path
from finterminal.market_data.nse_indices import parse_csv, url_for

FIX = Path(__file__).parents[1] / "fixtures" / "market_data" / "ind_close_all_29042026.csv"

def test_parse_extracts_nifty50_only():
    rows = parse_csv(FIX.read_bytes(), trade_date=date(2026, 4, 29))
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "_NIFTY50"
    assert r["close"] == 22550.0
    assert r["open"]  == 22500.0
    assert r["high"]  == 22580.0
    assert r["low"]   == 22480.0
    assert r["volume"] == 300_000_000

def test_url_for_uses_ddmmyyyy():
    u = url_for(date(2026, 4, 29))
    assert "ind_close_all_29042026.csv" in u
    assert u.startswith("https://nsearchives.nseindia.com/")
