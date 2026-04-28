# Storage

> Back to [[Index]] | See also [[ADR-003 DuckDB + SQLite + ChromaDB local-only]] · [[System Diagram]] · [[data — OpenBB + DuckDB]]

---

## Three-tier design

| Tier | Engine | Responsibility | Why |
|---|---|---|---|
| Analytics | DuckDB | OHLCV, fundamentals, news, LLM cost logs, all Phase 2.5 tables | Columnar engine; fast time-series aggregates; ASOF JOIN |
| App state | SQLite | Watchlist, agent memory, run logs | Better concurrent single-row writes; familiar tooling |
| Embeddings | ChromaDB | Semantic news search, CEO statement clustering | Embedded vector DB; no separate server |

All three are embedded — zero daemon processes.

---

## Phase-1 DuckDB schema

Migration file: `src/finterminal/data/migrations/001_initial.sql`

| Table | Key columns | Purpose |
|---|---|---|
| `quotes` | ticker, as_of, last_price, change_pct, volume, market_cap | Live + historical price snapshots |
| `fundamentals` | ticker, as_of, pe_ttm, eps_ttm, roe, roce, debt_to_equity, revenue_ttm, net_income_ttm | Financial metrics per tick |
| `news` | id, ticker, source, headline, url, published_at, body | Article store |
| `watchlist` | ticker, added_at, notes | User watchlist (SQLite in production; DuckDB for now) |
| `analyses` | id, ticker, created_at, bull_case, bear_case, confidence, sources_json | Saved /analyze outputs |
| `llm_calls` | ts, agent, model, tokens_in, tokens_out, cost_usd, latency_ms, cache_hit | Per-call cost tracking |

---

## Important gotcha: `asof` is a reserved keyword

DuckDB uses `asof` in `ASOF JOIN` syntax. The Phase-1 schema draft originally named the timestamp column `asof`. This was renamed to `as_of` before the first migration was committed.

**Rule:** Never use `asof` as a column name anywhere in DuckDB schemas. Use `as_of`.

Referenced in [CLAUDE.md workspace conventions](../docs/CLAUDE.md).

---

## Phase-2.5 schema additions (14 new tables)

Defined in PLAN.md §6.5.4. Migrations will live in `src/finterminal/data/migrations/002_phase25.sql` (not yet created).

Categories:
- **Transcripts:** `transcripts`, `transcript_sections`, `transcript_topics`, `transcript_guidance`
- **Consensus:** `consensus_snapshots`, `earnings_actuals`
- **Ownership:** `ownership_snapshots`, `sast_filings`, `bulk_block_deals`, `mf_holdings`, `fii_flows_daily`
- **Quality:** `quality_scores`
- **Comps:** `peer_groups`, `valuation_snapshots`
- **Macro / Calendar:** `macro_series`, `sector_macro_betas`, `events`

---

## DuckDB path configuration

```
DUCKDB_PATH=./data/finterminal.duckdb    # from .env
```

`duckdb_store.get_conn()` runs migrations on first open. See [[data — OpenBB + DuckDB]] for the store API.

---

## ChromaDB (Phase 2+)

Not yet initialized in Phase 1. Will be used by:
- News & Trend agent — embed headlines → semantic clustering
- CEO Tracker — embed transcript segments → topic similarity across leaders
- Transcript agent — embed concall sections → cross-quarter search
