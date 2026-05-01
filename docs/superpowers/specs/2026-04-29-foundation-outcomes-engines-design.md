# Foundation: Outcomes Ledger + Engine Taxonomy

**Date:** 2026-04-29
**Status:** Spec — pending user review
**Sub-project:** #1 of 4 (reshape after input.md critique)
**Predecessors:** Sprint B-2a (news + trend pipeline shipped)
**Successors blocked by this:** B-2b reshape, Quality Engine v1 (mgmt_claims), Reflexivity v1 (sentiment)

---

## 1. Why this exists

Input.md's only correct, load-bearing critique: the system has no way to prove it makes money. Every other recommendation (cut features, rename, focus) is downstream of that gap.

This sub-project closes that gap by adding **two complementary upstream pipelines** plus the analytics ledger that merges them downstream:

- **RSS / news pipeline** *(already shipped, B-2a)* — narrative discovery layer. Tells us **what** happened.
- **NSE Bhavcopy daily zip pipeline** *(new, this sub-project)* — official end-of-day market truth layer. Tells us **whether the market cared**.
- **Outcomes ledger** *(new, this sub-project)* — analytics layer. Every signal emitted by the news pipeline gets resolved against the price truth from the bhavcopy pipeline.

**Architectural principle (D9 below):** The two upstream pipelines remain independent. They never share schema, never depend on each other at runtime, and can be operated, tested, and reasoned about in isolation. They merge only inside the outcomes ledger.

```
RSS feeds   ─►  news/ pipeline       ─►  cluster signals  ┐
                                                          ├─►  outcomes ledger  ─►  predictive_power, alpha vs Nifty, ...
NSE archives ─►  market_data/ pipeline ─►  prices_eod    ┘
```

Concretely this sub-project ships:
1. A new market-data ingestion pipeline that pulls official NSE bhavcopy daily zips, parses OHLCV, normalizes tickers, maintains a historical price store, and logs every fetch attempt.
2. A `signals → signal_outcomes` ledger that resolves every signal against forward returns over 1 / 7 / 30 / 90 / 365 calendar days, vs Nifty 50.
3. A regime snapshot at every emission so predictive power can later be conditioned on macro regime.
4. The first wiring: `cluster_momentum` signals from the existing news pipeline emit into the ledger; price ingest resolves them.

No new analysis ships. It is pure measurement plumbing — the prerequisite for sub-projects #2–4.

## 2. Scope

### In scope

**Pipeline A — NSE Bhavcopy Daily Ingestion (Market Data Layer)**
- `market_data/` Python module: bhavcopy zip download, unzip + parse, NSE indices CSV ingest, ticker normalization, OHLCV upsert into `prices_eod`, holiday/weekend handling, missing-file detection + retry, ingestion logging
- New REPL command: `/refresh-prices`
- **Independently runnable and testable.** No runtime dependency on the outcomes module or news pipeline. A future contributor could swap the source (e.g., add BSE) without touching the analytics layer.

**Pipeline B — Outcomes Ledger + Engine Taxonomy (Analytics Layer)**
- DuckDB migration `004_outcomes_ledger.sql` — `signals`, `signal_outcomes`, `prices_eod`, `ingestion_log`
- `outcomes/` Python module: schema enums, `emit_signal`, backfill, queries
- New REPL command: `/backfill-outcomes`
- 5-engine Python enum + `SIGNAL_REGISTRY` mapping signal_type → engine
- `engines/base.py` placeholder; per-engine modules deferred until ≥2 signal types per engine

**Cross-pipeline wiring (the only intentional coupling)**
- `news/cluster.py` calls `outcomes.ledger.emit_signal()` after each `/refresh-news` (fail-safe wrapper, behind `OUTCOMES_LEDGER_ENABLED` flag)
- `outcomes.backfill` reads `prices_eod` (owned by the market-data pipeline) to resolve outcomes
- One-shot `outcomes/backfill_historical.py`: replays existing `news_clusters` rows (cutoff `first_seen ≤ today − 7d`) into the ledger

### Out of scope (each becomes its own sub-project)
- Sentiment module (sub-project #4)
- Management claims ledger (sub-project #3)
- `/analyze SYMBOL` 5-engine card reshape (sub-project #2)
- LLM generation of `why` text — emitter passes raw string for now
- INR / Brent / India 10y yield ingestion — regime cols stay NULL until a follow-up
- Predictive-power dashboards or visualizations
- Trading-day calendars; horizons stay calendar-day based

## 3. Architectural decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | Per-signal granularity (one row per emission) | Q1A. Per-ticker-snapshot and per-decision can be derived from this; reverse cannot. Lets us answer "which signal type predicts?" |
| D2 | Hybrid schema: `signals` flat + `signal_outcomes` long | Per-horizon NULL bloat in a wide table; full normalization adds joins for no win. Hybrid keeps signal metadata local but expands horizons row-wise. |
| D3 | Engine taxonomy lives in Python, not as DB tables | Matches existing house style (003 has no metadata tables). Static enum, version-controlled. |
| D4 | Stub `signal_outcomes` rows (one per horizon) inserted at emit time | Makes "find unresolved" cheap (`WHERE resolved_at IS NULL`); cost is 5 extra rows per signal — trivial. |
| D5 | Sentinel ticker convention: `_MACRO`, `_NIFTY50` | Keeps `ticker NOT NULL` and the (signal_type, ticker, ts_emitted) uniqueness constraint usable. |
| D6 | `_MACRO` ticker outcomes use Nifty forward return as proxy | A regime_shift signal's "did it work?" answer is whether Nifty moved as predicted. |
| D7 | Calendar-day horizons, not trading-day | Avoids holiday-calendar dependency. Resolution finds last close on or before target date. |
| D8 | Wiring `cluster.py → emit_signal` is fail-safe | Try/except around the call; emit failures must never break `/refresh-news`. Behind config flag `OUTCOMES_LEDGER_ENABLED`. |
| D9 | Bhavcopy ingestion and news ingestion are separate upstream pipelines | Different purposes (price truth vs narrative discovery), different cadences (EOD vs continuous), different failure modes, different schemas. They merge only inside the outcomes ledger so each can evolve, fail, and be tested independently. |
| D10 | Store full OHLCV in `prices_eod`, not just close | Future signals (volume spike, gap-up, range expansion, ATR-based risk triggers) need O/H/L/V. Marginal storage cost; avoids a v2 schema migration. The outcomes ledger uses `close` only in v1. |
| D11 | Every fetch attempt is logged in `ingestion_log` | Cheap audit trail. Lets us answer "did we have a price ingest yesterday?" without scanning `prices_eod`, and captures retries / parse failures / holiday skips. |

## 4. Schema (`004_outcomes_ledger.sql`)

```sql
-- Sub-project #1: outcomes ledger + price store.
-- Conventions match 003: VARCHAR, IF NOT EXISTS, naive TIMESTAMP (IST), no FK constraints.

CREATE TABLE IF NOT EXISTS signals (
    signal_id     VARCHAR PRIMARY KEY,           -- uuid4() str
    signal_type   VARCHAR NOT NULL,              -- enum value, validated app-side
    engine        VARCHAR NOT NULL,              -- denormalized from SIGNAL_REGISTRY
    ticker        VARCHAR NOT NULL,              -- '_MACRO' / '_NIFTY50' for non-equity signals
    ts_emitted    TIMESTAMP NOT NULL,            -- IST naive
    payload       JSON,                          -- signal-specific fields
    confidence    DOUBLE,                        -- 0..1, NULL allowed
    why           VARCHAR,                       -- short human-readable reason
    source_ref    VARCHAR,                       -- e.g. cluster_id, claim_id
    -- Regime snapshot at emission time (raw values, not bucketed):
    regime_nifty_close       DOUBLE,
    regime_nifty_pct_50d     DOUBLE,
    regime_india_vix         DOUBLE,
    regime_inr_usd           DOUBLE,             -- NULL in v1 (no source yet)
    regime_brent_usd         DOUBLE,             -- NULL in v1
    regime_india_10y_yield   DOUBLE,             -- NULL in v1
    UNIQUE (signal_type, ticker, ts_emitted)
);

CREATE INDEX IF NOT EXISTS signals_ticker_ts_idx ON signals(ticker, ts_emitted);
CREATE INDEX IF NOT EXISTS signals_engine_ts_idx ON signals(engine, ts_emitted);
CREATE INDEX IF NOT EXISTS signals_type_ts_idx   ON signals(signal_type, ts_emitted);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_id        VARCHAR NOT NULL,
    horizon_days     INTEGER NOT NULL,           -- 1, 7, 30, 90, 365
    ret_pct          DOUBLE,                     -- (close[t+N] / close[t]) - 1
    ret_pct_vs_nifty DOUBLE,                     -- ret_pct - nifty_ret_same_window
    resolved_at      TIMESTAMP,                  -- IST naive; NULL = unresolved
    PRIMARY KEY (signal_id, horizon_days)
);

CREATE INDEX IF NOT EXISTS signal_outcomes_unresolved_idx
    ON signal_outcomes(resolved_at);             -- cheap scan for backfill

CREATE TABLE IF NOT EXISTS prices_eod (
    trade_date  DATE    NOT NULL,
    ticker      VARCHAR NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE  NOT NULL,                -- only field outcomes ledger uses in v1
    volume      BIGINT,
    source      VARCHAR NOT NULL,                -- 'nse_bhavcopy' | 'nse_indices'
    created_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS prices_eod_date_idx ON prices_eod(trade_date);

-- One row per fetch attempt (any source, any date). Owned by market_data/.
CREATE TABLE IF NOT EXISTS ingestion_log (
    id            VARCHAR PRIMARY KEY,           -- uuid4()
    source        VARCHAR NOT NULL,              -- 'nse_bhavcopy' | 'nse_indices'
    target_date   DATE    NOT NULL,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    status        VARCHAR NOT NULL,              -- 'ok' | 'skipped_holiday' | 'http_error' | 'parse_error' | 'retrying'
    rows_written  INTEGER,
    http_code     INTEGER,
    note          VARCHAR
);

CREATE INDEX IF NOT EXISTS ingestion_log_source_date_idx
    ON ingestion_log(source, target_date);
```

## 5. Module layout

```
src/finterminal/
  outcomes/
    __init__.py
    schema.py          # Engine enum, SignalType enum, SIGNAL_REGISTRY, REGIME_FIELDS
    ledger.py          # emit_signal() — writes signals + 5 outcome stubs; idempotent
    backfill.py        # resolve_pending() — fills mature horizons
    backfill_historical.py  # one-shot replay of existing news_clusters
    queries.py         # predictive_power(signal_type, horizon) etc.
    engines/
      __init__.py
      base.py          # Engine base class — empty interface placeholder.
                       # Per-engine modules (mispricing.py, quality.py, ...) added
                       # only when ≥2 signal types per engine exist (Q6C).
  market_data/                        # Pipeline A — independent, owns prices_eod + ingestion_log
    __init__.py
    nse_bhavcopy.py    # daily equity zip: download → unzip → parse OHLCV
    nse_indices.py     # ind_close_all_DDMMYYYY.csv → populates _NIFTY50 row
    normalize.py       # NSE symbol → internal ticker map (reuses news/data/india/nse_universe)
    calendar.py        # NSE trading-holiday detection (avoid futile fetches)
    store.py           # upsert prices_eod; last_close_on_or_before(ticker, date) helper
    ingestion.py       # orchestrator: walk missing dates, call sources, write ingestion_log, retry transient errors
    macro.py           # nifty_pct_50d(date), india_vix_close(date) — reads prices_eod
    _http.py           # NSE-friendly UA + cookie + 1s rate-limit + single retry on 429
  data/migrations/
    004_outcomes_ledger.sql
```

### `schema.py` (key constants)

```python
class Engine(str, Enum):
    MISPRICING   = "mispricing"
    QUALITY      = "quality"
    REGIME       = "regime"
    REFLEXIVITY  = "reflexivity"
    RISK         = "risk"

class SignalType(str, Enum):
    CLUSTER_MOMENTUM      = "cluster_momentum"
    DIVERGENCE            = "divergence"            # added in sub-project #4
    SENTIMENT_DELTA       = "sentiment_delta"       # added in sub-project #4
    CLAIM_RECONCILIATION  = "claim_reconciliation"  # added in sub-project #3
    REGIME_SHIFT          = "regime_shift"          # added later
    RISK_TRIGGER          = "risk_trigger"          # added later

SIGNAL_REGISTRY: dict[SignalType, Engine] = {
    SignalType.CLUSTER_MOMENTUM:     Engine.REFLEXIVITY,
    SignalType.DIVERGENCE:           Engine.MISPRICING,
    SignalType.SENTIMENT_DELTA:      Engine.REFLEXIVITY,
    SignalType.CLAIM_RECONCILIATION: Engine.QUALITY,
    SignalType.REGIME_SHIFT:         Engine.REGIME,
    SignalType.RISK_TRIGGER:         Engine.RISK,
}

HORIZONS_DAYS: tuple[int, ...] = (1, 7, 30, 90, 365)

MACRO_TICKER  = "_MACRO"
NIFTY_TICKER  = "_NIFTY50"
```

## 6. Data flow

### 6.1 Emission (called from `news/cluster.py` after Q11C wiring)

```
cluster pipeline finishes
  └─> for each cluster with story_count_delta != 0:
        ledger.emit_signal(
            signal_type='cluster_momentum',
            ticker=cluster.top_tickers[0] or MACRO_TICKER,
            ts_emitted=now_ist(),
            payload={'cluster_id': cluster.id, 'story_count_delta': delta,
                     'story_count': cluster.story_count},
            confidence=min(1.0, abs(delta) / 10.0),
            why=f"cluster {cluster.id} {'grew' if delta>0 else 'shrank'} {abs(delta)} stories d/d",
            source_ref=cluster.id,
        )
```

`emit_signal` internally:
1. Validate `signal_type` against `SignalType` enum; look up `engine` from `SIGNAL_REGISTRY`.
2. Snapshot regime cols from `market_data/macro.py` helpers (last available close — T-1 if before close).
3. `INSERT INTO signals ... ON CONFLICT (signal_type, ticker, ts_emitted) DO NOTHING`.
4. If signal was newly inserted: `INSERT INTO signal_outcomes (signal_id, horizon_days)` for each horizon (5 rows, NULL ret).
5. Return `signal_id` (or None if dedup'd).

Wrapped at the call site in cluster.py:

```python
if config.OUTCOMES_LEDGER_ENABLED:
    try:
        outcomes.ledger.emit_signal(...)
    except Exception as e:
        log.warning("emit_signal failed (non-fatal): %s", e)
```

### 6.2 Price refresh (`/refresh-prices`) — owned by `market_data/`

Independent of the outcomes module. Could be invoked solo (e.g., from a future cron) and would still produce a complete `prices_eod` table.

```
window = [last_ingested + 1 .. yesterday]
for date in window:
    if calendar.is_holiday(date) or date.weekday() in (SAT, SUN):
        ingestion_log: status='skipped_holiday'; continue
    for source in ['nse_bhavcopy', 'nse_indices']:
        log_id = ingestion_log.start(source, date)
        try:
            blob = _http.fetch(url_for(source, date))      # UA + cookie + 1s rate-limit
            rows = parse(blob)                             # OHLCV per ticker (or index close)
            normalized = normalize.apply(rows)             # NSE symbol → internal ticker
            store.upsert_prices_eod(normalized, source=source)   # ON CONFLICT DO NOTHING
            ingestion_log.finish(log_id, status='ok', rows_written=len(rows))
        except Http404:
            ingestion_log.finish(log_id, status='skipped_holiday', http_code=404)
        except (Http429, ConnectionError):
            backoff(5s); retry once
            on 2nd failure → ingestion_log.finish(log_id, status='http_error')
        except ParseError as e:
            ingestion_log.finish(log_id, status='parse_error', note=str(e))
```

`nse_bhavcopy` populates equity rows (~2000 tickers/day OHLCV). `nse_indices` separately populates `_NIFTY50` (and any future indices) — bhavcopy equity zip does NOT include the index itself.

### 6.3 Outcome resolution (`/backfill-outcomes`, also nightly cron later)

```sql
-- pseudo:
SELECT s.signal_id, s.ticker, s.ts_emitted, o.horizon_days
FROM signals s JOIN signal_outcomes o USING (signal_id)
WHERE o.resolved_at IS NULL
  AND DATE(s.ts_emitted) + INTERVAL (o.horizon_days) DAY <= CURRENT_DATE;

-- for each row:
--   close_t  = last close <= DATE(ts_emitted) for ticker (use _NIFTY50 if ticker == _MACRO)
--   close_th = last close <= DATE(ts_emitted) + horizon_days for that ticker
--   nifty_t  = last close <= DATE(ts_emitted) for _NIFTY50
--   nifty_th = last close <= DATE(ts_emitted) + horizon_days for _NIFTY50
--   ret_pct          = close_th / close_t - 1
--   ret_pct_vs_nifty = ret_pct - (nifty_th / nifty_t - 1)
--   UPDATE signal_outcomes SET ret_pct, ret_pct_vs_nifty, resolved_at = now();
```

If either close lookup returns nothing (price gap), leave row unresolved; retry next run.

### 6.4 Queries

```python
queries.predictive_power(signal_type='cluster_momentum', horizon=30)
# returns: {n: int, mean_ret: float, mean_alpha: float, ic: float|None}

queries.engine_summary(engine='reflexivity', horizon=30)
# returns aggregate across all signal_types in that engine
```

### 6.5 Historical backfill (one-shot)

`outcomes/backfill_historical.py` scans existing `news_clusters` rows where `first_seen <= today - 7 days` (so the 1d and 7d horizons can resolve immediately once `/refresh-prices` has run), calls `emit_signal` with `ts_emitted = first_seen` for each, then runs normal resolution. Idempotent because of the unique constraint. Older clusters resolve more horizons; newest clusters skipped on first run and picked up by the live wiring instead.

## 7. Error handling

| Case | Behavior |
|---|---|
| Duplicate emission (composite key clash) | `ON CONFLICT DO NOTHING`; `emit_signal` returns None |
| Unknown `signal_type` passed to `emit_signal` | Raise `ValueError` — caller bug, must surface |
| Missing close at emission time (price gap) | Regime cols stored NULL; signal still logged |
| Missing close at resolution time | Leave outcome row NULL, retry next backfill |
| NSE bhavcopy 404 (holiday/weekend/network) | `ingestion_log.status='skipped_holiday'`; continue window |
| NSE rate-limit (HTTP 429) or transient ConnectionError | Backoff 5s, retry once. On 2nd failure → `ingestion_log.status='http_error'`; window continues |
| NSE returns malformed zip / CSV | `ingestion_log.status='parse_error'` with `note=str(e)`; continue window |
| Symbol in bhavcopy that doesn't map to internal ticker | Insert with raw NSE symbol as ticker; `normalize.py` logs unmapped symbols for review |
| `emit_signal` exception inside `cluster.py` wiring | Caught + logged; `/refresh-news` continues |
| `OUTCOMES_LEDGER_ENABLED=False` | `emit_signal` is never called from cluster.py |

## 8. Testing

### Pipeline A — `market_data/` (independently testable, no `outcomes/` import allowed in these tests)
- Bhavcopy parser: fixture zip with 3 tickers → 3 OHLCV rows with correct types
- Indices parser: fixture `ind_close_all` CSV → `_NIFTY50` row with correct close
- Ticker normalization: known symbol maps; unknown symbol passes through with warn log
- Holiday skip: known holiday date returns `skipped_holiday` without an HTTP call
- 404 path: mock `_http.fetch` raising → ingestion_log `skipped_holiday`, no rows written
- 429 path: mock raising 429 once then ok → backoff invoked, eventual `status='ok'`
- Parse error path: corrupt fixture → `status='parse_error'`, no rows written
- Idempotent upsert: re-running same date is a no-op on `prices_eod`
- Window walk: given `last_ingested = D-5`, calls fetch for 4 weekdays, skips 2 weekend days

### Pipeline B — `outcomes/`
- Migration applies cleanly on a fresh DuckDB
- `emit_signal` writes 1 signal + 5 outcome stubs; second call with same composite key is idempotent
- `emit_signal` rejects unknown signal_type
- `resolve_pending` math: given fixture price series in `prices_eod`, ret_pct + ret_pct_vs_nifty correct to 1e-9
- Resolution skips rows where prices missing on either endpoint
- `_MACRO` ticker resolves against `_NIFTY50` close series
- Calendar-day horizon resolution finds last close ≤ target (weekend rollback)
- `OUTCOMES_LEDGER_ENABLED=False` → cluster.py never calls emit_signal (verify via mock)

### Integration (both pipelines together)
- Fixture bhavcopy zip + indices CSV → `/refresh-prices` populates `prices_eod` + `ingestion_log`
- Replay 5 fixture clusters via `backfill_historical` → outcomes resolve for matured horizons against the fixture prices
- `predictive_power('cluster_momentum', 7)` returns expected shape on fixtures (n ≥ 1, sane mean_alpha)
- An `emit_signal` raised exception in cluster.py wiring does NOT fail `/refresh-news` (verify via injected raise)

### Regression guard
- All 173 existing tests still pass

## 9. Caveats & follow-ups

1. **NSE URL drift.** Current observed pattern is `nsearchives.nseindia.com/content/historical/EQUITIES/YYYY/MMM/cmDDMMMYYYYbhav.csv.zip` and `nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv`. NSE has changed paths historically; verify at implementation time and centralize URL builders so a future fix is one file.
2. **User-Agent + cookies.** NSE rejects requests without browser-like UA; some endpoints set cookies on first hit. Encapsulate in `market_data/_http.py`.
3. **Regime cols partially NULL in v1.** INR / Brent / 10y stay NULL until a follow-up. Schema is forward-compatible.
4. **Confidence semantics deferred per signal_type.** Sub-project's only definition: `cluster_momentum` confidence = `min(1.0, abs(delta)/10.0)`. Other types define their own when shipped.
5. **No predictive-power UI yet.** `/trends` etc. unchanged. A read command lands in sub-project #2.
6. **Engine class stubs are intentionally empty** to avoid input.md's "too many agents / vanity dashboards" trap. They become real when ≥2 signal types per engine exist.
7. **DuckDB FK & ON DELETE CASCADE not used** to match 003 house style. Cascade on delete is enforced app-side (rare path).

## 10. Acceptance criteria

### Pipeline A — market data layer (independently)
- `004_outcomes_ledger.sql` applies; `prices_eod` and `ingestion_log` tables present and empty.
- `/refresh-prices` populates `prices_eod` for the last 30 trading days for the full NSE equity universe (OHLCV) plus `_NIFTY50`.
- `ingestion_log` contains one row per `(source, target_date)` attempt with terminal status (`ok` / `skipped_holiday` / `http_error` / `parse_error`).
- Re-running `/refresh-prices` on the same window is a no-op for `prices_eod` (idempotent).
- `market_data/` test suite passes with **no `outcomes/` import** in any test file (proves the pipeline is independent).

### Pipeline B — outcomes ledger (atop A)
- `from finterminal.outcomes.schema import Engine, SignalType, SIGNAL_REGISTRY` works; `len(SIGNAL_REGISTRY) == 6`.
- After one `/refresh-news` with `OUTCOMES_LEDGER_ENABLED=True`: `signals` has ≥1 `cluster_momentum` row per cluster with momentum, each with 5 stub `signal_outcomes` rows.
- `backfill_historical.py` emits ≥1 signal for each existing `news_clusters` row where `first_seen ≤ today − 7d`.
- `/backfill-outcomes` resolves all 1d / 7d horizons that have prices on both endpoints in `prices_eod`.
- `queries.predictive_power('cluster_momentum', 7)` returns a dict with `n ≥ 1` and finite `mean_ret` / `mean_alpha`.

### Cross-cutting
- An exception injected into `outcomes.ledger.emit_signal` does not break `/refresh-news`.
- All 173 existing tests still pass; new module coverage ≥ 80%.
