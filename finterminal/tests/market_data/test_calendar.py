import logging
from datetime import date
from finterminal.market_data.calendar import is_holiday, is_trading_day
import finterminal.market_data.calendar as cal

def test_known_2026_holiday_republic_day():
    assert is_holiday(date(2026, 1, 26)) is True

def test_weekend_is_not_trading_day():
    assert is_trading_day(date(2026, 5, 2)) is False  # Saturday
    assert is_trading_day(date(2026, 5, 3)) is False  # Sunday

def test_regular_weekday_is_trading_day():
    assert is_trading_day(date(2026, 5, 4)) is True   # Monday, not a holiday

def test_known_2025_holiday_gandhi_jayanti():
    assert is_holiday(date(2025, 10, 2)) is True
    assert is_trading_day(date(2025, 10, 2)) is False

def test_unsupported_year_warns_once_and_returns_false(caplog):
    cal._WARNED_YEARS.discard(2099)
    with caplog.at_level(logging.WARNING, logger="finterminal.market_data.calendar"):
        assert is_holiday(date(2099, 1, 1)) is False
        assert is_holiday(date(2099, 6, 15)) is False
    warnings = [r for r in caplog.records if "no holiday list for year 2099" in r.message]
    assert len(warnings) == 1
