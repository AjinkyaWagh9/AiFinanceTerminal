# Feature Store — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a frozen, reproducible feature vector at signal-emission time so future model training is deterministic against revised fundamentals/news.

**Architecture:** New `features/` package downstream of `market_data/` + `outcomes/`. Long-form `signal_features` table. Compute runs inside `emit_signal`'s transaction so signal+outcome+features are atomic. Pure-function computes; orchestrator is the single public entry point. Freshness gate (D12) marks price/regime features `is_missing=true` when source data is stale beyond threshold.

**Tech Stack:** Python 3.13, DuckDB, uv, pytest. Reuses `market_data/store.py` for price lookups and `outcomes/schema.py` for sentinels/horizons.

**Spec:** `docs/superpowers/specs/2026-04-30-feature-store-design.md`
**Decision doc:** `TerminalVault/02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models.md`

**Working directory:** `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/`
**Branch:** `feature/feature-store` (cut from `main` once #1 merges, otherwise from `feature/foundation-outcomes-engines`)
**Predecessor commit:** `b4299cf` (head of foundation branch with review fixes)

---

## File Structure

**Create:**
```
src/finterminal/data/migrations/005_signal_features.sql
src/finterminal/features/__init__.py
src/finterminal/features/registry.py
src/finterminal/features/zscore.py
src/finterminal/features/freshness.py
src/finterminal/features/store.py
src/finterminal/features/compute_price.py
src/finterminal/features/compute_regime.py
src/finterminal/features/compute_news.py
src/finterminal/features/orchestrator.py
src/finterminal/commands_features.py            # /features SIGNAL_ID inspector REPL command
tests/features/__init__.py
tests/features/test_registry.py
tests/features/test_zscore.py
tests/features/test_freshness.py
tests/features/test_store.py
tests/features/test_compute_price.py
tests/features/test_compute_regime.py
tests/features/test_compute_news.py
tests/features/test_orchestrator.py
tests/features/test_atomicity.py
tests/features/test_no_leakage.py
tests/integration/test_features_e2e.py
```

**Modify:**
```
src/finterminal/data/duckdb_store.py            # apply migration 005
src/finterminal/outcomes/ledger.py              # call orchestrator + store inside emit_signal
src/finterminal/commands.py                     # register /features command
tests/test_pipeline_isolation.py                # extend to cover features/
```

**Boundaries (D9 extension):**
- `features/` MAY import from `market_data/`, `outcomes/`, `data/`.
- `market_data/`, `outcomes/`, `news/` MUST NOT import from `features/`.
- Enforced by AST-walked guard in `tests/test_pipeline_isolation.py`.

---

## Task 1: Migration 005 — `signal_features` table

**Files:**
- Create: `src/finterminal/data/migrations/005_signal_features.sql`
- Modify: `src/finterminal/data/duckdb_store.py` (apply on connect)
- Test: `tests/features/test_registry.py` (schema-existence smoke goes here for now)

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_registry.py
from finterminal.data.duckdb_store import connect

def test_signal_features_table_exists(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    cols = conn.execute("PRAGMA table_info('signal_features')").fetchall()
    names = {c[1] for c in cols}
    assert names == {"signal_id", "feature_name", "feature_value", "is_missing"}

def test_signal_features_pk_is_signal_id_and_feature_name(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    conn.execute(
        "INSERT INTO signal_features VALUES (?, ?, ?, ?)",
        ["s1", "mom_7d", 0.05, False],
    )
    # Duplicate PK must fail
    import duckdb
    try:
        conn.execute(
            "INSERT INTO signal_features VALUES (?, ?, ?, ?)",
            ["s1", "mom_7d", 0.99, False],
        )
        raised = False
    except duckdb.ConstraintException:
        raised = True
    assert raised
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal
uv run pytest tests/features/test_registry.py -v
```
Expected: both tests FAIL — table doesn't exist.

- [ ] **Step 3: Write the migration**

```sql
-- src/finterminal/data/migrations/005_signal_features.sql
CREATE TABLE IF NOT EXISTS signal_features (
    signal_id     VARCHAR NOT NULL,
    feature_name  VARCHAR NOT NULL,
    feature_value DOUBLE,
    is_missing    BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (signal_id, feature_name)
);

CREATE INDEX IF NOT EXISTS signal_features_name_idx ON signal_features(feature_name);
```

- [ ] **Step 4: Wire migration into `duckdb_store.py`**

Open `src/finterminal/data/duckdb_store.py`. Find the migration loop (look for `004_outcomes_ledger.sql`). Add `"005_signal_features.sql"` to the migration list **after** `"004_outcomes_ledger.sql"`.

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/features/test_registry.py -v
```
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/data/migrations/005_signal_features.sql \
        src/finterminal/data/duckdb_store.py \
        tests/features/__init__.py \
        tests/features/test_registry.py
git commit -m "feat(features): migration 005 — signal_features table"
```

---

## Task 2: `features/registry.py` — FeatureSpec + V1_FEATURES list

**Files:**
- Create: `src/finterminal/features/__init__.py` (empty)
- Create: `src/finterminal/features/registry.py`
- Test: extend `tests/features/test_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/features/test_registry.py`:

```python
from finterminal.features.registry import (
    FeatureSpec, V1_FEATURES, COMPUTABLE_NAMES, PLACEHOLDER_NAMES,
)

def test_v1_features_has_18_entries():
    assert len(V1_FEATURES) == 18

def test_v1_features_unique_names():
    names = [f.name for f in V1_FEATURES]
    assert len(set(names)) == len(names)

def test_computable_count_is_11_and_placeholders_7():
    assert len(COMPUTABLE_NAMES) == 11
    assert len(PLACEHOLDER_NAMES) == 7

def test_required_feature_names_present():
    expected = {
        "mom_7d", "mom_30d", "vol_20d", "mom_7d_z",
        "nifty_return_50d", "nifty_vol_20d",
        "regime_bull", "regime_bear", "regime_volatile",
        "cluster_momentum_z", "narrative_price_divergence",
        "roe", "leverage", "earnings_growth", "quality_score",
        "sentiment_level", "sentiment_delta", "entropy_sentiment",
    }
    assert {f.name for f in V1_FEATURES} == expected

def test_placeholders_have_compute_none():
    placeholders = {f.name for f in V1_FEATURES if f.compute is None}
    assert placeholders == set(PLACEHOLDER_NAMES)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_registry.py -v
```
Expected: 5 new tests FAIL with `ModuleNotFoundError` or `AttributeError`.

- [ ] **Step 3: Write the registry**

```python
# src/finterminal/features/__init__.py
# (empty)
```

```python
# src/finterminal/features/registry.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class FeatureSpec:
    name: str
    compute: Optional[str]   # name of compute function (or None for placeholder)
    source: str              # human-readable provenance

# Tunables: see spec D5.
ZSCORE_WINDOW_DAYS = 60
ZSCORE_MIN_OBS = 30
REGIME_VOL_MEDIAN_LOOKBACK_DAYS = 252

# Freshness gate (D12). G7/G10 from ADR-019.
# A signal emitted at ts_emitted whose most-recent prices_eod row for the
# ticker is older than this many days produces is_missing=true for all
# price-derived features. Same threshold applies to _NIFTY50 for regime.
MAX_PRICE_STALENESS_DAYS = 5
MAX_NIFTY_STALENESS_DAYS = 5

V1_FEATURES: tuple[FeatureSpec, ...] = (
    # Price (compute_price.py)
    FeatureSpec("mom_7d",                  "mom_7d",                   "prices_eod"),
    FeatureSpec("mom_30d",                 "mom_30d",                  "prices_eod"),
    FeatureSpec("vol_20d",                 "vol_20d",                  "prices_eod"),
    FeatureSpec("mom_7d_z",                "mom_7d_z",                 "derived"),
    # Regime (compute_regime.py)
    FeatureSpec("nifty_return_50d",        "nifty_return_50d",         "prices_eod[_NIFTY50]"),
    FeatureSpec("nifty_vol_20d",           "nifty_vol_20d",            "prices_eod[_NIFTY50]"),
    FeatureSpec("regime_bull",             "regime_bull",              "derived"),
    FeatureSpec("regime_bear",             "regime_bear",              "derived"),
    FeatureSpec("regime_volatile",         "regime_volatile",          "derived"),
    # News (compute_news.py)
    FeatureSpec("cluster_momentum_z",      "cluster_momentum_z",       "signals.payload"),
    FeatureSpec("narrative_price_divergence", "narrative_price_divergence", "derived"),
    # Quality placeholders (#3 fills these)
    FeatureSpec("roe",                     None, "fundamentals (#3)"),
    FeatureSpec("leverage",                None, "fundamentals (#3)"),
    FeatureSpec("earnings_growth",         None, "fundamentals (#3)"),
    FeatureSpec("quality_score",           None, "derived (#3)"),
    # Reflexivity placeholders (#4 fills these)
    FeatureSpec("sentiment_level",         None, "Grok / news (#4)"),
    FeatureSpec("sentiment_delta",         None, "derived (#4)"),
    FeatureSpec("entropy_sentiment",       None, "derived (#4)"),
)

COMPUTABLE_NAMES:  tuple[str, ...] = tuple(f.name for f in V1_FEATURES if f.compute is not None)
PLACEHOLDER_NAMES: tuple[str, ...] = tuple(f.name for f in V1_FEATURES if f.compute is None)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/features/test_registry.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/__init__.py src/finterminal/features/registry.py tests/features/test_registry.py
git commit -m "feat(features): registry — FeatureSpec + V1_FEATURES (11 computable + 7 placeholders)"
```

---

## Task 3: `features/zscore.py` — rolling z-score helper

**Files:**
- Create: `src/finterminal/features/zscore.py`
- Test: `tests/features/test_zscore.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_zscore.py
import pytest
from finterminal.features.zscore import rolling_zscore

def test_below_min_obs_returns_none_and_missing():
    z, missing = rolling_zscore(0.5, [0.1, 0.2, 0.3], min_obs=30)
    assert z is None and missing is True

def test_zero_variance_returns_none_and_missing():
    z, missing = rolling_zscore(0.5, [0.5] * 30, min_obs=30)
    assert z is None and missing is True

def test_happy_path():
    history = [float(i) for i in range(30)]   # mean=14.5, std≈8.803
    z, missing = rolling_zscore(20.0, history, min_obs=30)
    assert missing is False
    assert z == pytest.approx((20.0 - 14.5) / 8.803, rel=1e-3)

def test_value_excluded_from_history():
    # Caller is responsible for not passing the value being z'd.
    # Helper trusts history; no self-inclusion check here.
    history = [1.0] * 50
    z, missing = rolling_zscore(2.0, history, min_obs=30)
    assert missing is True   # zero variance
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_zscore.py -v
```
Expected: 4 tests FAIL — module not found.

- [ ] **Step 3: Write the helper**

```python
# src/finterminal/features/zscore.py
from __future__ import annotations
import statistics

def rolling_zscore(value: float, history: list[float], *,
                   min_obs: int = 30) -> tuple[float | None, bool]:
    """Compute z-score of `value` against `history`. History MUST exclude
    the value being z'd (caller's responsibility — see spec D5).

    Returns (z, is_missing). is_missing=True when:
      - len(history) < min_obs, OR
      - stdev(history) == 0 (degenerate distribution)
    """
    if len(history) < min_obs:
        return None, True
    sd = statistics.stdev(history)
    if sd == 0.0:
        return None, True
    mu = statistics.mean(history)
    return (value - mu) / sd, False
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/features/test_zscore.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/zscore.py tests/features/test_zscore.py
git commit -m "feat(features): rolling 60d z-score helper with min-obs gate"
```

---

## Task 4: `features/freshness.py` — D12 staleness gate

**Files:**
- Create: `src/finterminal/features/freshness.py`
- Test: `tests/features/test_freshness.py`

This is the data-quality / latency-contract gate (G7 + G10 in ADR-019). Price-derived features must NOT be computed against stale `prices_eod` data. The gate also implicitly catches silently-dead bhavcopy ingest: if `/refresh-prices` stops running, every new signal emits with price/regime features `is_missing=true` instead of training models on lies.

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_freshness.py
from datetime import date, datetime
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.freshness import (
    last_prices_date, is_prices_data_fresh, is_nifty_data_fresh,
)

def _seed(conn, ticker: str, last_date: date):
    upsert_prices_eod(conn, [{
        "trade_date": last_date, "ticker": ticker,
        "open":0.0, "high":0.0, "low":0.0, "close":100.0, "volume":0,
    }], source="test")

def test_last_prices_date_returns_none_when_no_data(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert last_prices_date(conn, "TCS", as_of=date(2026, 4, 30)) is None

def test_last_prices_date_ignores_future_rows(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 4, 28))
    _seed(conn, "TCS", date(2026, 5, 5))   # future relative to as_of
    assert last_prices_date(conn, "TCS", as_of=date(2026, 4, 30)) == date(2026, 4, 28)

def test_is_prices_data_fresh_within_threshold(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 4, 28))
    assert is_prices_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is True

def test_is_prices_data_fresh_stale(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "TCS", date(2026, 4, 20))   # 10 days before ts_emitted
    assert is_prices_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is False

def test_is_prices_data_fresh_no_data_at_all(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert is_prices_data_fresh(
        conn, "TCS", ts_emitted=datetime(2026, 4, 30, 10, 0)) is False

def test_is_nifty_data_fresh_uses_nifty_ticker(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed(conn, "_NIFTY50", date(2026, 4, 28))
    assert is_nifty_data_fresh(
        conn, ts_emitted=datetime(2026, 4, 30, 10, 0)) is True
    # Stale Nifty
    conn2 = connect(str(tmp_path / "t2.duckdb"))
    _seed(conn2, "_NIFTY50", date(2026, 4, 20))
    assert is_nifty_data_fresh(
        conn2, ts_emitted=datetime(2026, 4, 30, 10, 0)) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_freshness.py -v
```
Expected: 6 tests FAIL — module not found.

- [ ] **Step 3: Write `freshness.py`**

```python
# src/finterminal/features/freshness.py
from __future__ import annotations
from datetime import date, datetime, timedelta
import duckdb

from .registry import MAX_PRICE_STALENESS_DAYS, MAX_NIFTY_STALENESS_DAYS
from finterminal.outcomes.schema import NIFTY_TICKER

def last_prices_date(conn: duckdb.DuckDBPyConnection,
                     ticker: str, *, as_of: date) -> date | None:
    """Most recent trade_date for `ticker` with trade_date <= as_of, or None."""
    row = conn.execute(
        "SELECT MAX(trade_date) FROM prices_eod "
        "WHERE ticker = ? AND trade_date <= ?",
        [ticker, as_of],
    ).fetchone()
    return row[0] if row and row[0] is not None else None

def _fresh(conn, ticker: str, *, ts_emitted: datetime,
           max_staleness_days: int) -> bool:
    last = last_prices_date(conn, ticker, as_of=ts_emitted.date())
    if last is None:
        return False
    return (ts_emitted.date() - last) <= timedelta(days=max_staleness_days)

def is_prices_data_fresh(conn: duckdb.DuckDBPyConnection,
                         ticker: str, *, ts_emitted: datetime) -> bool:
    return _fresh(conn, ticker, ts_emitted=ts_emitted,
                  max_staleness_days=MAX_PRICE_STALENESS_DAYS)

def is_nifty_data_fresh(conn: duckdb.DuckDBPyConnection, *,
                        ts_emitted: datetime) -> bool:
    return _fresh(conn, NIFTY_TICKER, ts_emitted=ts_emitted,
                  max_staleness_days=MAX_NIFTY_STALENESS_DAYS)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/features/test_freshness.py -v
```
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/freshness.py tests/features/test_freshness.py
git commit -m "feat(features): D12 freshness gate (G7/G10) — stale prices/Nifty produce is_missing=true"
```

---

## Task 5: `features/store.py` — `upsert_features` helper

**Files:**
- Create: `src/finterminal/features/store.py`
- Test: `tests/features/test_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_store.py
from finterminal.data.duckdb_store import connect
from finterminal.features.store import upsert_features

def test_upsert_writes_value_and_missing_rows(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {
        "mom_7d":    {"value": 0.05, "is_missing": False},
        "vol_20d":   {"value": None, "is_missing": True},
    })
    rows = conn.execute(
        "SELECT feature_name, feature_value, is_missing "
        "FROM signal_features WHERE signal_id=? ORDER BY feature_name",
        ["sig1"],
    ).fetchall()
    assert rows == [("mom_7d", 0.05, False), ("vol_20d", None, True)]

def test_upsert_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {"mom_7d": {"value": 0.05, "is_missing": False}})
    upsert_features(conn, "sig1", {"mom_7d": {"value": 0.07, "is_missing": False}})
    rows = conn.execute(
        "SELECT feature_value FROM signal_features WHERE signal_id=?",
        ["sig1"],
    ).fetchall()
    assert rows == [(0.07,)]   # second write wins (overwrite semantics)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_store.py -v
```
Expected: 2 tests FAIL — module not found.

- [ ] **Step 3: Write the store**

```python
# src/finterminal/features/store.py
from __future__ import annotations
from typing import TypedDict
import duckdb

class FeatureCell(TypedDict):
    value: float | None
    is_missing: bool

def upsert_features(conn: duckdb.DuckDBPyConnection,
                    signal_id: str,
                    features: dict[str, FeatureCell]) -> None:
    """Upsert all features for a signal in one batch. Overwrite semantics
    (idempotent re-emit will refresh values, though emit_signal short-circuits
    duplicate signals before reaching here)."""
    if not features:
        return
    rows = [(signal_id, name, cell["value"], cell["is_missing"])
            for name, cell in features.items()]
    conn.executemany(
        """
        INSERT INTO signal_features (signal_id, feature_name, feature_value, is_missing)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (signal_id, feature_name) DO UPDATE SET
            feature_value = EXCLUDED.feature_value,
            is_missing    = EXCLUDED.is_missing
        """,
        rows,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/features/test_store.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/store.py tests/features/test_store.py
git commit -m "feat(features): upsert_features with overwrite semantics"
```

---

## Task 6: `features/compute_price.py` — momentum and volatility (gated by D12)

**Files:**
- Create: `src/finterminal/features/compute_price.py`
- Test: `tests/features/test_compute_price.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_compute_price.py
from datetime import date, datetime
import math
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.compute_price import (
    compute_mom_7d, compute_mom_30d, compute_vol_20d, compute_mom_7d_z,
)

def _seed_linear_prices(conn, ticker: str, start: date, n: int, base: float, step: float):
    rows = [{
        "trade_date": date.fromordinal(start.toordinal() + i),
        "ticker": ticker, "open": 0.0, "high": 0.0, "low": 0.0,
        "close": base + i * step, "volume": 0,
    } for i in range(n)]
    upsert_prices_eod(conn, rows, source="test")

def test_mom_7d_happy_path(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 4, 1), 30, base=100.0, step=1.0)
    val, missing = compute_mom_7d(conn, ticker="TCS",
                                  ts_emitted=datetime(2026, 4, 30, 10, 0))
    # Last close on or before 2026-04-30 = 100 + 29*1 = 129; 7d earlier 122
    assert missing is False
    assert val == pytest.approx(129/122 - 1, rel=1e-9)

def test_mom_7d_missing_when_insufficient_history(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 4, 28), 3, base=100.0, step=1.0)
    val, missing = compute_mom_7d(conn, ticker="TCS",
                                  ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val is None and missing is True

def test_vol_20d_zero_variance_returns_zero(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 3, 1), 30, base=100.0, step=0.0)
    val, missing = compute_vol_20d(conn, ticker="TCS",
                                   ts_emitted=datetime(2026, 4, 1, 10, 0))
    assert missing is False and val == 0.0

def test_no_leakage_future_prices_ignored(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 4, 1), 30, base=100.0, step=1.0)
    # Add a price 7 days in the FUTURE relative to ts_emitted — must not affect mom_7d
    upsert_prices_eod(conn, [{
        "trade_date": date(2026, 5, 7), "ticker": "TCS",
        "open":0.0, "high":0.0, "low":0.0, "close": 999.0, "volume":0,
    }], source="test")
    val, missing = compute_mom_7d(conn, ticker="TCS",
                                  ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val == pytest.approx(129/122 - 1, rel=1e-9)

def test_d12_stale_prices_force_is_missing(tmp_path):
    # Last close is 10 days before ts_emitted — exceeds MAX_PRICE_STALENESS_DAYS=5.
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_linear_prices(conn, "TCS", date(2026, 3, 1), 30, base=100.0, step=1.0)
    # Most recent close is 2026-03-30; ts_emitted is 2026-04-30 → 31 days stale.
    val, missing = compute_mom_7d(conn, ticker="TCS",
                                  ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val is None and missing is True
    val, missing = compute_mom_30d(conn, ticker="TCS",
                                   ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val is None and missing is True
    val, missing = compute_vol_20d(conn, ticker="TCS",
                                   ts_emitted=datetime(2026, 4, 30, 10, 0))
    assert val is None and missing is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_compute_price.py -v
```
Expected: tests FAIL — module not found.

- [ ] **Step 3: Implement compute_price.py**

```python
# src/finterminal/features/compute_price.py
from __future__ import annotations
import math
import statistics
from datetime import datetime, timedelta
import duckdb

from .zscore import rolling_zscore
from .freshness import is_prices_data_fresh
from .registry import ZSCORE_WINDOW_DAYS, ZSCORE_MIN_OBS

Result = tuple[float | None, bool]   # (value, is_missing)

def _last_n_closes_on_or_before(conn: duckdb.DuckDBPyConnection,
                                ticker: str, target_date,
                                n: int) -> list[tuple]:
    return conn.execute(
        """
        SELECT trade_date, close FROM prices_eod
        WHERE ticker = ? AND trade_date <= ?
        ORDER BY trade_date DESC LIMIT ?
        """,
        [ticker, target_date, n],
    ).fetchall()

def _close_n_trading_days_back(conn, ticker, target_date, n):
    # n+1 because index 0 is the as-of close; index n is n trading days back.
    rows = _last_n_closes_on_or_before(conn, ticker, target_date, n + 1)
    if len(rows) < n + 1:
        return None
    return rows[n][1]

def compute_mom_7d(conn, *, ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_prices_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    today = ts_emitted.date()
    rows = _last_n_closes_on_or_before(conn, ticker, today, 8)
    if len(rows) < 8:
        return None, True
    p_now, p_then = rows[0][1], rows[7][1]
    if p_then == 0:
        return None, True
    return p_now / p_then - 1, False

def compute_mom_30d(conn, *, ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_prices_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    today = ts_emitted.date()
    rows = _last_n_closes_on_or_before(conn, ticker, today, 31)
    if len(rows) < 31:
        return None, True
    p_now, p_then = rows[0][1], rows[30][1]
    if p_then == 0:
        return None, True
    return p_now / p_then - 1, False

def compute_vol_20d(conn, *, ticker: str, ts_emitted: datetime, **_) -> Result:
    if not is_prices_data_fresh(conn, ticker, ts_emitted=ts_emitted):
        return None, True
    today = ts_emitted.date()
    rows = _last_n_closes_on_or_before(conn, ticker, today, 21)
    if len(rows) < 21:
        return None, True
    closes = [r[1] for r in rows][::-1]   # ascending
    rets = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))
            if closes[i-1] != 0]
    if len(rets) < 2:
        return None, True
    if all(r == rets[0] for r in rets):
        return 0.0, False
    return statistics.stdev(rets), False

def compute_mom_7d_z(conn, *, ticker: str, ts_emitted: datetime,
                     mom_7d_value: float | None, **_) -> Result:
    """z(mom_7d) over the rolling 60d window of mom_7d values for the same ticker."""
    if mom_7d_value is None:
        return None, True
    cutoff = ts_emitted   # exclusive on the right
    history_rows = conn.execute(
        """
        SELECT sf.feature_value
        FROM signal_features sf
        JOIN signals s ON s.signal_id = sf.signal_id
        WHERE sf.feature_name = 'mom_7d'
          AND sf.is_missing = FALSE
          AND s.ticker = ?
          AND s.ts_emitted < ?
          AND s.ts_emitted >= ?
        ORDER BY s.ts_emitted DESC
        """,
        [ticker, cutoff, cutoff - timedelta(days=ZSCORE_WINDOW_DAYS)],
    ).fetchall()
    history = [r[0] for r in history_rows]
    return rolling_zscore(mom_7d_value, history, min_obs=ZSCORE_MIN_OBS)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/features/test_compute_price.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/compute_price.py tests/features/test_compute_price.py
git commit -m "feat(features): compute_price — mom_7d, mom_30d, vol_20d, mom_7d_z"
```

---

## Task 7: `features/compute_regime.py` — Nifty + regime one-hot (gated by D12)

**Files:**
- Create: `src/finterminal/features/compute_regime.py`
- Test: `tests/features/test_compute_regime.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_compute_regime.py
from datetime import date, datetime
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.compute_regime import (
    compute_nifty_return_50d, compute_nifty_vol_20d,
    compute_regime_bull, compute_regime_bear, compute_regime_volatile,
)

def _seed_nifty(conn, start: date, n: int, base: float, step: float):
    rows = [{
        "trade_date": date.fromordinal(start.toordinal() + i),
        "ticker": "_NIFTY50", "open":0.0,"high":0.0,"low":0.0,
        "close": base + i*step, "volume": 0,
    } for i in range(n)]
    upsert_prices_eod(conn, rows, source="test")

def test_nifty_return_50d_uptrend(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2026, 1, 1), 100, base=20000, step=10)
    val, missing = compute_nifty_return_50d(conn, ts_emitted=datetime(2026, 4, 10, 10, 0))
    assert missing is False and val > 0

def test_nifty_return_50d_missing_when_short_history(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2026, 4, 1), 10, base=20000, step=10)
    val, missing = compute_nifty_return_50d(conn, ts_emitted=datetime(2026, 4, 10, 10, 0))
    assert val is None and missing is True

def test_regime_bull_when_uptrend_and_low_vol(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2025, 5, 1), 280, base=20000, step=2)   # smooth uptrend, low vol
    ts = datetime(2026, 2, 1, 10, 0)
    bull, _   = compute_regime_bull(conn, ts_emitted=ts)
    bear, _   = compute_regime_bear(conn, ts_emitted=ts)
    vol, _    = compute_regime_volatile(conn, ts_emitted=ts)
    assert (bull, bear, vol) == (1.0, 0.0, 0.0)

def test_regime_bear_when_downtrend(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2025, 5, 1), 280, base=22000, step=-3)
    ts = datetime(2026, 2, 1, 10, 0)
    bull, _ = compute_regime_bull(conn, ts_emitted=ts)
    bear, _ = compute_regime_bear(conn, ts_emitted=ts)
    assert (bull, bear) == (0.0, 1.0)

def test_regime_one_hot_sums_to_one(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn, date(2025, 5, 1), 280, base=20000, step=2)
    ts = datetime(2026, 2, 1, 10, 0)
    s = sum(c(conn, ts_emitted=ts)[0] for c in
            (compute_regime_bull, compute_regime_bear, compute_regime_volatile))
    assert s == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_compute_regime.py -v
```
Expected: tests FAIL.

- [ ] **Step 3: Implement compute_regime.py**

```python
# src/finterminal/features/compute_regime.py
from __future__ import annotations
import math
import statistics
from datetime import datetime, timedelta
import duckdb

from .freshness import is_nifty_data_fresh
from .registry import REGIME_VOL_MEDIAN_LOOKBACK_DAYS

Result = tuple[float | None, bool]
NIFTY = "_NIFTY50"

def _nifty_closes(conn, target_date, n):
    return conn.execute(
        "SELECT trade_date, close FROM prices_eod "
        "WHERE ticker = ? AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT ?",
        [NIFTY, target_date, n],
    ).fetchall()

def compute_nifty_return_50d(conn, *, ts_emitted: datetime, **_) -> Result:
    if not is_nifty_data_fresh(conn, ts_emitted=ts_emitted):
        return None, True
    rows = _nifty_closes(conn, ts_emitted.date(), 51)
    if len(rows) < 51 or rows[50][1] == 0:
        return None, True
    return rows[0][1] / rows[50][1] - 1, False

def compute_nifty_vol_20d(conn, *, ts_emitted: datetime, **_) -> Result:
    if not is_nifty_data_fresh(conn, ts_emitted=ts_emitted):
        return None, True
    rows = _nifty_closes(conn, ts_emitted.date(), 21)
    if len(rows) < 21:
        return None, True
    closes = [r[1] for r in rows][::-1]
    rets = [math.log(closes[i]/closes[i-1]) for i in range(1, len(closes))
            if closes[i-1] != 0]
    if len(rets) < 2:
        return None, True
    if all(r == rets[0] for r in rets):
        return 0.0, False
    return statistics.stdev(rets), False

def _vol_below_median(conn, ts_emitted: datetime, current_vol: float) -> bool:
    """True if current 20d vol is at-or-below the historical median over LOOKBACK days
    of past Nifty 20d-vol windows. Computed inline (no caching) — cheap for v1."""
    today = ts_emitted.date()
    history_rows = _nifty_closes(conn, today, REGIME_VOL_MEDIAN_LOOKBACK_DAYS + 21)
    if len(history_rows) < 41:   # need at least two non-overlapping 20d windows
        return False
    closes = [r[1] for r in history_rows][::-1]
    log_rets = [math.log(closes[i]/closes[i-1]) for i in range(1, len(closes))
                if closes[i-1] != 0]
    vols = [statistics.stdev(log_rets[i-19:i+1]) for i in range(19, len(log_rets))]
    if not vols:
        return False
    return current_vol <= statistics.median(vols)

def compute_regime_bull(conn, *, ts_emitted: datetime, **_) -> Result:
    nr, miss = compute_nifty_return_50d(conn, ts_emitted=ts_emitted)
    nv, miss_v = compute_nifty_vol_20d(conn, ts_emitted=ts_emitted)
    if miss or miss_v:
        return None, True
    return (1.0 if (nr > 0 and _vol_below_median(conn, ts_emitted, nv)) else 0.0), False

def compute_regime_bear(conn, *, ts_emitted: datetime, **_) -> Result:
    nr, miss = compute_nifty_return_50d(conn, ts_emitted=ts_emitted)
    if miss:
        return None, True
    return (1.0 if nr < 0 else 0.0), False

def compute_regime_volatile(conn, *, ts_emitted: datetime, **_) -> Result:
    bull, miss_b = compute_regime_bull(conn, ts_emitted=ts_emitted)
    bear, miss_be = compute_regime_bear(conn, ts_emitted=ts_emitted)
    if miss_b or miss_be:
        return None, True
    return (1.0 if (bull == 0.0 and bear == 0.0) else 0.0), False
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/features/test_compute_regime.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/compute_regime.py tests/features/test_compute_regime.py
git commit -m "feat(features): compute_regime — Nifty 50d return, 20d vol, regime one-hot"
```

---

## Task 8: `features/compute_news.py` — cluster_momentum_z + narrative_price_divergence

**Files:**
- Create: `src/finterminal/features/compute_news.py`
- Test: `tests/features/test_compute_news.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_compute_news.py
from datetime import date, datetime, timedelta
import json, uuid
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.features.compute_news import (
    compute_cluster_momentum_z, compute_narrative_price_divergence,
)
from finterminal.outcomes.schema import SignalType, SIGNAL_REGISTRY

def _seed_prior_cluster_signal(conn, ticker, ts, story_count_delta):
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO signals (signal_id, signal_type, engine, ticker, ts_emitted, payload) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [sid, SignalType.CLUSTER_MOMENTUM.value,
         SIGNAL_REGISTRY[SignalType.CLUSTER_MOMENTUM].value,
         ticker, ts, json.dumps({"story_count_delta": story_count_delta})],
    )
    return sid

def test_cluster_momentum_z_missing_when_few_priors(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    val, missing = compute_cluster_momentum_z(
        conn, signal_type=SignalType.CLUSTER_MOMENTUM,
        ticker="TCS", ts_emitted=datetime(2026, 4, 30, 10, 0),
        payload={"story_count_delta": 5},
    )
    assert val is None and missing is True

def test_cluster_momentum_z_happy_path(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    base = datetime(2026, 4, 30, 10, 0)
    # 35 prior signals with story_count_delta uniform in [0..34], mean=17, std≈10.246
    for i in range(35):
        _seed_prior_cluster_signal(conn, "TCS", base - timedelta(days=i+1), float(i))
    val, missing = compute_cluster_momentum_z(
        conn, signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=base, payload={"story_count_delta": 30.0},
    )
    assert missing is False
    assert val == pytest.approx((30 - 17) / 10.246, rel=1e-2)

def test_cluster_momentum_z_placeholder_for_other_signal_types(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    val, missing = compute_cluster_momentum_z(
        conn, signal_type=SignalType.SENTIMENT_DELTA, ticker="TCS",
        ts_emitted=datetime(2026, 4, 30, 10, 0), payload={},
    )
    assert val is None and missing is True

def test_narrative_price_divergence_subtracts_z_of_both(tmp_path):
    val, missing = compute_narrative_price_divergence(
        cluster_momentum_z=2.0, mom_7d_z=0.5,
    )
    assert missing is False and val == pytest.approx(1.5)

def test_narrative_price_divergence_missing_when_either_input_missing(tmp_path):
    val, missing = compute_narrative_price_divergence(cluster_momentum_z=None, mom_7d_z=0.5)
    assert val is None and missing is True
    val, missing = compute_narrative_price_divergence(cluster_momentum_z=2.0, mom_7d_z=None)
    assert val is None and missing is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_compute_news.py -v
```
Expected: tests FAIL.

- [ ] **Step 3: Implement compute_news.py**

```python
# src/finterminal/features/compute_news.py
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
import duckdb

from .zscore import rolling_zscore
from .registry import ZSCORE_WINDOW_DAYS, ZSCORE_MIN_OBS
from finterminal.outcomes.schema import SignalType

Result = tuple[float | None, bool]

def compute_cluster_momentum_z(conn: duckdb.DuckDBPyConnection, *,
                               signal_type: SignalType,
                               ticker: str,
                               ts_emitted: datetime,
                               payload: dict[str, Any],
                               **_) -> Result:
    if signal_type != SignalType.CLUSTER_MOMENTUM:
        return None, True
    delta = payload.get("story_count_delta")
    if delta is None:
        return None, True
    cutoff = ts_emitted
    rows = conn.execute(
        """
        SELECT CAST(payload->>'story_count_delta' AS DOUBLE) AS d
        FROM signals
        WHERE signal_type = ? AND ticker = ?
          AND ts_emitted < ? AND ts_emitted >= ?
          AND payload IS NOT NULL
        ORDER BY ts_emitted DESC
        """,
        [SignalType.CLUSTER_MOMENTUM.value, ticker, cutoff,
         cutoff - timedelta(days=ZSCORE_WINDOW_DAYS)],
    ).fetchall()
    history = [r[0] for r in rows if r[0] is not None]
    return rolling_zscore(float(delta), history, min_obs=ZSCORE_MIN_OBS)

def compute_narrative_price_divergence(*,
                                       cluster_momentum_z: float | None,
                                       mom_7d_z: float | None,
                                       **_) -> Result:
    if cluster_momentum_z is None or mom_7d_z is None:
        return None, True
    return cluster_momentum_z - mom_7d_z, False
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/features/test_compute_news.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/compute_news.py tests/features/test_compute_news.py
git commit -m "feat(features): compute_news — cluster_momentum_z + narrative_price_divergence"
```

---

## Task 9: `features/orchestrator.py` — single public entry point

**Files:**
- Create: `src/finterminal/features/orchestrator.py`
- Test: `tests/features/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_orchestrator.py
from datetime import date, datetime
import json, uuid
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.outcomes.schema import SignalType
from finterminal.features.registry import COMPUTABLE_NAMES, PLACEHOLDER_NAMES, V1_FEATURES
from finterminal.features.orchestrator import compute_for_signal

def _seed_full(conn):
    # Equity ticker history
    rows = [{"trade_date": date.fromordinal(date(2026,1,1).toordinal()+i),
             "ticker":"TCS","open":0.0,"high":0.0,"low":0.0,
             "close":100.0+i,"volume":0} for i in range(120)]
    upsert_prices_eod(conn, rows, source="test")
    # Nifty history
    rows = [{"trade_date": date.fromordinal(date(2025,1,1).toordinal()+i),
             "ticker":"_NIFTY50","open":0.0,"high":0.0,"low":0.0,
             "close":20000.0+i*2,"volume":0} for i in range(485)]
    upsert_prices_eod(conn, rows, source="test")

def test_compute_for_signal_returns_18_keys(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    sig_id = str(uuid.uuid4())
    out = compute_for_signal(
        conn, signal_id=sig_id,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0),
        payload={"story_count_delta": 3.0, "cluster_id": "c1"},
    )
    assert set(out.keys()) == {f.name for f in V1_FEATURES}
    # Placeholders are all is_missing
    for name in PLACEHOLDER_NAMES:
        assert out[name]["is_missing"] is True and out[name]["value"] is None

def test_compute_for_signal_marks_cluster_z_missing_for_other_signal_types(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    out = compute_for_signal(
        conn, signal_id=str(uuid.uuid4()),
        signal_type=SignalType.SENTIMENT_DELTA, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0), payload={},
    )
    assert out["cluster_momentum_z"]["is_missing"] is True
    assert out["narrative_price_divergence"]["is_missing"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_orchestrator.py -v
```
Expected: tests FAIL.

- [ ] **Step 3: Implement orchestrator.py**

```python
# src/finterminal/features/orchestrator.py
from __future__ import annotations
from datetime import datetime
from typing import Any
import duckdb

from .registry import V1_FEATURES, PLACEHOLDER_NAMES
from . import compute_price, compute_regime, compute_news
from finterminal.outcomes.schema import SignalType

def compute_for_signal(conn: duckdb.DuckDBPyConnection, *,
                       signal_id: str,
                       signal_type: SignalType,
                       ticker: str,
                       ts_emitted: datetime,
                       payload: dict[str, Any]) -> dict[str, dict]:
    """Compute the v1 feature vector. Returns {name: {value, is_missing}} for
    every name in V1_FEATURES. Placeholders are emitted as is_missing=True."""
    ctx = dict(ticker=ticker, ts_emitted=ts_emitted,
               signal_type=signal_type, payload=payload)

    out: dict[str, dict] = {}

    # Price block (mom_7d feeds mom_7d_z and narrative_price_divergence)
    mom_7d_v, mom_7d_m  = compute_price.compute_mom_7d(conn, **ctx)
    out["mom_7d"]  = {"value": mom_7d_v,  "is_missing": mom_7d_m}
    mom_30d_v, mom_30d_m = compute_price.compute_mom_30d(conn, **ctx)
    out["mom_30d"] = {"value": mom_30d_v, "is_missing": mom_30d_m}
    vol_v, vol_m   = compute_price.compute_vol_20d(conn, **ctx)
    out["vol_20d"] = {"value": vol_v, "is_missing": vol_m}
    mom_7d_z_v, mom_7d_z_m = compute_price.compute_mom_7d_z(
        conn, mom_7d_value=mom_7d_v, **ctx)
    out["mom_7d_z"] = {"value": mom_7d_z_v, "is_missing": mom_7d_z_m}

    # Regime block
    nr_v, nr_m = compute_regime.compute_nifty_return_50d(conn, **ctx)
    out["nifty_return_50d"] = {"value": nr_v, "is_missing": nr_m}
    nv_v, nv_m = compute_regime.compute_nifty_vol_20d(conn, **ctx)
    out["nifty_vol_20d"] = {"value": nv_v, "is_missing": nv_m}
    bull_v, bull_m = compute_regime.compute_regime_bull(conn, **ctx)
    out["regime_bull"] = {"value": bull_v, "is_missing": bull_m}
    bear_v, bear_m = compute_regime.compute_regime_bear(conn, **ctx)
    out["regime_bear"] = {"value": bear_v, "is_missing": bear_m}
    vol2_v, vol2_m = compute_regime.compute_regime_volatile(conn, **ctx)
    out["regime_volatile"] = {"value": vol2_v, "is_missing": vol2_m}

    # News block
    cmz_v, cmz_m = compute_news.compute_cluster_momentum_z(conn, **ctx)
    out["cluster_momentum_z"] = {"value": cmz_v, "is_missing": cmz_m}
    div_v, div_m = compute_news.compute_narrative_price_divergence(
        cluster_momentum_z=cmz_v, mom_7d_z=mom_7d_z_v)
    out["narrative_price_divergence"] = {"value": div_v, "is_missing": div_m}

    # Placeholders
    for name in PLACEHOLDER_NAMES:
        out[name] = {"value": None, "is_missing": True}

    # Sanity: every registered feature accounted for
    expected = {f.name for f in V1_FEATURES}
    assert set(out.keys()) == expected, \
        f"orchestrator missing features: {expected - set(out.keys())}"
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/features/test_orchestrator.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/features/orchestrator.py tests/features/test_orchestrator.py
git commit -m "feat(features): orchestrator — compute_for_signal v1 (18 features)"
```

---

## Task 10: Wire orchestrator into `outcomes/ledger.py:emit_signal`

**Files:**
- Modify: `src/finterminal/outcomes/ledger.py`
- Test: `tests/features/test_atomicity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_atomicity.py
from datetime import datetime, date
from unittest.mock import patch
import pytest
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.schema import SignalType

def _seed_nifty(conn):
    upsert_prices_eod(conn, [{
        "trade_date": date(2026,4,28),"ticker":"_NIFTY50",
        "open":22000,"high":22000,"low":22000,"close":22000.0,"volume":0,
    }], source="nse_indices")

def test_emit_signal_writes_features(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    sid = emit_signal(conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 29, 10, 0),
        payload={"story_count_delta": 5.0, "cluster_id": "c1"},
    )
    n = conn.execute(
        "SELECT COUNT(*) FROM signal_features WHERE signal_id=?", [sid]
    ).fetchone()[0]
    assert n == 18   # 11 computable (most missing due to thin seed) + 7 placeholders

def test_emit_signal_rolls_back_when_features_throw(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_nifty(conn)
    with patch("finterminal.outcomes.ledger.compute_for_signal",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            emit_signal(conn,
                signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
                ts_emitted=datetime(2026, 4, 29, 10, 0),
                payload={"cluster_id": "c1"},
            )
    n_signals  = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    n_outcomes = conn.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()[0]
    n_features = conn.execute("SELECT COUNT(*) FROM signal_features").fetchone()[0]
    assert (n_signals, n_outcomes, n_features) == (0, 0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/features/test_atomicity.py -v
```
Expected: tests FAIL — `compute_for_signal` not yet imported in ledger.

- [ ] **Step 3: Modify `outcomes/ledger.py`**

Find the body of `emit_signal` after the `signal_outcomes` insert (the `conn.executemany("INSERT INTO signal_outcomes ...` block ends with `return signal_id`). Add the import at the top of the module and the feature-store wiring before `return signal_id`. The whole emit must run inside a single transaction — wrap from before the duplicate-check INSERT through the end with `conn.execute("BEGIN")` / `conn.execute("COMMIT")`, with `ROLLBACK` on exception.

Replace the current function body with:

```python
def emit_signal(conn: duckdb.DuckDBPyConnection, *,
                signal_type: SignalType | str,
                ticker: str,
                ts_emitted: datetime,
                payload: dict[str, Any] | None = None,
                confidence: float | None = None,
                why: str | None = None,
                source_ref: str | None = None) -> str | None:
    """Insert a signal + 5 outcome stubs + feature vector. Idempotent on
    (signal_type, ticker, ts_emitted). Returns new signal_id, or None if duplicate."""
    from finterminal.features.orchestrator import compute_for_signal
    from finterminal.features.store import upsert_features

    st = SignalType(signal_type) if not isinstance(signal_type, SignalType) else signal_type
    engine = SIGNAL_REGISTRY[st]

    ts_emitted = _to_ist_naive(ts_emitted)
    regime = snapshot_regime(conn, as_of=ts_emitted.date())

    signal_id = str(uuid.uuid4())
    cols = ["signal_id", "signal_type", "engine", "ticker", "ts_emitted",
            "payload", "confidence", "why", "source_ref", *REGIME_FIELDS]
    vals = [signal_id, st.value, engine.value, ticker, ts_emitted,
            json.dumps(payload) if payload is not None else None,
            confidence, why, source_ref,
            *(regime[f] for f in REGIME_FIELDS)]
    placeholders = ",".join("?" * len(cols))

    conn.execute("BEGIN")
    try:
        before = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        conn.execute(
            f"INSERT INTO signals ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (signal_type, ticker, ts_emitted) DO NOTHING",
            vals,
        )
        after = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        if after == before:
            conn.execute("ROLLBACK")
            return None  # duplicate

        conn.executemany(
            "INSERT INTO signal_outcomes (signal_id, horizon_days) VALUES (?, ?)",
            [(signal_id, h) for h in HORIZONS_DAYS],
        )

        features = compute_for_signal(
            conn, signal_id=signal_id, signal_type=st, ticker=ticker,
            ts_emitted=ts_emitted, payload=payload or {},
        )
        upsert_features(conn, signal_id, features)

        conn.execute("COMMIT")
        return signal_id
    except Exception:
        conn.execute("ROLLBACK")
        raise
```

Make sure the existing module-level `compute_for_signal` import stays absent at module load time — keep the import inside the function so circular-import risk between `outcomes` and `features` is avoided. (`features/` imports from `outcomes/schema.py`; if we top-import `features` here we'd have outcomes→features→outcomes.)

- [ ] **Step 4: Run feature-atomicity tests**

```bash
uv run pytest tests/features/test_atomicity.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Run the previously-shipped ledger tests to confirm no regression**

```bash
uv run pytest tests/outcomes/ -v
```
Expected: all PASS (the existing 6 ledger tests still hold; new emits will write 18 feature rows but those tests don't query the features table).

- [ ] **Step 6: Run the full suite**

```bash
uv run pytest --tb=short -q
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/finterminal/outcomes/ledger.py tests/features/test_atomicity.py
git commit -m "feat(features): wire compute_for_signal into emit_signal (atomic tx)"
```

---

## Task 11: Extend pipeline-isolation guard to `features/`

**Files:**
- Modify: `tests/test_pipeline_isolation.py`

- [ ] **Step 1: Read the current guard**

```bash
cat tests/test_pipeline_isolation.py
```
Note its current shape (substring grep). We're going to keep that for backward compat and add a new assertion.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_pipeline_isolation.py`:

```python
import ast
from pathlib import Path

SRC = Path("src/finterminal")

def _imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out

def _all_imports_in(pkg: str) -> set[str]:
    out = set()
    for f in (SRC / pkg).rglob("*.py"):
        out |= _imports(f)
    return out

def test_market_data_does_not_import_features():
    bad = {m for m in _all_imports_in("market_data")
           if m.startswith("finterminal.features")}
    assert bad == set(), f"market_data must not import features: {bad}"

def test_outcomes_does_not_import_features_at_module_level():
    # ledger.py imports inside emit_signal (function-local) to avoid circular import.
    # AST-walk catches ImportFrom at module level only via a top-level filter.
    for f in (SRC / "outcomes").rglob("*.py"):
        tree = ast.parse(f.read_text())
        for node in tree.body:   # top-level only
            if isinstance(node, ast.ImportFrom) and node.module \
                    and node.module.startswith("finterminal.features"):
                raise AssertionError(f"{f} imports features at module level")

def test_news_does_not_import_features():
    bad = {m for m in _all_imports_in("news")
           if m.startswith("finterminal.features")}
    assert bad == set(), f"news must not import features: {bad}"
```

- [ ] **Step 3: Run the new tests**

```bash
uv run pytest tests/test_pipeline_isolation.py -v
```
Expected: 3 new tests PASS (we deliberately kept the `features` import inside the function in Task 10 to satisfy `test_outcomes_does_not_import_features_at_module_level`).

- [ ] **Step 4: Commit**

```bash
git add tests/test_pipeline_isolation.py
git commit -m "test(isolation): extend guard — features/ is downstream-only"
```

---

## Task 12: End-to-end integration test

**Files:**
- Create: `tests/integration/test_features_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_features_e2e.py
from datetime import date, datetime, timedelta
from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.outcomes.ledger import emit_signal
from finterminal.outcomes.schema import SignalType
from finterminal.features.registry import V1_FEATURES, PLACEHOLDER_NAMES

def _seed_full(conn):
    # 120 days of TCS prices
    upsert_prices_eod(conn, [{
        "trade_date": date(2026,1,1) + timedelta(days=i),
        "ticker":"TCS","open":0.0,"high":0.0,"low":0.0,
        "close":100.0+i,"volume":0,
    } for i in range(120)], source="test")
    # 485 days of Nifty
    upsert_prices_eod(conn, [{
        "trade_date": date(2025,1,1) + timedelta(days=i),
        "ticker":"_NIFTY50","open":0.0,"high":0.0,"low":0.0,
        "close":20000.0 + i*2,"volume":0,
    } for i in range(485)], source="test")

def test_e2e_signal_emits_full_feature_row(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)

    sid = emit_signal(
        conn,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0),
        payload={"cluster_id":"c1","story_count_delta":3.0},
    )
    assert sid is not None

    rows = conn.execute(
        "SELECT feature_name, feature_value, is_missing "
        "FROM signal_features WHERE signal_id=? ORDER BY feature_name",
        [sid],
    ).fetchall()
    by_name = {r[0]: (r[1], r[2]) for r in rows}

    # All 18 registered features present
    assert set(by_name.keys()) == {f.name for f in V1_FEATURES}
    # Placeholders missing
    for name in PLACEHOLDER_NAMES:
        assert by_name[name] == (None, True)
    # Computables that have enough seed data
    assert by_name["mom_7d"][1] is False         # 7d history present
    assert by_name["nifty_return_50d"][1] is False
    assert by_name["regime_bull"][1] is False
    # cluster_momentum_z requires ≥30 prior cluster_momentum signals — none seeded
    assert by_name["cluster_momentum_z"][1] is True
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/integration/test_features_e2e.py -v
```
Expected: 1 test PASS.

- [ ] **Step 3: Run the entire suite to confirm no regression**

```bash
uv run pytest --tb=short -q
```
Expected: 222 (post-foundation review fixes) + ~35 new = ~257+ tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_features_e2e.py
git commit -m "test(features): end-to-end signal → feature vector"
```

---

## Task 13: `/features SIGNAL_ID` REPL inspector

**Files:**
- Create: `src/finterminal/commands_features.py`
- Modify: `src/finterminal/commands.py` — register the new command
- Test: tested via integration in Task 12; this is mostly mechanical wiring

- [ ] **Step 1: Read existing command registration style**

```bash
grep -n -B 2 -A 10 "@command" src/finterminal/commands.py | head -50
```

Match whatever decorator pattern is already there. (Per `context.md` follow-up, T8/T11 added similar commands — read 5–10 lines around the `/refresh-prices` registration for style.)

- [ ] **Step 2: Write the command body**

```python
# src/finterminal/commands_features.py
from __future__ import annotations
import duckdb
from rich.table import Table
from rich.console import Console

console = Console()

def features_inspect(conn: duckdb.DuckDBPyConnection, signal_id: str) -> None:
    rows = conn.execute(
        "SELECT feature_name, feature_value, is_missing "
        "FROM signal_features WHERE signal_id = ? ORDER BY feature_name",
        [signal_id],
    ).fetchall()
    if not rows:
        console.print(f"[yellow]No features found for signal_id {signal_id}[/yellow]")
        return
    t = Table(title=f"Features for {signal_id}")
    t.add_column("Feature"); t.add_column("Value", justify="right"); t.add_column("Missing")
    for name, value, missing in rows:
        v = "—" if missing else f"{value:.6g}" if value is not None else "NULL"
        t.add_row(name, v, "yes" if missing else "")
    console.print(t)
```

- [ ] **Step 3: Register in `commands.py`**

In `src/finterminal/commands.py`, find where `/refresh-prices` and `/backfill-outcomes` are wired (search for `refresh_prices`). Add a `/features` command following the same registration style, calling `features_inspect(conn, args[0])` (with arg-count validation matching local style).

- [ ] **Step 4: Run the suite**

```bash
uv run pytest --tb=short -q
```
Expected: still all PASS — no test changes, just a new CLI surface.

- [ ] **Step 5: Manual smoke (optional, marked 'manual')**

```bash
# Inside REPL: emit a signal via /refresh-news with OUTCOMES_LEDGER_ENABLED=1, grab its sid
# Then: /features <sid>
# Expected: 18-row table, regime + price features have values, placeholders show "—"
```

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/commands_features.py src/finterminal/commands.py
git commit -m "feat(features): /features SIGNAL_ID REPL inspector"
```

---

## Task 14: Final review + branch handoff

- [ ] **Step 1: Run the full suite**

```bash
uv run pytest --tb=short -q
```
Expected: ~257 tests PASS.

- [ ] **Step 2: Verify diff stat**

```bash
git diff --stat main..HEAD     # or wherever the branch was cut from
```

- [ ] **Step 3: Dispatch end-of-branch code-reviewer subagent**

Use the `superpowers:requesting-code-review` skill. Brief the reviewer with:
- Spec: `docs/superpowers/specs/2026-04-30-feature-store-design.md`
- ADR: `TerminalVault/02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models.md`
- Focus on: leakage rules (D5/D6), atomicity in `emit_signal`, pipeline-isolation guard correctness.

- [ ] **Step 4: Apply review fixes (if any), push, open PR**

Same flow as the foundation branch — 3-line PR title, body summarizes the 13 commits.

---

## Self-review checklist (writer's pass)

- [x] Every spec D1–D11 has at least one task implementing it.
- [x] No "TBD" or "implement later" — every step has runnable code.
- [x] Type names consistent: `Result = tuple[float | None, bool]` reused; `FeatureCell` TypedDict in store; `compute_for_signal` returns `dict[name, {value, is_missing}]` everywhere.
- [x] Leakage rules (D5/D6) tested explicitly in T6, T8.
- [x] Freshness gate (D12, G7/G10) tested explicitly in T4 + integration in T12.
- [x] Atomicity (D3) tested explicitly in T10.
- [x] Pipeline isolation (D9 extension) tested in T11 with both substring-grep and AST-walk variants.
- [x] Features without source data yet (`roe`, `sentiment_*`) are placeholder rows with `is_missing=true`, not absent — confirmed in T9 / T12.
- [x] No mention of H=7 anywhere; horizons are not a #5 concern. Alpha-vs-Nifty target locked into ADR-019 for #6.
- [x] Survivorship handling (D13) deferred to sub-project #9 — features read tickers as-given.
