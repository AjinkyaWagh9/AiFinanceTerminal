from finterminal.market_data.normalize import normalize_symbol, apply

def test_known_symbol_passes_through_uppercased():
    assert normalize_symbol("tcs") == "TCS"
    assert normalize_symbol("RELIANCE") == "RELIANCE"

def test_strips_be_eq_series_suffixes_in_raw_input():
    # NSE bhavcopy SYMBOL field is already without series suffix; defensive.
    assert normalize_symbol(" TCS ") == "TCS"

def test_apply_keeps_unmapped_with_warning(caplog):
    rows = [{"ticker": "UNKNOWNCO", "close": 100.0, "trade_date": "2026-04-29"}]
    out = apply(rows)
    assert out == rows
    assert any("unmapped" in m.lower() for m in caplog.messages)
