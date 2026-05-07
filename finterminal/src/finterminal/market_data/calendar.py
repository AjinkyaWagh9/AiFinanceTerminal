from __future__ import annotations
import logging
from datetime import date

log = logging.getLogger(__name__)

# NSE official trading holidays. Verify annually.
# Source: https://www.nseindia.com/resources/exchange-communication-holidays
_HOLIDAYS_2025: frozenset[date] = frozenset({
    date(2025, 2, 26),  # Maha Shivratri
    date(2025, 3, 14),  # Holi
    date(2025, 3, 31),  # Eid-ul-Fitr
    date(2025, 4, 10),  # Mahavir Jayanti
    date(2025, 4, 14),  # Dr. Ambedkar Jayanti
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 1),   # Maharashtra Day
    date(2025, 8, 15),  # Independence Day
    date(2025, 8, 27),  # Ganesh Chaturthi
    date(2025, 10, 2),  # Mahatma Gandhi Jayanti
    date(2025, 10, 21), # Diwali (Laxmi Pujan)
    date(2025, 10, 22), # Diwali Balipratipada
    date(2025, 11, 5),  # Prakash Gurpurb
    date(2025, 12, 25), # Christmas
})

_HOLIDAYS_2026: frozenset[date] = frozenset({
    date(2026, 1, 26),  # Republic Day
    date(2026, 3, 6),   # Holi
    date(2026, 3, 19),  # Eid-ul-Fitr (tentative)
    date(2026, 4, 3),   # Good Friday
    date(2026, 4, 14),  # Dr. Ambedkar Jayanti
    date(2026, 5, 1),   # Maharashtra Day
    date(2026, 5, 27),  # Eid-ul-Adha (tentative)
    date(2026, 8, 15),  # Independence Day
    date(2026, 8, 27),  # Ganesh Chaturthi (tentative)
    date(2026, 10, 2),  # Mahatma Gandhi Jayanti
    date(2026, 11, 20), # Diwali (Laxmi Pujan, tentative)
    date(2026, 12, 25), # Christmas
})

_HOLIDAYS_BY_YEAR: dict[int, frozenset[date]] = {
    2025: _HOLIDAYS_2025,
    2026: _HOLIDAYS_2026,
}
_WARNED_YEARS: set[int] = set()

def is_holiday(d: date) -> bool:
    holidays = _HOLIDAYS_BY_YEAR.get(d.year)
    if holidays is None:
        if d.year not in _WARNED_YEARS:
            log.warning("calendar: no holiday list for year %d; weekdays will "
                        "be treated as trading days. Update calendar.py.", d.year)
            _WARNED_YEARS.add(d.year)
        return False
    return d in holidays

def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and not is_holiday(d)
