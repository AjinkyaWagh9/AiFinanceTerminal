# Quality Engine v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the four `#3` quality features (roe, leverage, earnings_growth, quality_score) into the feature vector and introduce the mgmt_claims ledger table.

**Architecture:** `compute_quality.py` mirrors the pattern of `compute_price.py` — each function takes `(conn, *, ticker, ts_emitted, **_)` and returns `(value | None, is_missing: bool)`. `quality_score` additionally takes the three pre-computed fundamental values and applies cross-sectional z-scoring across all tickers in the `fundamentals` table. The four `#3` FeatureSpecs in `registry.py` are promoted from `compute=None` to their real compute names, which removes them from `PLACEHOLDER_NAMES` and requires a new quality block in `orchestrator.py`. The `mgmt_claims` table (migration 006) is a standalone ledger with no NLP extractor in v1.

**Tech Stack:** Python 3.13, DuckDB, uv/pytest. No new dependencies.

---

## Baseline

Before touching any code, run:

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal
uv run pytest -q --tb=no
# expect: 266 passed
```

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/finterminal/data/migrations/006_mgmt_claims.sql` | mgmt_claims DDL |
| Modify | `src/finterminal/features/registry.py` | Add `MAX_FUNDAMENTALS_STALENESS_DAYS`; promote 4 FeatureSpecs |
| Modify | `src/finterminal/features/freshness.py` | Add `last_fundamentals_date`, `is_fundamentals_data_fresh` |
| Create | `src/finterminal/features/compute_quality.py` | `compute_roe`, `compute_leverage`, `compute_earnings_growth`, `compute_quality_score` |
| Modify | `src/finterminal/features/orchestrator.py` | Import `compute_quality`; add quality block |
| Modify | `src/finterminal/data/duckdb_store.py` | Add `insert_mgmt_claim`, `list_mgmt_claims` |
| Create | `tests/features/test_compute_quality.py` | Unit tests for all 4 compute functions |
| Modify | `tests/features/test_freshness.py` | Tests for `is_fundamentals_data_fresh` |
| Create | `tests/test_mgmt_claims.py` | CRUD tests for mgmt_claims |
| Modify | `tests/features/test_atomicity.py` | Update stale placeholder-count comment |

---

## Task 1: Migration 006 — mgmt_claims table

**Files:**
- Create: `src/finterminal/data/migrations/006_mgmt_claims.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Sub-project #3: management claims ledger.
-- Records discrete claims made by management in earnings calls / press releases / news.
-- outcome_verified is populated when claim horizon passes (sub-project #6 fills this).
-- Leakage rule: any feature derived from this table must use an as_of cutoff and
-- exclude claims that resolved after as_of - horizon_days.
CREATE TABLE IF NOT EXISTS mgmt_claims (
    claim_id         VARCHAR PRIMARY KEY,
    ticker           VARCHAR NOT NULL,
    claimed_at       TIMESTAMP NOT NULL,
    claim_text       VARCHAR NOT NULL,
    horizon_days     INTEGER NOT NULL,
    outcome_date     DATE,
    outcome_verified BOOLEAN,
    source_ref       VARCHAR
);

CREATE INDEX IF NOT EXISTS mgmt_claims_ticker_idx       ON mgmt_claims(ticker);
CREATE INDEX IF NOT EXISTS mgmt_claims_outcome_date_idx ON mgmt_claims(outcome_date);
```

- [ ] **Step 2: Verify migration applies cleanly**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal
uv run python -c "
from finterminal.data.duckdb_store import connect
conn = connect('/tmp/test_006.duckdb')
tables = conn.execute(\"SELECT table_name FROM information_schema.tables WHERE table_name = 'mgmt_claims'\").fetchall()
print('mgmt_claims exists:', bool(tables))
"
```
Expected output: `mgmt_claims exists: True`

- [ ] **Step 3: Verify full suite still green**

```bash
uv run pytest -q --tb=short
```
Expected: 266 passed (no new tests yet, nothing broken)

- [ ] **Step 4: Commit**

```bash
git add src/finterminal/data/migrations/006_mgmt_claims.sql
git commit -m "feat(#3): migration 006 — mgmt_claims ledger table"
```

---

## Task 2: Registry constant + freshness gate for fundamentals

**Files:**
- Modify: `src/finterminal/features/registry.py:12-22`
- Modify: `src/finterminal/features/freshness.py`
- Modify: `tests/features/test_freshness.py`

- [ ] **Step 1: Write failing freshness tests**

Append to `tests/features/test_freshness.py`:

```python
from finterminal.data.duckdb_store import upsert_fundamentals
from finterminal.features.freshness import (
    last_fundamentals_date, is_fundamentals_data_fresh,
)

def _seed_fundamentals(conn, ticker: str, as_of: date, roe: float = 0.15):
    upsert_fundamentals(conn, {
        "ticker": ticker, "as_of": as_of,
        "roe": roe, "debt_to_equity": 1.0,
        "net_income_ttm": 1000.0,
    })

def test_last_fundamentals_date_returns_none_when_no_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert last_fundamentals_date(conn, "TCS", as_of=date(2026, 4, 30)) is None

def test_last_fundamentals_date_ignores_future_rows(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_fundamentals(conn, "TCS", date(2026, 1, 1))
    _seed_fundamentals(conn, "TCS", date(2026, 7, 1))  # future relative to as_of
    assert last_fundamentals_date(conn, "TCS", as_of=date(2026, 4, 30)) == date(2026, 1, 1)

def test_is_fundamentals_data_fresh_within_threshold(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_fundamentals(conn, "TCS", date(2026, 2, 1))  # 88 days before ts_emitted
    assert is_fundamentals_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is True

def test_is_fundamentals_data_fresh_stale(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_fundamentals(conn, "TCS", date(2025, 12, 1))  # > 120 days before ts_emitted
    assert is_fundamentals_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is False

def test_is_fundamentals_data_fresh_no_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert is_fundamentals_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/features/test_freshness.py -k "fundamentals" -v
```
Expected: 5 errors — `ImportError: cannot import name 'last_fundamentals_date'`

- [ ] **Step 3: Add the constant to registry.py**

In `src/finterminal/features/registry.py`, after line 19 (after `MAX_NIFTY_STALENESS_DAYS = 5`), add:

```python
MAX_FUNDAMENTALS_STALENESS_DAYS = 120   # one quarter
```

- [ ] **Step 4: Add freshness helpers to freshness.py**

In `src/finterminal/features/freshness.py`, append after the last function:

```python
from .registry import MAX_FUNDAMENTALS_STALENESS_DAYS

def last_fundamentals_date(conn: duckdb.DuckDBPyConnection,
                           ticker: str, *, as_of: date) -> date | None:
    """Most recent fundamentals as_of for `ticker` with as_of <= as_of, or None."""
    row = conn.execute(
        "SELECT MAX(as_of) FROM fundamentals "
        "WHERE ticker = ? AND as_of <= ?",
        [ticker, as_of],
    ).fetchone()
    return row[0] if row and row[0] is not None else None

def is_fundamentals_data_fresh(conn: duckdb.DuckDBPyConnection,
                               ticker: str, *, ts_emitted: datetime) -> bool:
    last = last_fundamentals_date(conn, ticker, as_of=ts_emitted.date())
    if last is None:
        return False
    return (ts_emitted.date() - last) <= timedelta(days=MAX_FUNDAMENTALS_STALENESS_DAYS)
```

Note: `timedelta` is already imported in `freshness.py`.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/features/test_freshness.py -v
```
Expected: 11 passed (6 original + 5 new)

- [ ] **Step 6: Commit**

> **Note:** FeatureSpec promotion is intentionally deferred to Task 5 so it lands atomically with the orchestrator quality block. Promoting FeatureSpecs first would shrink `PLACEHOLDER_NAMES`, then the orchestrator's completeness check (`if set(out.keys()) != expected: raise RuntimeError`) would fire on every `emit_signal` call.

```bash
git add src/finterminal/features/registry.py src/finterminal/features/freshness.py tests/features/test_freshness.py
git commit -m "feat(#3): MAX_FUNDAMENTALS_STALENESS_DAYS constant + is_fundamentals_data_fresh gate"
```

---

## Task 3: compute_quality.py — roe, leverage, earnings_growth

**Files:**
- Create: `src/finterminal/features/compute_quality.py`
- Create: `tests/features/test_compute_quality.py`

- [ ] **Step 1: Write failing tests for roe, leverage, earnings_growth**

Create `tests/features/test_compute_quality.py`:

```python
from datetime import date, datetime
import pytest
from finterminal.data.duckdb_store import connect, upsert_fundamentals
from finterminal.features.compute_quality import (
    compute_roe, compute_leverage, compute_earnings_growth,
)

def _seed(conn, ticker, as_of, roe=0.18, d2e=0.5, ni=1000.0):
    upsert_fundamentals(conn, {
        "ticker": ticker, "as_of": as_of,
        "roe": roe, "debt_to_equity": d2e, "net_income_ttm": ni,
    })

TS = datetime(2026, 4, 30, 10, 0)

# ---------- roe ----------

def test_compute_roe_returns_value(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 1, 1), roe=0.18)
    v, m = compute_roe(conn, ticker="TCS", ts_emitted=TS)
    assert m is False
    assert abs(v - 0.18) < 1e-9

def test_compute_roe_missing_when_no_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    v, m = compute_roe(conn, ticker="TCS", ts_emitted=TS)
    assert v is None and m is True

def test_compute_roe_missing_when_stale(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2025, 12, 1), roe=0.18)   # > 120 days stale
    v, m = compute_roe(conn, ticker="TCS", ts_emitted=TS)
    assert v is None and m is True

def test_compute_roe_uses_latest_row(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 1, 1), roe=0.10)
    _seed(conn, "TCS", date(2026, 3, 1), roe=0.20)
    v, m = compute_roe(conn, ticker="TCS", ts_emitted=TS)
    assert m is False and abs(v - 0.20) < 1e-9

# ---------- leverage ----------

def test_compute_leverage_returns_value(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 1, 1), d2e=1.5)
    v, m = compute_leverage(conn, ticker="TCS", ts_emitted=TS)
    assert m is False and abs(v - 1.5) < 1e-9

def test_compute_leverage_missing_when_no_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    v, m = compute_leverage(conn, ticker="TCS", ts_emitted=TS)
    assert v is None and m is True

# ---------- earnings_growth ----------

def test_compute_earnings_growth_yoy(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 1, 1), ni=1200.0)   # latest
    _seed(conn, "TCS", date(2025, 10, 1), ni=1000.0)  # prior
    v, m = compute_earnings_growth(conn, ticker="TCS", ts_emitted=TS)
    assert m is False
    assert abs(v - 0.20) < 1e-9   # (1200 - 1000) / 1000 = 0.20

def test_compute_earnings_growth_missing_when_only_one_row(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 1, 1), ni=1000.0)
    v, m = compute_earnings_growth(conn, ticker="TCS", ts_emitted=TS)
    assert v is None and m is True

def test_compute_earnings_growth_missing_when_prior_is_zero(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 1, 1), ni=500.0)
    _seed(conn, "TCS", date(2025, 10, 1), ni=0.0)
    v, m = compute_earnings_growth(conn, ticker="TCS", ts_emitted=TS)
    assert v is None and m is True

def test_compute_earnings_growth_negative_growth(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 1, 1), ni=800.0)
    _seed(conn, "TCS", date(2025, 10, 1), ni=1000.0)
    v, m = compute_earnings_growth(conn, ticker="TCS", ts_emitted=TS)
    assert m is False
    assert abs(v - (-0.20)) < 1e-9
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/features/test_compute_quality.py -v 2>&1 | head -20
```
Expected: `ImportError: No module named 'finterminal.features.compute_quality'`

- [ ] **Step 3: Create compute_quality.py with roe, leverage, earnings_growth**

Create `src/finterminal/features/compute_quality.py`:

```python
from __future__ import annotations
from datetime import datetime
import duckdb

from .freshness import is_fundamentals_data_fresh

Result = tuple[float | None, bool]   # (value, is_missing)

MIN_CROSS_SECTION_COUNT = 3   # minimum tickers needed for quality_score z-scoring


def compute_roe(conn: duckdb.DuckDBPyConnection, *,
                ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_fundamentals_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    row = conn.execute(
        "SELECT roe FROM fundamentals "
        "WHERE ticker = ? AND as_of <= ? ORDER BY as_of DESC LIMIT 1",
        [ticker, ts_emitted.date()],
    ).fetchone()
    if row is None or row[0] is None:
        return None, True
    return row[0], False


def compute_leverage(conn: duckdb.DuckDBPyConnection, *,
                     ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_fundamentals_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    row = conn.execute(
        "SELECT debt_to_equity FROM fundamentals "
        "WHERE ticker = ? AND as_of <= ? ORDER BY as_of DESC LIMIT 1",
        [ticker, ts_emitted.date()],
    ).fetchone()
    if row is None or row[0] is None:
        return None, True
    return row[0], False


def compute_earnings_growth(conn: duckdb.DuckDBPyConnection, *,
                            ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_fundamentals_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    rows = conn.execute(
        "SELECT as_of, net_income_ttm FROM fundamentals "
        "WHERE ticker = ? AND as_of <= ? ORDER BY as_of DESC LIMIT 2",
        [ticker, ts_emitted.date()],
    ).fetchall()
    if len(rows) < 2:
        return None, True
    curr, prev = rows[0][1], rows[1][1]
    if curr is None or prev is None or prev == 0:
        return None, True
    return (curr - prev) / abs(prev), False
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/features/test_compute_quality.py -v
```
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/compute_quality.py tests/features/test_compute_quality.py
git commit -m "feat(#3): compute_roe, compute_leverage, compute_earnings_growth"
```

---

## Task 4: compute_quality_score — cross-sectional z-score

**Files:**
- Modify: `src/finterminal/features/compute_quality.py` (append `_zscore` + `compute_quality_score`)
- Modify: `tests/features/test_compute_quality.py` (append quality_score tests)

- [ ] **Step 1: Write failing tests for compute_quality_score**

Append to `tests/features/test_compute_quality.py`:

```python
from finterminal.features.compute_quality import compute_quality_score

def _seed_multi(conn, tickers_data):
    """tickers_data: list of (ticker, as_of, roe, d2e, ni_curr, ni_prev)"""
    for ticker, as_of_curr, as_of_prev, roe, d2e, ni_curr, ni_prev in tickers_data:
        _seed(conn, ticker, as_of_curr, roe=roe, d2e=d2e, ni=ni_curr)
        _seed(conn, ticker, as_of_prev, ni=ni_prev)

def test_compute_quality_score_missing_when_any_input_is_none(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    v, m = compute_quality_score(conn, ticker="TCS", ts_emitted=TS,
                                  roe_value=None, leverage_value=0.5,
                                  earnings_growth_value=0.1)
    assert v is None and m is True

def test_compute_quality_score_missing_when_fewer_than_3_tickers(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    # Only 2 tickers — below MIN_CROSS_SECTION_COUNT
    _seed(conn, "TCS", date(2026, 1, 1), roe=0.2, d2e=0.3)
    _seed(conn, "INFY", date(2026, 1, 1), roe=0.15, d2e=0.5)
    v, m = compute_quality_score(conn, ticker="TCS", ts_emitted=TS,
                                  roe_value=0.2, leverage_value=0.3,
                                  earnings_growth_value=0.1)
    assert v is None and m is True

def test_compute_quality_score_returns_float_with_3_tickers(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS",  date(2026, 1, 1), roe=0.20, d2e=0.3)
    _seed(conn, "INFY", date(2026, 1, 1), roe=0.15, d2e=0.5)
    _seed(conn, "WIPRO", date(2026, 1, 1), roe=0.10, d2e=0.8)
    v, m = compute_quality_score(conn, ticker="TCS", ts_emitted=TS,
                                  roe_value=0.20, leverage_value=0.3,
                                  earnings_growth_value=0.10)
    assert m is False
    assert isinstance(v, float)

def test_compute_quality_score_best_company_positive(tmp_path):
    """Highest roe, lowest leverage → quality_score should be > 0."""
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "BEST",  date(2026, 1, 1), roe=0.30, d2e=0.1)
    _seed(conn, "MID",   date(2026, 1, 1), roe=0.15, d2e=0.5)
    _seed(conn, "WORST", date(2026, 1, 1), roe=0.05, d2e=1.5)
    v, m = compute_quality_score(conn, ticker="BEST", ts_emitted=TS,
                                  roe_value=0.30, leverage_value=0.1,
                                  earnings_growth_value=0.20)
    assert m is False and v > 0

def test_compute_quality_score_worst_company_negative(tmp_path):
    """Lowest roe, highest leverage → quality_score should be < 0."""
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "BEST",  date(2026, 1, 1), roe=0.30, d2e=0.1)
    _seed(conn, "MID",   date(2026, 1, 1), roe=0.15, d2e=0.5)
    _seed(conn, "WORST", date(2026, 1, 1), roe=0.05, d2e=1.5)
    v, m = compute_quality_score(conn, ticker="WORST", ts_emitted=TS,
                                  roe_value=0.05, leverage_value=1.5,
                                  earnings_growth_value=-0.10)
    assert m is False and v < 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/features/test_compute_quality.py -k "quality_score" -v 2>&1 | head -10
```
Expected: `ImportError: cannot import name 'compute_quality_score'`

- [ ] **Step 3: Implement compute_quality_score in compute_quality.py**

Append to `src/finterminal/features/compute_quality.py`:

```python
def _zscore(value: float, mean: float | None, std: float | None) -> float:
    """Z-score a value; returns 0.0 if std is None or zero (can't discriminate)."""
    if mean is None or std is None or std == 0:
        return 0.0
    return (value - mean) / std


def compute_quality_score(
    conn: duckdb.DuckDBPyConnection, *,
    ticker: str,
    ts_emitted: datetime,
    roe_value: float | None,
    leverage_value: float | None,
    earnings_growth_value: float | None,
    **_,
) -> Result:
    """Cross-sectional equal-weighted z-score of (roe, -leverage, earnings_growth).
    
    Requires all three input values non-None and >= MIN_CROSS_SECTION_COUNT tickers
    with roe + debt_to_equity data in fundamentals as_of ts_emitted.
    """
    if roe_value is None or leverage_value is None or earnings_growth_value is None:
        return None, True

    as_of = ts_emitted.date()

    # Cross-sectional stats for roe and leverage (latest row per ticker)
    cs_row = conn.execute(
        """
        WITH latest AS (
            SELECT ticker, MAX(as_of) AS latest_as_of
            FROM fundamentals
            WHERE as_of <= ?
            GROUP BY ticker
        )
        SELECT
            AVG(f.roe),              STDDEV_SAMP(f.roe),
            AVG(f.debt_to_equity),   STDDEV_SAMP(f.debt_to_equity),
            COUNT(*)
        FROM latest l
        JOIN fundamentals f ON f.ticker = l.ticker AND f.as_of = l.latest_as_of
        WHERE f.roe IS NOT NULL AND f.debt_to_equity IS NOT NULL
        """,
        [as_of],
    ).fetchone()

    if cs_row is None or cs_row[4] is None or cs_row[4] < MIN_CROSS_SECTION_COUNT:
        return None, True

    mean_roe, std_roe, mean_lev, std_lev, _ = cs_row

    # Cross-sectional earnings growth stats (requires 2 rows per ticker)
    eg_row = conn.execute(
        """
        WITH ranked AS (
            SELECT ticker, as_of, net_income_ttm,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY as_of DESC) AS rn
            FROM fundamentals
            WHERE as_of <= ?
        ),
        growth AS (
            SELECT (c.net_income_ttm - p.net_income_ttm)
                       / NULLIF(ABS(p.net_income_ttm), 0) AS eg
            FROM ranked c
            JOIN ranked p ON c.ticker = p.ticker AND p.rn = 2
            WHERE c.rn = 1
              AND c.net_income_ttm IS NOT NULL
              AND p.net_income_ttm IS NOT NULL
        )
        SELECT AVG(eg), STDDEV_SAMP(eg)
        FROM growth
        """,
        [as_of],
    ).fetchone()

    mean_eg = eg_row[0] if eg_row else None
    std_eg  = eg_row[1] if eg_row else None

    z_roe = _zscore(roe_value, mean_roe, std_roe)
    z_lev = -_zscore(leverage_value, mean_lev, std_lev)   # lower leverage → better
    z_eg  = _zscore(earnings_growth_value, mean_eg, std_eg)

    return (z_roe + z_lev + z_eg) / 3.0, False
```

- [ ] **Step 4: Run all compute_quality tests**

```bash
uv run pytest tests/features/test_compute_quality.py -v
```
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/compute_quality.py tests/features/test_compute_quality.py
git commit -m "feat(#3): compute_quality_score — cross-sectional equal-weight z-score"
```

---

## Task 5: Orchestrator wiring + FeatureSpec promotion (atomic)

**Files:**
- Modify: `src/finterminal/features/registry.py` (promote 4 FeatureSpecs)
- Modify: `src/finterminal/features/orchestrator.py` (imports + quality block)
- Modify: `tests/features/test_atomicity.py` (comment update only)

> **Why atomic:** registry promotion + orchestrator quality block must land in the same commit. If registry is promoted first, `PLACEHOLDER_NAMES` shrinks and the orchestrator can't fill all 18 features → completeness check fails. If orchestrator quality block is added first without promotion, the placeholder loop runs over the old 7-entry `PLACEHOLDER_NAMES` and overwrites the quality block's values with `is_missing=True`.

- [ ] **Step 1: Write a failing orchestrator test for quality block**

Append to `tests/features/test_orchestrator.py` (read the file first to check for existing tests, then append):

```python
from finterminal.data.duckdb_store import connect, upsert_fundamentals
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.orchestrator import compute_for_signal
from finterminal.outcomes.schema import SignalType
from datetime import datetime, date

def test_quality_features_present_in_output(tmp_path):
    """All four quality features must be in the output dict, even if is_missing."""
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [{
        "trade_date": date(2026, 4, 28), "ticker": "_NIFTY50",
        "open": 22000, "high": 22000, "low": 22000, "close": 22000.0, "volume": 0,
    }], source="nse_indices")
    out = compute_for_signal(
        conn, signal_id="test-q", signal_type=SignalType.CLUSTER_MOMENTUM,
        ticker="TCS", ts_emitted=datetime(2026, 4, 29, 10, 0),
        payload={"cluster_id": "c1"},
    )
    for name in ("roe", "leverage", "earnings_growth", "quality_score"):
        assert name in out, f"{name} missing from orchestrator output"
        assert "value" in out[name] and "is_missing" in out[name]

def test_quality_features_computed_when_fundamentals_seeded(tmp_path):
    """With 3+ tickers fundamentals seeded, quality features should not be missing."""
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_prices_eod(conn, [{
        "trade_date": date(2026, 4, 28), "ticker": "_NIFTY50",
        "open": 22000, "high": 22000, "low": 22000, "close": 22000.0, "volume": 0,
    }], source="nse_indices")
    as_of = date(2026, 1, 1)
    as_of_prev = date(2025, 10, 1)
    for ticker, roe, d2e, ni_curr, ni_prev in [
        ("TCS",   0.20, 0.3, 1200.0, 1000.0),
        ("INFY",  0.15, 0.5, 900.0,  800.0),
        ("WIPRO", 0.10, 0.8, 500.0,  450.0),
    ]:
        upsert_fundamentals(conn, {"ticker": ticker, "as_of": as_of,
                                   "roe": roe, "debt_to_equity": d2e,
                                   "net_income_ttm": ni_curr})
        upsert_fundamentals(conn, {"ticker": ticker, "as_of": as_of_prev,
                                   "net_income_ttm": ni_prev})
    out = compute_for_signal(
        conn, signal_id="test-q2", signal_type=SignalType.CLUSTER_MOMENTUM,
        ticker="TCS", ts_emitted=datetime(2026, 4, 29, 10, 0),
        payload={"cluster_id": "c1"},
    )
    assert out["roe"]["is_missing"]            is False
    assert out["leverage"]["is_missing"]       is False
    assert out["earnings_growth"]["is_missing"] is False
    assert out["quality_score"]["is_missing"]   is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/features/test_orchestrator.py -k "quality" -v
```
Expected: 2 FAILED — quality features still come back as is_missing=True (they're still on the PLACEHOLDER path)

- [ ] **Step 3a: Update registry.py FeatureSpecs**

In `src/finterminal/features/registry.py`, replace lines 39–42:

```python
    # Quality placeholders (#3 fills these)
    FeatureSpec("roe",                     None, "fundamentals (#3)"),
    FeatureSpec("leverage",                None, "fundamentals (#3)"),
    FeatureSpec("earnings_growth",         None, "fundamentals (#3)"),
    FeatureSpec("quality_score",           None, "derived (#3)"),
```

with:

```python
    # Quality (#3)
    FeatureSpec("roe",             "roe",              "fundamentals"),
    FeatureSpec("leverage",        "leverage",          "fundamentals"),
    FeatureSpec("earnings_growth", "earnings_growth",   "fundamentals"),
    FeatureSpec("quality_score",   "quality_score",     "derived"),
```

- [ ] **Step 3b: Update orchestrator.py**

In `src/finterminal/features/orchestrator.py`, make two edits:

**Edit A** — change the imports line (line 8):
```python
from . import compute_price, compute_regime, compute_news, compute_quality
```

**Edit B** — Replace the entire `# Placeholders` block (lines 54–56):
```python
    # Quality block (#3)
    roe_v, roe_m = compute_quality.compute_roe(conn, **ctx)
    out["roe"] = {"value": roe_v, "is_missing": roe_m}
    lev_v, lev_m = compute_quality.compute_leverage(conn, **ctx)
    out["leverage"] = {"value": lev_v, "is_missing": lev_m}
    eg_v, eg_m = compute_quality.compute_earnings_growth(conn, **ctx)
    out["earnings_growth"] = {"value": eg_v, "is_missing": eg_m}
    qs_v, qs_m = compute_quality.compute_quality_score(
        conn, roe_value=roe_v, leverage_value=lev_v,
        earnings_growth_value=eg_v, **ctx)
    out["quality_score"] = {"value": qs_v, "is_missing": qs_m}

    # Placeholders (reflexivity — #4 fills these)
    for name in PLACEHOLDER_NAMES:
        out[name] = {"value": None, "is_missing": True}
```

- [ ] **Step 4: Run orchestrator tests**

```bash
uv run pytest tests/features/test_orchestrator.py -v
```
Expected: all pass including the 2 new quality tests

- [ ] **Step 5: Update comment in test_atomicity.py**

In `tests/features/test_atomicity.py`, change line 27's comment from:
```python
    assert n == 18   # 11 computable (most missing due to thin seed) + 7 placeholders
```
to:
```python
    assert n == 18   # 15 computable (most missing due to thin seed) + 3 reflexivity placeholders
```

- [ ] **Step 6: Run atomicity tests**

```bash
uv run pytest tests/features/test_atomicity.py -v
```
Expected: 4 passed

- [ ] **Step 7: Run pipeline isolation guard**

```bash
uv run pytest tests/test_pipeline_isolation.py -v
```
Expected: all pass (compute_quality.py only imports from `features/` — no D9 violation)

- [ ] **Step 8: Commit**

```bash
git add src/finterminal/features/registry.py src/finterminal/features/orchestrator.py tests/features/test_orchestrator.py tests/features/test_atomicity.py
git commit -m "feat(#3): promote quality FeatureSpecs + wire orchestrator quality block"
```

---

## Task 6: mgmt_claims CRUD helpers

**Files:**
- Modify: `src/finterminal/data/duckdb_store.py` (append at bottom)
- Create: `tests/test_mgmt_claims.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_mgmt_claims.py`:

```python
from datetime import datetime
import pytest
from finterminal.data.duckdb_store import connect, insert_mgmt_claim, list_mgmt_claims

TS = datetime(2026, 4, 29, 9, 0)

def test_insert_mgmt_claim_returns_uuid(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    claim_id = insert_mgmt_claim(conn, {
        "ticker": "TCS",
        "claimed_at": TS,
        "claim_text": "We will double revenue in 2 years.",
        "horizon_days": 730,
        "source_ref": "Q4-2026-earnings-call",
    })
    assert isinstance(claim_id, str) and len(claim_id) == 36   # UUID4

def test_list_mgmt_claims_returns_inserted(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    insert_mgmt_claim(conn, {
        "ticker": "TCS", "claimed_at": TS,
        "claim_text": "Double revenue in 2 years.", "horizon_days": 730,
    })
    rows = list_mgmt_claims(conn, "TCS")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "TCS"
    assert rows[0]["claim_text"] == "Double revenue in 2 years."
    assert rows[0]["outcome_verified"] is None

def test_list_mgmt_claims_filters_by_ticker(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    insert_mgmt_claim(conn, {"ticker": "TCS",  "claimed_at": TS,
                              "claim_text": "TCS claim", "horizon_days": 365})
    insert_mgmt_claim(conn, {"ticker": "INFY", "claimed_at": TS,
                              "claim_text": "INFY claim", "horizon_days": 180})
    tcs_rows  = list_mgmt_claims(conn, "TCS")
    infy_rows = list_mgmt_claims(conn, "INFY")
    assert len(tcs_rows) == 1 and tcs_rows[0]["ticker"] == "TCS"
    assert len(infy_rows) == 1 and infy_rows[0]["ticker"] == "INFY"

def test_list_mgmt_claims_empty_when_none(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert list_mgmt_claims(conn, "TCS") == []

def test_insert_mgmt_claim_with_outcome(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    from datetime import date
    claim_id = insert_mgmt_claim(conn, {
        "ticker": "TCS", "claimed_at": TS,
        "claim_text": "Margin will expand 200bps.", "horizon_days": 365,
        "outcome_date": date(2027, 4, 29), "outcome_verified": True,
        "source_ref": "Annual-Report-2027",
    })
    rows = list_mgmt_claims(conn, "TCS")
    assert rows[0]["outcome_verified"] is True
    assert rows[0]["source_ref"] == "Annual-Report-2027"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_mgmt_claims.py -v 2>&1 | head -10
```
Expected: `ImportError: cannot import name 'insert_mgmt_claim'`

- [ ] **Step 3: Add CRUD helpers to duckdb_store.py**

Append to `src/finterminal/data/duckdb_store.py` (after the last function):

```python
# ---------- mgmt_claims ----------

def insert_mgmt_claim(conn: duckdb.DuckDBPyConnection, c: dict) -> str:
    """Insert a management claim record. Returns the new claim_id (uuid4)."""
    claim_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mgmt_claims
            (claim_id, ticker, claimed_at, claim_text, horizon_days,
             outcome_date, outcome_verified, source_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            claim_id,
            c["ticker"],
            c["claimed_at"],
            c["claim_text"],
            c["horizon_days"],
            c.get("outcome_date"),
            c.get("outcome_verified"),
            c.get("source_ref"),
        ],
    )
    return claim_id


def list_mgmt_claims(conn: duckdb.DuckDBPyConnection, ticker: str) -> list[dict]:
    """Return all claims for `ticker`, most recent first."""
    rows = conn.execute(
        "SELECT claim_id, ticker, claimed_at, claim_text, horizon_days, "
        "       outcome_date, outcome_verified, source_ref "
        "FROM mgmt_claims WHERE ticker = ? ORDER BY claimed_at DESC",
        [ticker],
    ).fetchall()
    cols = ["claim_id", "ticker", "claimed_at", "claim_text", "horizon_days",
            "outcome_date", "outcome_verified", "source_ref"]
    return [dict(zip(cols, r)) for r in rows]
```

- [ ] **Step 4: Run mgmt_claims tests**

```bash
uv run pytest tests/test_mgmt_claims.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/data/duckdb_store.py tests/test_mgmt_claims.py
git commit -m "feat(#3): insert_mgmt_claim + list_mgmt_claims CRUD helpers"
```

---

## Task 7: Full smoke test

**Files:** None (validation only)

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal
uv run pytest -q --tb=short
```
Expected: ≥ 290 passed, 0 failed.

Target breakdown:
- 266 original tests
- +5 freshness tests (fundamentals)
- +16 compute_quality tests
- +2 orchestrator quality tests
- +5 mgmt_claims tests
= 294 tests minimum

- [ ] **Step 2: If any test fails, diagnose before moving on**

Common failures and fixes:
- `ImportError` in `orchestrator.py` → check `from . import compute_quality` is present
- `KeyError` in orchestrator completeness check → verify the 4 quality feature names match exactly between `registry.py` and the quality block
- `PLACEHOLDER_NAMES` still contains quality feature names → re-check registry.py FeatureSpec changes (Task 2 Step 6)

- [ ] **Step 3: Spawn TerminalVault update**

After confirming green, spawn a Haiku sub-agent to update the vault:

```
Agent(
  description="Update TerminalVault — Quality Engine v1 complete",
  subagent_type="general-purpose",
  model="haiku",
  prompt="""
    Update the Obsidian vault at /Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault.

    Context — what just changed:
      Sub-project #3 (Quality Engine v1) is complete. Four quality features
      (roe, leverage, earnings_growth, quality_score) are wired into the feature
      vector via compute_quality.py. migration 006 adds the mgmt_claims ledger table.
      All 294+ tests pass on main.

    Files affected:
      src/finterminal/data/migrations/006_mgmt_claims.sql
      src/finterminal/features/registry.py (MAX_FUNDAMENTALS_STALENESS_DAYS, 4 FeatureSpecs promoted)
      src/finterminal/features/freshness.py (last_fundamentals_date, is_fundamentals_data_fresh)
      src/finterminal/features/compute_quality.py (NEW — all 4 compute functions)
      src/finterminal/features/orchestrator.py (quality block added)
      src/finterminal/data/duckdb_store.py (insert_mgmt_claim, list_mgmt_claims)
      tests/features/test_compute_quality.py (NEW — 16 tests)
      tests/test_mgmt_claims.py (NEW — 5 tests)

    Tasks:
      1. Append a dated entry to TerminalVault/05 - Build Log/ — 2026-05-01 — Sub-project 3 Quality Engine v1.md
      2. Create code-map entries under TerminalVault/04 - Code Map/:
         - features — compute_quality.md
      3. Update TerminalVault/04 - Code Map/ entries for registry.py, freshness.py, orchestrator.py, duckdb_store.py
      4. Update TerminalVault/03 - Phases/ to mark #3 as COMPLETE
      5. Cross-link with [[wikilinks]] to [[ADR-019]] and [[Feature Store]]
      6. Update TerminalVault/Index.md if a major new page is added

    Conventions:
      - Date format: YYYY-MM-DD
      - File naming: Title Case With Spaces.md
      - Use [[wikilinks]] not [markdown](links)
      - Keep notes under 200 lines
  """
)
```

- [ ] **Step 4: Final commit (if not already done)**

```bash
git status
```
All working tree should be clean (all changes committed in Tasks 1–6).

---

## Self-review against spec

**Spec coverage check:**
| Requirement | Task |
|-------------|------|
| `roe` feature computed from fundamentals table | Task 3 |
| `leverage` feature (debt_to_equity) from fundamentals | Task 3 |
| `earnings_growth` (YoY net_income_ttm) | Task 3 |
| `quality_score` cross-sectional z-score composite | Task 4 |
| Registry FeatureSpecs promoted (no longer PLACEHOLDER) | Task 2 |
| Orchestrator quality block wired | Task 5 |
| `MAX_FUNDAMENTALS_STALENESS_DAYS = 120` freshness gate | Task 2 |
| `is_fundamentals_data_fresh` follows D12 pattern | Task 2 |
| `mgmt_claims` table schema + migration 006 | Task 1 |
| `insert_mgmt_claim` / `list_mgmt_claims` helpers | Task 6 |
| Existing 266 tests still green | Task 7 |
| Pipeline isolation (D9) not violated | Task 5 Step 7 |
| No NLP extractor (v1 scope) | ✓ — not in plan |

**No placeholders or TODOs detected in plan.**

**Type consistency:** `Result = tuple[float | None, bool]` defined once in `compute_quality.py` and used by all four functions. `_zscore` function returns `float` (not `float | None`). `compute_quality_score` parameters `roe_value`, `leverage_value`, `earnings_growth_value` match the names used in the orchestrator call.
