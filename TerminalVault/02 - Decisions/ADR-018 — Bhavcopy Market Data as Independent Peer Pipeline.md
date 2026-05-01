# ADR-018 — Bhavcopy Market Data as Independent Peer Pipeline

> The NSE Bhavcopy ingestion pipeline (`market_data/`) is an independent upstream module that MUST NOT import from `outcomes/` or `news/`. It merges with other pipelines only inside the analytics layer.

**Status:** Accepted
**Date:** 2026-04-29
**Source:** Sub-project #1 design session; [[05 - Build Log/2026-04-29 — Plan Reshape & Sub-Project 1 Spec]]
**Drivers:** Need official EOD price truth for outcomes resolution; independence required so each pipeline can fail, evolve, and be tested in isolation.

---

## Context

Sub-project #1 introduces `market_data/` as a second upstream data pipeline alongside the existing `news/` pipeline. Both feed into the `outcomes/` analytics layer. The critical design question: should these pipelines know about each other?

The answer is no — for the same reasons a data warehouse separates ingestion from transformation.

---

## Decision

| Rule | Enforcement |
|---|---|
| `market_data/` MUST NOT import from `outcomes/` | Test that greps import lines in all `market_data/` files; fails CI if `outcomes` appears |
| `market_data/` MUST NOT import from `news/` | Same grep test |
| `outcomes/` MAY import from `market_data/` | Specifically: `store.last_close_on_or_before`, `macro.nifty_pct_50d` |
| `news/cluster.py` calls `outcomes.ledger.emit_signal` only via try/except behind `OUTCOMES_LEDGER_ENABLED` | Fail-safe wrapper; emit failure never breaks `/refresh-news` |

### What `market_data/` owns

| Module | Responsibility |
|---|---|
| `nse_bhavcopy.py` | Download + parse NSE equity daily zip → OHLCV rows (~2000 tickers/day) |
| `nse_indices.py` | Parse `ind_close_all_DDMMYYYY.csv` → `_NIFTY50` close (equity zip excludes index) |
| `normalize.py` | NSE symbol → internal ticker map (reuses `data/india/nse_universe`) |
| `calendar.py` | NSE holiday detection — skip futile fetches |
| `store.py` | Upsert `prices_eod`; `last_close_on_or_before(ticker, date)` helper |
| `ingestion.py` | Orchestrator: walk missing date window, call sources, write `ingestion_log`, retry 429 |
| `macro.py` | `nifty_pct_50d(date)`, `india_vix_close(date)` — read-only views of `prices_eod` |
| `_http.py` | NSE-friendly UA + cookie + 1 s rate-limit + single retry on 429 |

REPL command: `/refresh-prices`

### Source details

| Source | URL pattern | Content |
|---|---|---|
| `nse_bhavcopy` | `nsearchives.nseindia.com/content/historical/EQUITIES/YYYY/MMM/cmDDMMMYYYYbhav.csv.zip` | ~2000 equity tickers, OHLCV |
| `nse_indices` | `nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv` | All NSE indices (incl. NIFTY 50) |

Both patterns have drifted historically — URL builders centralized in `ingestion.py`.

---

## Rationale

| Factor | Independent pipelines | Coupled pipelines |
|---|---|---|
| Failure isolation | Price ingest failure doesn't break news refresh or outcome resolution | One failure cascades |
| Test clarity | `market_data/` tests require zero `outcomes/` fixtures | Tests must mock two systems together |
| Contributor surface | Future BSE or Brent oil source added to `market_data/` only | Requires touching analytics layer |
| Cadence mismatch | Bhavcopy: EOD batch. News: continuous. | Forces artificial synchronisation |
| Audit trail | `ingestion_log` owned entirely by `market_data/`; clean provenance | Mixed ownership |

---

## Consequences

### Positive
- `market_data/` can be developed, tested, deployed, and replaced without touching `outcomes/` or `news/`
- Adding a new price source (BSE, US market data in Phase 3) requires only a new file in `market_data/`
- `ingestion_log` gives a clean audit trail: "did yesterday's prices load?" without scanning `prices_eod`

### Negative / risks
- `normalize.py` reuses `data/india/nse_universe.py` — this is the one permitted cross-import from `data/india/`; not a violation
- NSE requires browser-like User-Agent and may set cookies — encapsulated in `_http.py`; monitor for NSE-side changes

### What this does NOT change
- `outcomes/` is still allowed to read `prices_eod` via `market_data/store` and `market_data/macro` — these are read-only helpers, not a circular dependency
- ADR-001 (Indian markets first) unchanged — US price data deferred to Phase 3

---

## Alternatives Considered and Rejected

| Alternative | Why rejected |
|---|---|
| Single `data/` module for all ingest | Couples news pipeline cadence to EOD batch cadence; one failure stops both |
| Reuse real-time `nse_quote.py` as price truth | Live quote ≠ official EOD; subject to rate-limits, doesn't give historical window |
| Have `outcomes/` own the bhavcopy fetcher | Violates separation of concerns — outcomes layer should read prices, not fetch them |
| Store prices in SQLite (not DuckDB) | Outcomes join across `signals` + `prices_eod` must be in same DB; both belong in DuckDB |

---

## Open Questions

- Q-ADR-018-1: NSE bhavcopy URL patterns have changed before. At implementation time verify paths and document the last verified date in `market_data/ingestion.py`.
- Q-ADR-018-2: Does NSE provide an official holiday calendar via API, or must we maintain a static list? (Calendar.py must answer this before first failing test.)

---

## Cross-Links

- Triggered by: [[05 - Build Log/2026-04-29 — Plan Reshape & Sub-Project 1 Spec]]
- Partner ADR: [[02 - Decisions/ADR-017 — Outcomes Ledger as the System's Moat]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]] (sub-project #1)
- Related: [[02 - Decisions/ADR-003 DuckDB + SQLite + ChromaDB local-only]] — `prices_eod` lives in DuckDB (same DB as `news_*` tables), consistent with this ADR
