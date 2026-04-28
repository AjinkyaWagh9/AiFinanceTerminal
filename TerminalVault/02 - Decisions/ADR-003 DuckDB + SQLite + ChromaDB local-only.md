# ADR-003 — DuckDB + SQLite + ChromaDB, Local-Only

> Back to [[Index]] | See also [[01 - Architecture/Storage]] · [[01 - Architecture/System Diagram]]

**Status:** Accepted
**Date:** 2026-04-27
**Source:** [PLAN.md §4.8, §10](../docs/PLAN.md)

---

## Context

The project requires three categories of data persistence:

1. **Analytical queries** — time-series OHLCV, fundamentals, news, LLM cost logs.
2. **App state** — watchlist, agent memory, run logs.
3. **Vector embeddings** — semantic news search, CEO statement clustering.

The project is explicitly local-first (G4 in PLAN.md §2). A cloud database (Supabase, Neon, PlanetScale) was considered and rejected at the user's request.

---

## Decision

**Three-tier embedded storage, no servers:**
- **DuckDB** — analytics
- **SQLite** — app state
- **ChromaDB** — embeddings

---

## Decision matrix (from PLAN.md §4.8)

| Aspect | Weight | DuckDB | SQLite | Postgres (local) | Parquet |
|---|---:|---:|---:|---:|---:|
| Analytical queries | 5 | **5** | 2 | 4 | 4 |
| Embedded / zero-ops | 5 | **5** | 5 | 1 | 5 |
| Concurrent writes | 4 | 3 | **4** | 5 | 2 |
| Vector search | 3 | 3 | 2 | 4 | 1 |

**DuckDB wins for analytics** (columnar engine, ASOF JOIN, native OHLCV queries).  
**SQLite wins for app state** (concurrent writes, single-writer per table).

---

## Rationale

- All three are embedded — no daemon processes, no port management, no Docker required.
- DuckDB's columnar engine handles 5Y OHLCV queries 10–100× faster than SQLite for time-series aggregation.
- ChromaDB handles embedding creation + vector search with a simple Python API; no separate vector-DB server.
- Each tier has exactly one responsibility, keeping query patterns clean.

---

## Important gotcha

`asof` is a reserved keyword in DuckDB (used in `ASOF JOIN`). The column originally named `asof` in the Phase-1 schema was renamed to `as_of` before first migration. See [[01 - Architecture/Storage]] for details.

---

## Rejected options

| Option | Why rejected |
|---|---|
| Supabase (cloud Postgres) | Violates local-first privacy goal (G4); requires network for every query |
| Local Postgres | Requires daemon process; excessive for single-user terminal |
| Single DuckDB for everything | DuckDB's write concurrency is limited; SQLite is a better fit for app-state row ops |
| LanceDB instead of ChromaDB | Both work; defaulting to ChromaDB until volume forces an upgrade |

---

## Consequences

- Schema lives at `src/finterminal/data/migrations/001_initial.sql` and future `00X_*.sql` files.
- Phase 2.5 adds ~14 new tables (see [[02 - Decisions/ADR-008 Phase 2.5 Analyst-Grade Layer]]).
- DuckDB path configured via `DUCKDB_PATH` env var.
