# Foundation: Outcomes Ledger + Engine Taxonomy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two complementary upstream pipelines — NSE bhavcopy market-data ingest and the signals→outcomes ledger — plus the wiring that lets every signal the news pipeline emits get measured against forward returns vs Nifty 50.

**Architecture:** Two independent pipelines, merged only inside the analytics ledger.
- `market_data/` owns `prices_eod` (OHLCV) + `ingestion_log`. Pulls NSE bhavcopy daily zip + indices CSV.
- `outcomes/` owns `signals` + `signal_outcomes`. Reads `prices_eod` to resolve forward returns.
- `news/cluster.py` gets a fail-safe `emit_signal` call behind `OUTCOMES_LEDGER_ENABLED`.

**Tech Stack:** Python 3.12, DuckDB (vss already wired), uv, pytest, requests, scipy. Reuses `data/india/nse_universe.py` for ticker normalization.

**Spec:** `docs/superpowers/specs/2026-04-29-foundation-outcomes-engines-design.md`

---

## File Structure

**Create:**
```
src/finterminal/data/migrations/004_outcomes_ledger.sql
src/finterminal/outcomes/__init__.py
src/finterminal/outcomes/schema.py
src/finterminal/outcomes/ledger.py
src/finterminal/outcomes/backfill.py
src/finterminal/outcomes/backfill_historical.py
src/finterminal/outcomes/queries.py
src/finterminal/outcomes/engines/__init__.py
src/finterminal/outcomes/engines/base.py
src/finterminal/market_data/__init__.py
src/finterminal/market_data/_http.py
src/finterminal/market_data/calendar.py
src/finterminal/market_data/normalize.py
src/finterminal/market_data/nse_bhavcopy.py
src/finterminal/market_data/nse_indices.py
src/finterminal/market_data/store.py
src/finterminal/market_data/ingestion.py
src/finterminal/market_data/macro.py
tests/outcomes/test_schema.py
tests/outcomes/test_ledger.py
tests/outcomes/test_backfill.py
tests/outcomes/test_queries.py
tests/outcomes/test_backfill_historical.py
tests/market_data/test_http.py
tests/market_data/test_calendar.py
tests/market_data/test_normalize.py
tests/market_data/test_bhavcopy.py
tests/market_data/test_indices.py
tests/market_data/test_store.py
tests/market_data/test_ingestion.py
tests/market_data/test_macro.py
tests/integration/test_foundation_e2e.py
tests/fixtures/market_data/cm29APR2026bhav.csv.zip
tests/fixtures/market_data/ind_close_all_29042026.csv
```

**Modify:**
```
src/finterminal/data/duckdb_store.py     # apply migration 004
src/finterminal/news/cluster.py          # wire emit_signal (fail-safe)
src/finterminal/commands.py              # /refresh-prices, /backfill-outcomes
src/finterminal/config.py (or equivalent)# add OUTCOMES_LEDGER_ENABLED flag
```

**Boundaries:**
- `market_data/` MUST NOT import from `outcomes/`. Enforced by test that greps imports.
- `outcomes/` MAY import from `market_data/` (specifically `store.last_close_on_or_before`, `macro.nifty_pct_50d`).
- `news/cluster.py` calls `outcomes.ledger.emit_signal` only inside a try/except behind `OUTCOMES_LEDGER_ENABLED`.

---

## Task 1: Migration 004 — schema for signals, signal_outcomes, prices_eod, ingestion_log

**Files:**
- Create: `src/finterminal/data/migrations/004_outcomes_ledger.sql`
- Modify: `src/finterminal/data/duckdb_store.py` (apply on connect)
- Test: `tests/outcomes/test_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/outcomes/test_schema.py
import duckdb
from finterminal.data.duckdb_store import connect

def test_migration_004_creates_all_tables(tmp_path):
    db_path = tmp_path / "t.duckdb"
    conn = connect(str(db_path))
    tables = {r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()}
    for t in ("signals", "signal_outcomes", "prices_eod", "ingestion_log"):
        assert t in tables, f"missing table: {t}"

def test_signals_unique_constraint(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    conn.execute("""
        INSERT INTO signals (signal_id, signal_type, engine, ticker, ts_emitted)
        VALUES ('a', 'cluster_momentum', 'reflexivity', 'TCS', '2026-04-29 10:00:00')
    """)
    import pytest, duckdb
    with pytest.raises(duckdb.ConstraintException):
        conn.execute("""
            INSERT INTO signals (signal_id, signal_type, engine, ticker, ts_emitted)
            VALUES ('b', 'cluster_momentum', 'reflexivity', 'TCS', '2026-04-29 10:00:00')
        """)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/outcomes/test_schema.py -v`
Expected: FAIL — tables don't exist.

- [ ] **Step 3: Write the migration**

```sql
-- src/finterminal/data/migrations/004_outcomes_ledger.sql
-- Sub-project #1: outcomes ledger + price store + ingestion log.
-- Conventions match 003: VARCHAR, IF NOT EXISTS, naive TIMESTAMP (IST), no FK constraints.

CREATE TABLE IF NOT EXISTS signals (
    signal_id     VARCHAR PRIMARY KEY,
    signal_type   VARCHAR NOT NULL,
    engine        VARCHAR NOT NULL,
    ticker        VARCHAR NOT NULL,
    ts_emitted    TIMESTAMP NOT NULL,
    payload       JSON,
    confidence    DOUBLE,
    why           VARCHAR,
    source_ref    VARCHAR,
    regime_nifty_close       DOUBLE,
    regime_nifty_pct_50d     DOUBLE,
    regime_india_vix         DOUBLE,
    regime_inr_usd           DOUBLE,
    regime_brent_usd         DOUBLE,
    regime_india_10y_yield   DOUBLE,
    UNIQUE (signal_type, ticker, ts_emitted)
);

CREATE INDEX IF NOT EXISTS signals_ticker_ts_idx ON signals(ticker, ts_emitted);
CREATE INDEX IF NOT EXISTS signals_engine_ts_idx ON signals(engine, ts_emitted);
CREATE INDEX IF NOT EXISTS signals_type_ts_idx   ON signals(signal_type, ts_emitted);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_id        VARCHAR NOT NULL,
    horizon_days     INTEGER NOT NULL,
    ret_pct          DOUBLE,
    ret_pct_vs_nifty DOUBLE,
    resolved_at      TIMESTAMP,
    PRIMARY KEY (signal_id, horizon_days)
);

CREATE INDEX IF NOT EXISTS signal_outcomes_unresolved_idx
    ON signal_outcomes(resolved_at);

CREATE TABLE IF NOT EXISTS prices_eod (
    trade_date  DATE    NOT NULL,
    ticker      VARCHAR NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE  NOT NULL,
    volume      BIGINT,
    source      VARCHAR NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS prices_eod_date_idx ON prices_eod(trade_date);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id            VARCHAR PRIMARY KEY,
    source        VARCHAR NOT NULL,
    target_date   DATE    NOT NULL,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    status        VARCHAR NOT NULL,
    rows_written  INTEGER,
    http_code     INTEGER,
    note          VARCHAR
);

CREATE INDEX IF NOT EXISTS ingestion_log_source_date_idx
    ON ingestion_log(source, target_date);
```

- [ ] **Step 4: Wire migration into the store**

Locate the migration-runner in `src/finterminal/data/duckdb_store.py` (look for the loop that applies `00X_*.sql` files) and ensure `004_outcomes_ledger.sql` is included by ordering. If migrations are listed explicitly, append `"004_outcomes_ledger.sql"` to the list. Do not change the order of existing migrations.

- [ ] **Step 5: Run tests — pass**

Run: `uv run pytest tests/outcomes/test_schema.py -v`
Expected: PASS.

- [ ] **Step 6: Run full suite**

Run: `uv run pytest -x`
Expected: 175 passing (173 existing + 2 new).

- [ ] **Step 7: Commit**

```bash
git add src/finterminal/data/migrations/004_outcomes_ledger.sql \
        src/finterminal/data/duckdb_store.py \
        tests/outcomes/test_schema.py
git commit -m "feat(outcomes): add migration 004 for signals/outcomes/prices_eod/ingestion_log"
```

---

## Task 2: outcomes/schema.py — engine + signal_type enums, registry, constants

**Files:**
- Create: `src/finterminal/outcomes/__init__.py` (empty)
- Create: `src/finterminal/outcomes/schema.py`
- Test: `tests/outcomes/test_schema.py` (extend)

- [ ] **Step 1: Extend the test**

```python
# tests/outcomes/test_schema.py — append:
from finterminal.outcomes.schema import (
    Engine, SignalType, SIGNAL_REGISTRY,
    HORIZONS_DAYS, MACRO_TICKER, NIFTY_TICKER,
)

def test_engines_are_lowercase_strings():
    assert {e.value for e in Engine} == {
        "mispricing", "quality", "regime", "reflexivity", "risk"
    }

def test_signal_registry_covers_every_signal_type():
    assert set(SIGNAL_REGISTRY.keys()) == set(SignalType)

def test_signal_registry_engines_are_valid():
    for e in SIGNAL_REGISTRY.values():
        assert isinstance(e, Engine)

def test_horizons_are_canonical():
    assert HORIZONS_DAYS == (1, 7, 30, 90, 365)

def test_sentinel_tickers():
    assert MACRO_TICKER == "_MACRO"
    assert NIFTY_TICKER == "_NIFTY50"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/outcomes/test_schema.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement schema.py**

```python
# src/finterminal/outcomes/schema.py
from __future__ import annotations
from enum import Enum

class Engine(str, Enum):
    MISPRICING  = "mispricing"
    QUALITY     = "quality"
    REGIME      = "regime"
    REFLEXIVITY = "reflexivity"
    RISK        = "risk"

class SignalType(str, Enum):
    CLUSTER_MOMENTUM     = "cluster_momentum"
    DIVERGENCE           = "divergence"
    SENTIMENT_DELTA      = "sentiment_delta"
    CLAIM_RECONCILIATION = "claim_reconciliation"
    REGIME_SHIFT         = "regime_shift"
    RISK_TRIGGER         = "risk_trigger"

SIGNAL_REGISTRY: dict[SignalType, Engine] = {
    SignalType.CLUSTER_MOMENTUM:     Engine.REFLEXIVITY,
    SignalType.DIVERGENCE:           Engine.MISPRICING,
    SignalType.SENTIMENT_DELTA:      Engine.REFLEXIVITY,
    SignalType.CLAIM_RECONCILIATION: Engine.QUALITY,
    SignalType.REGIME_SHIFT:         Engine.REGIME,
    SignalType.RISK_TRIGGER:         Engine.RISK,
}

HORIZONS_DAYS: tuple[int, ...] = (1, 7, 30, 90, 365)

MACRO_TICKER = "_MACRO"
NIFTY_TICKER = "_NIFTY50"

REGIME_FIELDS: tuple[str, ...] = (
    "regime_nifty_close",
    "regime_nifty_pct_50d",
    "regime_india_vix",
    "regime_inr_usd",
    "regime_brent_usd",
    "regime_india_10y_yield",
)
```

- [ ] **Step 4: Run — pass**

Run: `uv run pytest tests/outcomes/test_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/outcomes/__init__.py src/finterminal/outcomes/schema.py tests/outcomes/test_schema.py
git commit -m "feat(outcomes): add Engine/SignalType enums + SIGNAL_REGISTRY"
```

---

## Task 3: market_data/_http.py + calendar.py — NSE-friendly fetcher and holiday detection

**Files:**
- Create: `src/finterminal/market_data/__init__.py` (empty)
- Create: `src/finterminal/market_data/_http.py`
- Create: `src/finterminal/market_data/calendar.py`
- Test: `tests/market_data/test_http.py`, `tests/market_data/test_calendar.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/market_data/test_http.py
import pytest
from unittest.mock import patch, Mock
from finterminal.market_data._http import fetch, Http404, Http429

def _resp(status, content=b"x"):
    r = Mock()
    r.status_code = status
    r.content = content
    return r

def test_fetch_returns_bytes_on_200():
    with patch("finterminal.market_data._http.requests.get",
               return_value=_resp(200, b"hello")):
        assert fetch("http://x") == b"hello"

def test_fetch_raises_404():
    with patch("finterminal.market_data._http.requests.get",
               return_value=_resp(404)):
        with pytest.raises(Http404):
            fetch("http://x")

def test_fetch_retries_once_on_429_then_raises():
    calls = [_resp(429), _resp(429)]
    with patch("finterminal.market_data._http.requests.get",
               side_effect=calls), \
         patch("finterminal.market_data._http.time.sleep") as sleep:
        with pytest.raises(Http429):
            fetch("http://x")
        sleep.assert_called()  # backoff happened

def test_fetch_recovers_after_one_429():
    with patch("finterminal.market_data._http.requests.get",
               side_effect=[_resp(429), _resp(200, b"ok")]), \
         patch("finterminal.market_data._http.time.sleep"):
        assert fetch("http://x") == b"ok"
```

```python
# tests/market_data/test_calendar.py
from datetime import date
from finterminal.market_data.calendar import is_holiday, is_trading_day

def test_known_2026_holiday_republic_day():
    assert is_holiday(date(2026, 1, 26)) is True

def test_weekend_is_not_trading_day():
    assert is_trading_day(date(2026, 5, 2)) is False  # Saturday
    assert is_trading_day(date(2026, 5, 3)) is False  # Sunday

def test_regular_weekday_is_trading_day():
    assert is_trading_day(date(2026, 5, 4)) is True   # Monday, not a holiday
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/market_data -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement _http.py**

```python
# src/finterminal/market_data/_http.py
from __future__ import annotations
import time
import requests

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
_RATE_LIMIT_SECONDS = 1.0
_BACKOFF_SECONDS = 5.0
_TIMEOUT = 20

class Http404(Exception): ...
class Http429(Exception): ...

_session: requests.Session | None = None

def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(_HEADERS)
        try:
            s.get("https://www.nseindia.com", timeout=_TIMEOUT)  # cookie warm-up
        except Exception:
            pass
        _session = s
    return _session

def fetch(url: str, *, _attempt: int = 0) -> bytes:
    session = _get_session()
    time.sleep(_RATE_LIMIT_SECONDS)
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT,
                        cookies=session.cookies)
    if resp.status_code == 200:
        return resp.content
    if resp.status_code == 404:
        raise Http404(url)
    if resp.status_code == 429:
        if _attempt == 0:
            time.sleep(_BACKOFF_SECONDS)
            return fetch(url, _attempt=1)
        raise Http429(url)
    raise RuntimeError(f"unexpected status {resp.status_code} for {url}")
```

- [ ] **Step 4: Implement calendar.py**

```python
# src/finterminal/market_data/calendar.py
from __future__ import annotations
from datetime import date

# NSE official trading holidays for 2026 (verify annually).
# Source: https://www.nseindia.com/resources/exchange-communication-holidays
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

def is_holiday(d: date) -> bool:
    return d in _HOLIDAYS_2026

def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and not is_holiday(d)
```

- [ ] **Step 5: Run — pass**

Run: `uv run pytest tests/market_data/test_http.py tests/market_data/test_calendar.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/market_data/__init__.py \
        src/finterminal/market_data/_http.py \
        src/finterminal/market_data/calendar.py \
        tests/market_data/
git commit -m "feat(market_data): add NSE-friendly HTTP fetcher and holiday calendar"
```

---

## Task 4: market_data/normalize.py — NSE symbol → internal ticker

**Files:**
- Create: `src/finterminal/market_data/normalize.py`
- Test: `tests/market_data/test_normalize.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/market_data/test_normalize.py
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
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/market_data/test_normalize.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/finterminal/market_data/normalize.py
from __future__ import annotations
import logging
from typing import Iterable, Sequence

from finterminal.data.india.nse_universe import load_universe

log = logging.getLogger(__name__)

def normalize_symbol(raw: str) -> str:
    return raw.strip().upper()

def apply(rows: Sequence[dict]) -> list[dict]:
    universe = load_universe()
    known = {sym.upper() for sym in universe.symbols()}
    out: list[dict] = []
    for row in rows:
        sym = normalize_symbol(row["ticker"])
        if sym not in known and not sym.startswith("_"):
            log.warning("unmapped NSE symbol %s — passing through", sym)
        out.append({**row, "ticker": sym})
    return out
```

Note: `load_universe()` exists per `src/finterminal/data/india/nse_universe.py`. If its API differs, adapt the call — the contract is "give me the set of known NSE symbols". The bhavcopy fixture must include at least one symbol from `EQUITY_L.csv` and one outside it to exercise both paths.

- [ ] **Step 4: Run — pass**

Run: `uv run pytest tests/market_data/test_normalize.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/market_data/normalize.py tests/market_data/test_normalize.py
git commit -m "feat(market_data): NSE symbol normalization + unmapped-symbol logging"
```

---

## Task 5: market_data/nse_bhavcopy.py — daily equity zip parser

**Files:**
- Create: `src/finterminal/market_data/nse_bhavcopy.py`
- Create: `tests/fixtures/market_data/cm29APR2026bhav.csv.zip` (synthetic, see step 3)
- Test: `tests/market_data/test_bhavcopy.py`

NSE bhavcopy zip contains a single CSV with columns: `SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN`. We keep only `SERIES='EQ'`.

- [ ] **Step 1: Write the fixture**

Create `tests/fixtures/market_data/_make_fixture.py` (one-off helper, committed alongside the zip):

```python
# tests/fixtures/market_data/_make_fixture.py
import io, zipfile, pathlib
HERE = pathlib.Path(__file__).parent
CSV = (
    "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN\n"
    "TCS,EQ,3500.00,3550.00,3490.00,3540.00,3540.00,3500.00,1000000,3.5e9,29-APR-2026,50000,INE467B01029\n"
    "RELIANCE,EQ,2900.00,2920.00,2880.00,2910.00,2910.00,2900.00,2000000,5.8e9,29-APR-2026,80000,INE002A01018\n"
    "TCS,BE,3500.00,3500.00,3500.00,3500.00,3500.00,3500.00,0,0,29-APR-2026,0,INE467B01029\n"
)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("cm29APR2026bhav.csv", CSV)
(HERE / "cm29APR2026bhav.csv.zip").write_bytes(buf.getvalue())
```

Run it once: `uv run python tests/fixtures/market_data/_make_fixture.py`. Commit the resulting zip.

- [ ] **Step 2: Write failing tests**

```python
# tests/market_data/test_bhavcopy.py
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
```

- [ ] **Step 3: Run — fail**

Run: `uv run pytest tests/market_data/test_bhavcopy.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement**

```python
# src/finterminal/market_data/nse_bhavcopy.py
from __future__ import annotations
import csv
import io
import zipfile
from datetime import date

_BASE = "https://nsearchives.nseindia.com/content/historical/EQUITIES"
_MONTHS = ("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC")

def url_for(d: date) -> str:
    mmm = _MONTHS[d.month - 1]
    fname = f"cm{d.day:02d}{mmm}{d.year}bhav.csv.zip"
    return f"{_BASE}/{d.year}/{mmm}/{fname}"

def parse_zip(blob: bytes, *, trade_date: date) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        text = zf.read(name).decode("utf-8")
    out: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("SERIES", "").strip() != "EQ":
            continue
        out.append({
            "trade_date": trade_date,
            "ticker": row["SYMBOL"].strip(),
            "open":   float(row["OPEN"]),
            "high":   float(row["HIGH"]),
            "low":    float(row["LOW"]),
            "close":  float(row["CLOSE"]),
            "volume": int(float(row["TOTTRDQTY"])),
        })
    return out
```

- [ ] **Step 5: Run — pass**

Run: `uv run pytest tests/market_data/test_bhavcopy.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/market_data/nse_bhavcopy.py \
        tests/market_data/test_bhavcopy.py \
        tests/fixtures/market_data/
git commit -m "feat(market_data): NSE bhavcopy daily zip parser + fixture"
```

---

## Task 6: market_data/nse_indices.py — Nifty close ingest

**Files:**
- Create: `src/finterminal/market_data/nse_indices.py`
- Create: `tests/fixtures/market_data/ind_close_all_29042026.csv`
- Test: `tests/market_data/test_indices.py`

`ind_close_all_DDMMYYYY.csv` columns: `Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield`. We keep `Index Name='Nifty 50'` and store as ticker `_NIFTY50`.

- [ ] **Step 1: Write the fixture**

Create `tests/fixtures/market_data/ind_close_all_29042026.csv` literally:

```csv
Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield
Nifty 50,29-04-2026,22500.00,22580.00,22480.00,22550.00,50.0,0.22,300000000,15000.0,22.5,4.1,1.2
Nifty Bank,29-04-2026,49000.00,49200.00,48900.00,49100.00,100.0,0.20,150000000,7500.0,18.5,2.9,0.8
```

- [ ] **Step 2: Write failing tests**

```python
# tests/market_data/test_indices.py
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
```

- [ ] **Step 3: Run — fail**

Run: `uv run pytest tests/market_data/test_indices.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement**

```python
# src/finterminal/market_data/nse_indices.py
from __future__ import annotations
import csv
import io
from datetime import date

_BASE = "https://nsearchives.nseindia.com/content/indices"

def url_for(d: date) -> str:
    return f"{_BASE}/ind_close_all_{d.day:02d}{d.month:02d}{d.year}.csv"

def parse_csv(blob: bytes, *, trade_date: date) -> list[dict]:
    text = blob.decode("utf-8")
    out: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("Index Name", "").strip() != "Nifty 50":
            continue
        out.append({
            "trade_date": trade_date,
            "ticker": "_NIFTY50",
            "open":   float(row["Open Index Value"]),
            "high":   float(row["High Index Value"]),
            "low":    float(row["Low Index Value"]),
            "close":  float(row["Closing Index Value"]),
            "volume": int(float(row["Volume"])) if row.get("Volume") else None,
        })
    return out
```

- [ ] **Step 5: Run — pass**

Run: `uv run pytest tests/market_data/test_indices.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/market_data/nse_indices.py \
        tests/market_data/test_indices.py \
        tests/fixtures/market_data/ind_close_all_29042026.csv
git commit -m "feat(market_data): NSE indices CSV parser + fixture (Nifty 50)"
```

---

## Task 7: market_data/store.py — upsert prices_eod, ingestion_log helpers, last-close lookup

**Files:**
- Create: `src/finterminal/market_data/store.py`
- Test: `tests/market_data/test_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/market_data/test_store.py
from datetime import date, datetime
import uuid
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import (
    upsert_prices_eod, last_close_on_or_before,
    log_start, log_finish,
)

def _seed_rows(trade_date):
    return [
        {"trade_date": trade_date, "ticker": "TCS",
         "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000},
        {"trade_date": trade_date, "ticker": "RELIANCE",
         "open": 200.0, "high": 210.0, "low": 195.0, "close": 205.0, "volume": 2000},
    ]

def test_upsert_writes_and_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    rows = _seed_rows(date(2026, 4, 29))
    n1 = upsert_prices_eod(conn, rows, source="nse_bhavcopy")
    n2 = upsert_prices_eod(conn, rows, source="nse_bhavcopy")
    assert n1 == 2 and n2 == 0
    total = conn.execute("SELECT COUNT(*) FROM prices_eod").fetchone()[0]
    assert total == 2

def test_last_close_finds_latest_on_or_before(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [
        {"trade_date": date(2026,4,27),"ticker":"TCS","open":1,"high":1,"low":1,"close":100.0,"volume":0},
        {"trade_date": date(2026,4,29),"ticker":"TCS","open":1,"high":1,"low":1,"close":105.0,"volume":0},
    ], source="nse_bhavcopy")
    assert last_close_on_or_before(conn, "TCS", date(2026, 4, 28)) == 100.0
    assert last_close_on_or_before(conn, "TCS", date(2026, 4, 29)) == 105.0
    assert last_close_on_or_before(conn, "TCS", date(2026, 4, 26)) is None

def test_ingestion_log_lifecycle(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    log_id = log_start(conn, source="nse_bhavcopy", target_date=date(2026, 4, 29))
    log_finish(conn, log_id, status="ok", rows_written=2)
    row = conn.execute("SELECT status, rows_written, finished_at FROM ingestion_log WHERE id=?", [log_id]).fetchone()
    assert row[0] == "ok" and row[1] == 2 and row[2] is not None
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/market_data/test_store.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run — pass**

Run: `uv run pytest tests/market_data/test_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/market_data/store.py tests/market_data/test_store.py
git commit -m "feat(market_data): prices_eod upsert + ingestion_log helpers + last-close lookup"
```

---

## Task 8: market_data/ingestion.py — orchestrator + /refresh-prices command

**Files:**
- Create: `src/finterminal/market_data/ingestion.py`
- Modify: `src/finterminal/commands.py` (add `/refresh-prices`)
- Test: `tests/market_data/test_ingestion.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/market_data/test_ingestion.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement ingestion.py**

```python
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
    d = start
    while d <= end:
        if not calendar.is_trading_day(d):
            for source, _, _ in _SOURCES:
                log_id = store.log_start(conn, source=source, target_date=d)
                store.log_finish(conn, log_id, status="skipped_holiday")
            skipped.append(d)
        else:
            attempted.append(d)
            for source, url_for, parse in _SOURCES:
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
    return {"dates_attempted": attempted, "dates_skipped_holiday": skipped}
```

- [ ] **Step 4: Wire `/refresh-prices` REPL command**

Open `src/finterminal/commands.py`. Match the existing pattern used for `/refresh-news` (likely a `@command("/refresh-prices")` decorator or a dispatch table). Add:

```python
# in commands.py — match local style and imports
from datetime import date, timedelta
from finterminal.market_data.ingestion import refresh_prices

@command("/refresh-prices")
def cmd_refresh_prices(ctx, args: str = "") -> str:
    """Pull NSE bhavcopy + indices for the last 30 calendar days (idempotent)."""
    end = date.today() - timedelta(days=1)  # NSE doesn't publish today's bhav until late evening
    start = end - timedelta(days=30)
    result = refresh_prices(ctx.conn, start=start, end=end)
    return (f"Attempted {len(result['dates_attempted'])} trading days; "
            f"skipped {len(result['dates_skipped_holiday'])} non-trading days.")
```

If `commands.py` uses a different pattern (e.g., `if cmd == "/refresh-news":`), follow that pattern instead. Read 5–10 lines of context in that file first.

- [ ] **Step 5: Run — pass**

Run: `uv run pytest tests/market_data/test_ingestion.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/market_data/ingestion.py src/finterminal/commands.py tests/market_data/test_ingestion.py
git commit -m "feat(market_data): ingestion orchestrator + /refresh-prices command"
```

---

## Task 9: market_data/macro.py — regime snapshot helpers

**Files:**
- Create: `src/finterminal/market_data/macro.py`
- Test: `tests/market_data/test_macro.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/market_data/test_macro.py
from datetime import date
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.market_data.macro import snapshot_regime

def _seed_nifty(conn, series):
    rows = [{"trade_date": d, "ticker": "_NIFTY50",
             "open": v, "high": v, "low": v, "close": v, "volume": 0}
            for d, v in series]
    upsert_prices_eod(conn, rows, source="nse_indices")

def test_snapshot_regime_pct_50d_uses_50_trading_days_back(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    series = [(date.fromordinal(date(2026,1,1).toordinal()+i), 22000 + i*5)
              for i in range(120)]  # 120 calendar days, monotonic
    _seed_nifty(conn, series)
    snap = snapshot_regime(conn, as_of=date(2026, 4, 29))
    assert snap["regime_nifty_close"] == 22000 + (date(2026,4,29).toordinal()-date(2026,1,1).toordinal())*5
    # 50 calendar days back exists in series; pct should be > 0
    assert snap["regime_nifty_pct_50d"] > 0

def test_snapshot_regime_handles_missing_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    snap = snapshot_regime(conn, as_of=date(2026, 4, 29))
    assert snap["regime_nifty_close"] is None
    assert snap["regime_nifty_pct_50d"] is None
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/market_data/test_macro.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/finterminal/market_data/macro.py
from __future__ import annotations
from datetime import date, timedelta
import duckdb

from .store import last_close_on_or_before

def snapshot_regime(conn: duckdb.DuckDBPyConnection, *, as_of: date) -> dict:
    """Returns the regime_* fields for a signals row, computed at as_of date.
    Missing data → field is None. INR/Brent/10y stay None in v1 (no source yet)."""
    nifty_now  = last_close_on_or_before(conn, "_NIFTY50", as_of)
    nifty_50dB = last_close_on_or_before(conn, "_NIFTY50", as_of - timedelta(days=50))

    pct_50d = None
    if nifty_now is not None and nifty_50dB not in (None, 0):
        pct_50d = (nifty_now / nifty_50dB) - 1.0

    vix = last_close_on_or_before(conn, "_INDIAVIX", as_of)  # populated when added later

    return {
        "regime_nifty_close":      nifty_now,
        "regime_nifty_pct_50d":    pct_50d,
        "regime_india_vix":        vix,
        "regime_inr_usd":          None,
        "regime_brent_usd":        None,
        "regime_india_10y_yield":  None,
    }
```

- [ ] **Step 4: Run — pass**

Run: `uv run pytest tests/market_data/test_macro.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/market_data/macro.py tests/market_data/test_macro.py
git commit -m "feat(market_data): regime snapshot helper (nifty close + 50d pct, vix-ready)"
```

---

## Task 10: outcomes/ledger.py — emit_signal

**Files:**
- Create: `src/finterminal/outcomes/ledger.py`
- Test: `tests/outcomes/test_ledger.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/outcomes/test_ledger.py
from datetime import datetime, date
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.schema import SignalType, HORIZONS_DAYS
from finterminal.market_data.store import upsert_prices_eod

def _seed_nifty(conn):
    upsert_prices_eod(conn, [{
        "trade_date": date(2026,4,28),"ticker":"_NIFTY50",
        "open":22000,"high":22000,"low":22000,"close":22000.0,"volume":0,
    }], source="nse_indices")

def test_emit_signal_writes_signal_plus_5_outcome_stubs(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0),
        payload={"cluster_id": "c1", "story_count_delta": 5},
        confidence=0.5, why="grew 5", source_ref="c1",
    )
    assert sid is not None
    n_signals = conn.execute("SELECT COUNT(*) FROM signals WHERE signal_id=?", [sid]).fetchone()[0]
    n_out     = conn.execute("SELECT COUNT(*) FROM signal_outcomes WHERE signal_id=?", [sid]).fetchone()[0]
    assert n_signals == 1 and n_out == len(HORIZONS_DAYS)

def test_emit_signal_idempotent_on_duplicate(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    kw = dict(signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
              ts_emitted=datetime(2026, 4, 29, 10, 0),
              payload={"cluster_id": "c1"}, confidence=0.5, why="x", source_ref="c1")
    sid1 = emit_signal(conn, **kw)
    sid2 = emit_signal(conn, **kw)
    assert sid1 is not None and sid2 is None
    n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    assert n == 1

def test_emit_signal_rejects_unknown_signal_type(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    with pytest.raises((ValueError, KeyError)):
        emit_signal(conn, signal_type="not_a_real_type", ticker="TCS",
                    ts_emitted=datetime(2026, 4, 29, 10, 0))

def test_emit_signal_snapshots_regime(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0),
    )
    nifty = conn.execute(
        "SELECT regime_nifty_close FROM signals WHERE signal_id=?", [sid]
    ).fetchone()[0]
    assert nifty == 22000.0
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/outcomes/test_ledger.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/finterminal/outcomes/ledger.py
from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import Any

import duckdb

from finterminal.market_data.macro import snapshot_regime
from .schema import (
    SignalType, SIGNAL_REGISTRY, HORIZONS_DAYS, REGIME_FIELDS,
)

def emit_signal(conn: duckdb.DuckDBPyConnection, *,
                signal_type: SignalType | str,
                ticker: str,
                ts_emitted: datetime,
                payload: dict[str, Any] | None = None,
                confidence: float | None = None,
                why: str | None = None,
                source_ref: str | None = None) -> str | None:
    """Insert a signal + 5 outcome stubs. Idempotent on (signal_type, ticker, ts_emitted).
    Returns new signal_id, or None if the row was a duplicate."""
    st = SignalType(signal_type) if not isinstance(signal_type, SignalType) else signal_type
    engine = SIGNAL_REGISTRY[st]  # raises KeyError on unknown — surfaced to caller

    regime = snapshot_regime(conn, as_of=ts_emitted.date())

    signal_id = str(uuid.uuid4())
    cols = ["signal_id", "signal_type", "engine", "ticker", "ts_emitted",
            "payload", "confidence", "why", "source_ref", *REGIME_FIELDS]
    vals = [signal_id, st.value, engine.value, ticker, ts_emitted,
            json.dumps(payload) if payload is not None else None,
            confidence, why, source_ref,
            *(regime[f] for f in REGIME_FIELDS)]
    placeholders = ",".join("?" * len(cols))

    before = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.execute(
        f"INSERT INTO signals ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (signal_type, ticker, ts_emitted) DO NOTHING",
        vals,
    )
    after = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    if after == before:
        return None  # dedup'd

    conn.executemany(
        "INSERT INTO signal_outcomes (signal_id, horizon_days) VALUES (?, ?)",
        [(signal_id, h) for h in HORIZONS_DAYS],
    )
    return signal_id
```

- [ ] **Step 4: Run — pass**

Run: `uv run pytest tests/outcomes/test_ledger.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/outcomes/ledger.py tests/outcomes/test_ledger.py
git commit -m "feat(outcomes): emit_signal — idempotent write of signal + 5 horizon stubs"
```

---

## Task 11: outcomes/backfill.py — resolve_pending + /backfill-outcomes command

**Files:**
- Create: `src/finterminal/outcomes/backfill.py`
- Modify: `src/finterminal/commands.py` (add `/backfill-outcomes`)
- Test: `tests/outcomes/test_backfill.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/outcomes/test_backfill.py
from datetime import datetime, date, timedelta
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.backfill import resolve_pending
from finterminal.outcomes.schema import SignalType, MACRO_TICKER
from finterminal.market_data.store import upsert_prices_eod

def _seed(conn, tcs_then, tcs_thN, nifty_then, nifty_thN, ts_then, ts_thN):
    upsert_prices_eod(conn, [
        {"trade_date": ts_then,"ticker":"TCS","open":1,"high":1,"low":1,"close":tcs_then,"volume":0},
        {"trade_date": ts_thN,"ticker":"TCS","open":1,"high":1,"low":1,"close":tcs_thN,"volume":0},
        {"trade_date": ts_then,"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":nifty_then,"volume":0},
        {"trade_date": ts_thN,"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":nifty_thN,"volume":0},
    ], source="nse_bhavcopy")

def test_resolve_pending_computes_ret_and_alpha(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    ts_then, ts_thN = date(2026, 4, 22), date(2026, 4, 29)  # 7 days
    _seed(conn, tcs_then=100.0, tcs_thN=110.0,        # TCS +10%
                nifty_then=22000.0, nifty_thN=22220.0, # Nifty +1%
                ts_then=ts_then, ts_thN=ts_thN)
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 22, 10, 0),
    )
    n = resolve_pending(conn, today=date(2026, 5, 30))
    assert n >= 1
    row = conn.execute(
        "SELECT ret_pct, ret_pct_vs_nifty FROM signal_outcomes "
        "WHERE signal_id=? AND horizon_days=7", [sid]
    ).fetchone()
    assert row[0] == pytest.approx(0.10, rel=1e-9)
    assert row[1] == pytest.approx(0.10 - 0.01, rel=1e-9)

def test_resolve_pending_skips_when_prices_missing(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [
        {"trade_date": date(2026,4,22),"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":22000.0,"volume":0},
    ], source="nse_indices")
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 22, 10, 0),
    )
    resolve_pending(conn, today=date(2026, 5, 30))
    row = conn.execute(
        "SELECT ret_pct, resolved_at FROM signal_outcomes "
        "WHERE signal_id=? AND horizon_days=7", [sid]
    ).fetchone()
    assert row[0] is None and row[1] is None

def test_macro_ticker_resolves_against_nifty(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, tcs_then=100.0, tcs_thN=110.0, nifty_then=22000.0, nifty_thN=22220.0,
          ts_then=date(2026,4,22), ts_thN=date(2026,4,29))
    sid = emit_signal(conn,
        signal_type=SignalType.REGIME_SHIFT, ticker=MACRO_TICKER,
        ts_emitted=datetime(2026, 4, 22, 10, 0),
    )
    resolve_pending(conn, today=date(2026, 5, 30))
    row = conn.execute(
        "SELECT ret_pct, ret_pct_vs_nifty FROM signal_outcomes "
        "WHERE signal_id=? AND horizon_days=7", [sid]
    ).fetchone()
    assert row[0] == pytest.approx(0.01, rel=1e-9)         # nifty's own ret
    assert row[1] == pytest.approx(0.0, abs=1e-12)         # alpha is zero
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/outcomes/test_backfill.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/finterminal/outcomes/backfill.py
from __future__ import annotations
from datetime import date, datetime, timedelta
import duckdb

from finterminal.market_data.store import last_close_on_or_before
from .schema import MACRO_TICKER, NIFTY_TICKER

def resolve_pending(conn: duckdb.DuckDBPyConnection, *,
                    today: date | None = None) -> int:
    """Fill ret_pct + ret_pct_vs_nifty for every (signal, horizon) where
    today >= ts_emitted + horizon_days AND prices exist for both endpoints.
    Returns count of rows resolved."""
    today = today or date.today()
    pending = conn.execute(
        """
        SELECT s.signal_id, s.ticker, s.ts_emitted, o.horizon_days
        FROM signals s
        JOIN signal_outcomes o USING (signal_id)
        WHERE o.resolved_at IS NULL
          AND DATE(s.ts_emitted) + INTERVAL (o.horizon_days) DAY <= ?
        """,
        [today],
    ).fetchall()

    resolved = 0
    for signal_id, ticker, ts_emitted, horizon in pending:
        emit_date = ts_emitted.date() if isinstance(ts_emitted, datetime) else ts_emitted
        target_date = emit_date + timedelta(days=horizon)

        price_ticker = NIFTY_TICKER if ticker == MACRO_TICKER else ticker
        c_then = last_close_on_or_before(conn, price_ticker, emit_date)
        c_thN  = last_close_on_or_before(conn, price_ticker, target_date)
        n_then = last_close_on_or_before(conn, NIFTY_TICKER, emit_date)
        n_thN  = last_close_on_or_before(conn, NIFTY_TICKER, target_date)
        if None in (c_then, c_thN, n_then, n_thN) or c_then == 0 or n_then == 0:
            continue

        ret = (c_thN / c_then) - 1.0
        nifty_ret = (n_thN / n_then) - 1.0
        alpha = ret - nifty_ret

        conn.execute(
            "UPDATE signal_outcomes SET ret_pct=?, ret_pct_vs_nifty=?, resolved_at=? "
            "WHERE signal_id=? AND horizon_days=?",
            [ret, alpha, datetime.now(), signal_id, horizon],
        )
        resolved += 1
    return resolved
```

- [ ] **Step 4: Wire `/backfill-outcomes` REPL command**

In `src/finterminal/commands.py`:

```python
from finterminal.outcomes.backfill import resolve_pending

@command("/backfill-outcomes")
def cmd_backfill_outcomes(ctx, args: str = "") -> str:
    """Resolve forward returns for every signal whose horizon has matured."""
    n = resolve_pending(ctx.conn)
    return f"Resolved {n} signal/horizon pairs."
```

- [ ] **Step 5: Run — pass**

Run: `uv run pytest tests/outcomes/test_backfill.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/outcomes/backfill.py src/finterminal/commands.py tests/outcomes/test_backfill.py
git commit -m "feat(outcomes): resolve_pending + /backfill-outcomes command"
```

---

## Task 12: outcomes/queries.py + outcomes/engines/base.py

**Files:**
- Create: `src/finterminal/outcomes/queries.py`
- Create: `src/finterminal/outcomes/engines/__init__.py` (empty)
- Create: `src/finterminal/outcomes/engines/base.py`
- Test: `tests/outcomes/test_queries.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/outcomes/test_queries.py
from datetime import datetime, date
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.backfill import resolve_pending
from finterminal.outcomes.queries import predictive_power, engine_summary
from finterminal.outcomes.schema import SignalType, Engine
from finterminal.market_data.store import upsert_prices_eod

def _seed(conn, ret_tcs_pct, ret_nifty_pct):
    upsert_prices_eod(conn, [
        {"trade_date": date(2026,4,22),"ticker":"TCS","open":1,"high":1,"low":1,"close":100.0,"volume":0},
        {"trade_date": date(2026,4,29),"ticker":"TCS","open":1,"high":1,"low":1,"close":100.0*(1+ret_tcs_pct),"volume":0},
        {"trade_date": date(2026,4,22),"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":22000.0,"volume":0},
        {"trade_date": date(2026,4,29),"ticker":"_NIFTY50","open":1,"high":1,"low":1,"close":22000.0*(1+ret_nifty_pct),"volume":0},
    ], source="nse_bhavcopy")

def test_predictive_power_returns_shape(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, ret_tcs_pct=0.10, ret_nifty_pct=0.01)
    emit_signal(conn, signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
                ts_emitted=datetime(2026, 4, 22, 10, 0))
    resolve_pending(conn, today=date(2026, 5, 30))
    res = predictive_power(conn, signal_type=SignalType.CLUSTER_MOMENTUM, horizon=7)
    assert set(res.keys()) >= {"n", "mean_ret", "mean_alpha"}
    assert res["n"] == 1
    assert res["mean_ret"] == pytest.approx(0.10, rel=1e-9)
    assert res["mean_alpha"] == pytest.approx(0.09, rel=1e-9)

def test_engine_summary_aggregates(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, ret_tcs_pct=0.05, ret_nifty_pct=0.0)
    emit_signal(conn, signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
                ts_emitted=datetime(2026, 4, 22, 10, 0))
    resolve_pending(conn, today=date(2026, 5, 30))
    res = engine_summary(conn, engine=Engine.REFLEXIVITY, horizon=7)
    assert res["n"] >= 1
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/outcomes/test_queries.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement queries.py**

```python
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
```

- [ ] **Step 4: Implement engines/base.py**

```python
# src/finterminal/outcomes/engines/base.py
"""Engine class hook. Empty placeholder — per-engine modules
(mispricing.py, quality.py, ...) are added when ≥2 signal types per engine ship.
This file exists so the import path is stable from day 1."""
from __future__ import annotations

class EngineBase:
    """Marker base class. Concrete engines override `signals_for_card(ticker)` later."""
    name: str = ""
```

- [ ] **Step 5: Run — pass**

Run: `uv run pytest tests/outcomes/test_queries.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/outcomes/queries.py \
        src/finterminal/outcomes/engines/__init__.py \
        src/finterminal/outcomes/engines/base.py \
        tests/outcomes/test_queries.py
git commit -m "feat(outcomes): predictive_power + engine_summary + engines/base placeholder"
```

---

## Task 13: config flag + news/cluster.py wiring (fail-safe)

**Files:**
- Modify: `src/finterminal/config.py` (or wherever existing flags live)
- Modify: `src/finterminal/news/cluster.py`
- Modify: `src/finterminal/news/pipeline.py` (only if cluster_momentum is most natural to emit there — check first)
- Test: extend an existing news pipeline test, or add `tests/outcomes/test_wiring.py`

First read `src/finterminal/news/cluster.py` and `pipeline.py` to find the place where final clusters with `story_count_delta` are produced (probably `pipeline.py` after lineage matching). Wire there if so. The TDD-correct location is "after lineage produces (cluster, story_count_delta) pairs".

- [ ] **Step 1: Write failing test**

```python
# tests/outcomes/test_wiring.py
from datetime import datetime
from unittest.mock import patch
from finterminal.data.duckdb_store import connect

def test_cluster_pipeline_emits_signals_when_flag_on(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOMES_LEDGER_ENABLED", "1")
    conn = connect(str(tmp_path / "t.duckdb"))
    # Drive the news pipeline in test mode with one synthetic cluster carrying delta=+5.
    # Implementation: use the same fixture loader the existing news tests use; if absent,
    # call lineage.match() directly on a small in-memory pair and then invoke the wiring
    # function exposed in news/pipeline.py.
    from finterminal.news.pipeline import _emit_cluster_momentum_signals  # added in Step 3
    _emit_cluster_momentum_signals(conn, [
        {"cluster_id": "c1", "top_tickers": ["TCS"], "story_count": 7,
         "story_count_delta": 5, "first_seen": datetime(2026, 4, 29, 10, 0)},
    ])
    n = conn.execute("SELECT COUNT(*) FROM signals WHERE signal_type='cluster_momentum'").fetchone()[0]
    assert n == 1

def test_emit_signal_failure_does_not_break_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOMES_LEDGER_ENABLED", "1")
    conn = connect(str(tmp_path / "t.duckdb"))
    from finterminal.news.pipeline import _emit_cluster_momentum_signals
    with patch("finterminal.outcomes.ledger.emit_signal",
               side_effect=RuntimeError("boom")):
        _emit_cluster_momentum_signals(conn, [
            {"cluster_id": "c1", "top_tickers": ["TCS"], "story_count": 7,
             "story_count_delta": 5, "first_seen": datetime(2026, 4, 29, 10, 0)},
        ])  # MUST NOT raise

def test_flag_off_skips_emission(tmp_path, monkeypatch):
    monkeypatch.delenv("OUTCOMES_LEDGER_ENABLED", raising=False)
    conn = connect(str(tmp_path / "t.duckdb"))
    from finterminal.news.pipeline import _emit_cluster_momentum_signals
    _emit_cluster_momentum_signals(conn, [
        {"cluster_id": "c1", "top_tickers": ["TCS"], "story_count": 7,
         "story_count_delta": 5, "first_seen": datetime(2026, 4, 29, 10, 0)},
    ])
    n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    assert n == 0
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/outcomes/test_wiring.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the config flag**

In `src/finterminal/config.py` (or whichever module hosts the existing settings):

```python
import os
OUTCOMES_LEDGER_ENABLED: bool = os.getenv("OUTCOMES_LEDGER_ENABLED", "0") == "1"
```

If the project uses pydantic / dataclass config, add it to that class with default `False` and env-var override.

- [ ] **Step 4: Add the wiring function**

In `src/finterminal/news/pipeline.py`, append:

```python
import logging as _logging
from finterminal.config import OUTCOMES_LEDGER_ENABLED
from finterminal.outcomes import ledger as _ledger
from finterminal.outcomes.schema import SignalType, MACRO_TICKER

_log = _logging.getLogger(__name__)

def _emit_cluster_momentum_signals(conn, clusters: list[dict]) -> None:
    """Fail-safe: emit cluster_momentum signals after a /refresh-news run.
    Any exception in emission is swallowed so the news pipeline keeps working."""
    if not OUTCOMES_LEDGER_ENABLED:
        return
    for c in clusters:
        delta = c.get("story_count_delta", 0)
        if not delta:
            continue
        ticker = (c.get("top_tickers") or [None])[0] or MACRO_TICKER
        try:
            _ledger.emit_signal(
                conn,
                signal_type=SignalType.CLUSTER_MOMENTUM,
                ticker=ticker,
                ts_emitted=c["first_seen"],
                payload={"cluster_id": c["cluster_id"],
                         "story_count_delta": delta,
                         "story_count": c.get("story_count")},
                confidence=min(1.0, abs(delta) / 10.0),
                why=(f"cluster {c['cluster_id']} "
                     f"{'grew' if delta > 0 else 'shrank'} {abs(delta)} stories d/d"),
                source_ref=c["cluster_id"],
            )
        except Exception as e:
            _log.warning("emit_signal failed for cluster %s: %s",
                         c.get("cluster_id"), e)
```

- [ ] **Step 5: Wire it into the pipeline run**

Find the function in `pipeline.py` that currently returns the `PipelineResult` after lineage. At its tail, before returning, add:

```python
_emit_cluster_momentum_signals(conn, result_clusters_with_lineage)
```

Where `result_clusters_with_lineage` is the existing list of dicts/dataclasses that already contain `cluster_id`, `top_tickers`, `story_count`, `story_count_delta`, `first_seen`. If the existing types don't expose those fields verbatim, build the dict inline before the call — do not change the existing return shape.

- [ ] **Step 6: Run — pass**

Run: `uv run pytest tests/outcomes/test_wiring.py -v`
Expected: PASS.

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -x`
Expected: all green; no existing news test broken.

- [ ] **Step 8: Commit**

```bash
git add src/finterminal/config.py src/finterminal/news/pipeline.py tests/outcomes/test_wiring.py
git commit -m "feat(outcomes): wire cluster_momentum emission into /refresh-news (fail-safe)"
```

---

## Task 14: outcomes/backfill_historical.py — replay existing news_clusters

**Files:**
- Create: `src/finterminal/outcomes/backfill_historical.py`
- Test: `tests/outcomes/test_backfill_historical.py`

- [ ] **Step 1: Write failing test**

```python
# tests/outcomes/test_backfill_historical.py
from datetime import datetime, date, timedelta
from finterminal.data.duckdb_store import connect
from finterminal.outcomes.backfill_historical import backfill_from_news_clusters

def _insert_cluster(conn, cluster_id, first_seen, tickers, story_count):
    conn.execute(
        """INSERT INTO news_clusters (id, as_of, story_count, source_count,
           top_tickers, dominant_sector, representative_id, centroid, first_seen)
           VALUES (?, ?, ?, 1, ?, NULL, 'rep', NULL, ?)""",
        [cluster_id, first_seen.date(), story_count, tickers, first_seen],
    )

def test_old_clusters_are_replayed_recent_skipped(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _insert_cluster(conn, "old", datetime.now() - timedelta(days=30), ["TCS"], 5)
    _insert_cluster(conn, "new", datetime.now() - timedelta(days=2),  ["TCS"], 5)
    n = backfill_from_news_clusters(conn)
    assert n == 1  # only "old" was emitted
    rows = conn.execute(
        "SELECT source_ref FROM signals WHERE signal_type='cluster_momentum'"
    ).fetchall()
    assert {r[0] for r in rows} == {"old"}
```

- [ ] **Step 2: Run — fail**

Run: `uv run pytest tests/outcomes/test_backfill_historical.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/finterminal/outcomes/backfill_historical.py
from __future__ import annotations
from datetime import date, timedelta
import duckdb

from .ledger import emit_signal
from .schema import SignalType, MACRO_TICKER

_CUTOFF_DAYS = 7

def backfill_from_news_clusters(conn: duckdb.DuckDBPyConnection) -> int:
    """One-shot replay of `news_clusters` rows where first_seen <= today - 7d.
    For each, emits a cluster_momentum signal. Idempotent via signals UNIQUE constraint."""
    cutoff = date.today() - timedelta(days=_CUTOFF_DAYS)
    rows = conn.execute(
        """
        SELECT id, top_tickers, story_count, first_seen
        FROM news_clusters
        WHERE DATE(first_seen) <= ?
        """,
        [cutoff],
    ).fetchall()

    emitted = 0
    for cluster_id, top_tickers, story_count, first_seen in rows:
        ticker = (top_tickers[0] if top_tickers else MACRO_TICKER) or MACRO_TICKER
        # Historical clusters don't carry a delta — use story_count as a proxy
        # (won't compute alpha differently; just metadata). Confidence = story_count clamp.
        sid = emit_signal(
            conn,
            signal_type=SignalType.CLUSTER_MOMENTUM,
            ticker=ticker,
            ts_emitted=first_seen,
            payload={"cluster_id": cluster_id, "story_count": story_count,
                     "historical_replay": True},
            confidence=min(1.0, story_count / 10.0),
            why=f"historical replay of cluster {cluster_id}",
            source_ref=cluster_id,
        )
        if sid is not None:
            emitted += 1
    return emitted
```

- [ ] **Step 4: Run — pass**

Run: `uv run pytest tests/outcomes/test_backfill_historical.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/outcomes/backfill_historical.py tests/outcomes/test_backfill_historical.py
git commit -m "feat(outcomes): one-shot historical backfill from news_clusters (>=7d old)"
```

---

## Task 15: Pipeline-isolation guard + end-to-end integration test + acceptance verification

**Files:**
- Test: `tests/integration/test_foundation_e2e.py`
- Test: `tests/test_pipeline_isolation.py`

- [ ] **Step 1: Pipeline-isolation guard (encodes D9)**

```python
# tests/test_pipeline_isolation.py
import pathlib

ROOT = pathlib.Path(__file__).parents[1] / "src" / "finterminal" / "market_data"

def test_market_data_does_not_import_outcomes():
    offenders = []
    for p in ROOT.rglob("*.py"):
        text = p.read_text()
        if "from finterminal.outcomes" in text or "import finterminal.outcomes" in text:
            offenders.append(str(p))
    assert not offenders, f"market_data must not import outcomes: {offenders}"
```

Run: `uv run pytest tests/test_pipeline_isolation.py -v`
Expected: PASS.

- [ ] **Step 2: End-to-end integration test**

```python
# tests/integration/test_foundation_e2e.py
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.market_data.ingestion import refresh_prices
from finterminal.market_data._http import Http404
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.backfill import resolve_pending
from finterminal.outcomes.queries import predictive_power
from finterminal.outcomes.schema import SignalType

FIX = Path(__file__).parents[1] / "fixtures" / "market_data"

def _fixture_fetch(url: str) -> bytes:
    if "cm29APR2026" in url:
        return (FIX / "cm29APR2026bhav.csv.zip").read_bytes()
    if "29042026" in url:
        return (FIX / "ind_close_all_29042026.csv").read_bytes()
    raise Http404(url)

def test_full_pipeline_emit_then_resolve_then_query(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOMES_LEDGER_ENABLED", "1")
    conn = connect(str(tmp_path / "t.duckdb"))

    # 1. Pipeline A: ingest one day of fixture prices.
    with patch("finterminal.market_data.ingestion._http.fetch", side_effect=_fixture_fetch):
        refresh_prices(conn, start=date(2026, 4, 29), end=date(2026, 4, 29))

    # 2. Synthesize a t+7 row to make the 7d horizon resolvable.
    conn.execute(
        """INSERT INTO prices_eod (trade_date, ticker, close, source, created_at)
           VALUES (?, 'TCS', 3700.0, 'test', ?), (?, '_NIFTY50', 22600.0, 'test', ?)""",
        [date(2026, 5, 6), datetime.now(), date(2026, 5, 6), datetime.now()],
    )

    # 3. Pipeline B: emit a signal at t and resolve at t+30.
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0),
    )
    assert sid is not None
    n = resolve_pending(conn, today=date(2026, 5, 30))
    assert n >= 1

    # 4. Query.
    res = predictive_power(conn, signal_type=SignalType.CLUSTER_MOMENTUM, horizon=7)
    assert res["n"] >= 1
    assert res["mean_ret"] is not None
    assert res["mean_alpha"] is not None
```

- [ ] **Step 3: Run all new tests**

Run: `uv run pytest tests/integration/test_foundation_e2e.py tests/test_pipeline_isolation.py -v`
Expected: PASS.

- [ ] **Step 4: Run the entire suite**

Run: `uv run pytest`
Expected: all tests pass; existing 173 + new tests, no regressions.

- [ ] **Step 5: Verify acceptance criteria from the spec**

Manually walk through `docs/superpowers/specs/2026-04-29-foundation-outcomes-engines-design.md` § 10 and check each bullet against the test suite + commands. Capture results in commit message.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_foundation_e2e.py tests/test_pipeline_isolation.py
git commit -m "test: pipeline-isolation guard + foundation end-to-end integration"
```

---

## Self-Review (run after writing all tasks)

**1. Spec coverage** — every bullet in spec § 2 (In scope) maps to a task:

| Spec item | Task |
|---|---|
| Migration 004 | T1 |
| outcomes/schema.py + enums | T2 |
| `_http.py` + calendar.py | T3 |
| normalize.py | T4 |
| nse_bhavcopy.py | T5 |
| nse_indices.py | T6 |
| store.py + ingestion_log helpers | T7 |
| ingestion.py + /refresh-prices | T8 |
| macro.py | T9 |
| ledger.py / emit_signal | T10 |
| backfill.py + /backfill-outcomes | T11 |
| queries.py + engines/base.py | T12 |
| OUTCOMES_LEDGER_ENABLED + cluster wiring | T13 |
| backfill_historical.py | T14 |
| Pipeline isolation + E2E | T15 |

All 14 in-scope items covered. None of the four out-of-scope items (sentiment, mgmt_claims, /analyze reshape, INR/Brent/10y) appear in any task — correct.

**2. Placeholder scan** — no "TBD", "TODO", "fill in details", "similar to task N" left. Each step contains the actual code or exact command.

**3. Type consistency**
- `Engine`, `SignalType` enums defined in T2; same names used in T10, T11, T12, T13, T14. ✓
- `MACRO_TICKER`, `NIFTY_TICKER` defined in T2; used in T11, T13, T14. ✓
- `emit_signal` signature defined in T10; called with same kwargs in T13, T14, T15. ✓
- `last_close_on_or_before(conn, ticker, date)` defined in T7; called with same shape in T9, T11. ✓
- `refresh_prices(conn, *, start, end)` defined in T8; called with same kwargs in T15. ✓
- `resolve_pending(conn, *, today=None)` defined in T11; called with same kwargs in T12, T15. ✓
- `predictive_power(conn, *, signal_type, horizon)` defined in T12; called with same kwargs in T15. ✓
- `Http404`, `Http429` defined in T3; referenced in T8. ✓

No type drift detected.
