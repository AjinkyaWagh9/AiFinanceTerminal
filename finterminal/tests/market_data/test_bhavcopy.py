from datetime import date
from pathlib import Path
from finterminal.market_data.nse_bhavcopy import parse_zip, url_for

FIX = Path(__file__).parents[1] / "fixtures" / "market_data" / "cm29APR2026bhav.csv.zip"

def test_parse_returns_only_eq_series():
    rows = parse_zip(FIX.read_bytes(), trade_date=date(2026, 4, 29))
    syms = [r["ticker"] for r in rows]
    assert "TCS" in syms and "RELIANCE" in syms
    assert sum(1 for s in syms if s == "TCS") == 1  # BE row dropped

def test_parse_yields_full_ohlcv():
    rows = parse_zip(FIX.read_bytes(), trade_date=date(2026, 4, 29))
    tcs = next(r for r in rows if r["ticker"] == "TCS")
    assert tcs == {
        "trade_date": date(2026, 4, 29),
        "ticker": "TCS",
        "open": 3500.0, "high": 3550.0, "low": 3490.0, "close": 3540.0,
        "volume": 1_000_000,
    }

def test_url_for_uses_nsearchives_host():
    u = url_for(date(2026, 4, 29))
    assert u.startswith("https://nsearchives.nseindia.com/")
    assert "cm29APR2026bhav.csv.zip" in u
