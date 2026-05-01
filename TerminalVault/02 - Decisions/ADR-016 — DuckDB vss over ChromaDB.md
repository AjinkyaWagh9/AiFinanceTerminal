# ADR-016 — DuckDB vss over ChromaDB for vector storage

> Use DuckDB's bundled `vss` extension for embedding storage and cosine similarity queries instead of adding ChromaDB as a dependency.

**Status:** Accepted
**Date:** 2026-04-29
**Sprint:** B-2a — News & Trend pipeline
**Source:** Sprint B-2a design session; [[02 - Decisions/ADR-003 DuckDB + SQLite + ChromaDB local-only]] superseded for vector storage

---

## Context

Sprint B-2a requires:
- Storing 384-d sentence embeddings per news story (daily volume: hundreds of stories)
- Computing cosine similarity for cluster centroid matching (lineage)
- Querying by date, sector, and story ID alongside vector operations

The original storage ADR ([[02 - Decisions/ADR-003 DuckDB + SQLite + ChromaDB local-only]]) included ChromaDB as the vector store. At B-2a design time, DuckDB v1.1+ bundles the `vss` extension natively, which covers the required vector operations without a separate process or dependency.

---

## Decision

- Use DuckDB `vss` extension (`LOAD vss;` per connection) for all embedding storage and vector search
- Store embeddings as `FLOAT[384]` columns in `news_stories` and `news_clusters` tables
- Use `array_cosine_similarity(a, b)` for centroid matching in lineage queries
- ChromaDB is NOT added as a dependency for Sprint B-2a

---

## Rationale

| Factor | DuckDB vss | ChromaDB |
|---|---|---|
| Extra dependency | None — bundled since v1.1 | New pip dep + optional native libs |
| Process model | In-process (same DuckDB connection) | Separate process or embedded mode |
| Query join support | Native SQL joins with vector ops | No SQL join; separate API call |
| Date/sector filtering | Single SQL query | Metadata filter API (separate) |
| Operational complexity | Zero — no new infra | Client + server or embedded setup |
| Dimensionality (384-d) | Supported | Supported |
| Production-scale ANN | IVFFlat index (vss) | HNSW — better at very large scale |
| Alignment with existing stack | DuckDB already in use | New component |

At B-2a daily volumes (hundreds to low thousands of stories), exact cosine search is fast enough. IVFFlat ANN index available in vss if needed at larger scale.

---

## Consequences

### Positive
- Zero new infrastructure — DuckDB connection already established in `duckdb_store.py`
- Vector ops and relational filters (date, sector) in a single SQL query
- `FLOAT[384]` column is stored, compressed, and queried with the rest of the row — no separate lookup
- `array_cosine_similarity` available without extra libraries

### Negative / risks
- `vss` is a DuckDB extension; API could change across DuckDB versions — pin DuckDB version in `pyproject.toml`
- Not optimal for approximate nearest-neighbour at millions of vectors — acceptable for daily news volumes; revisit if archive grows beyond ~500k stories
- ChromaDB's HNSW offers better recall at very large scale; not needed at current volumes

### What this changes in ADR-003
- [[02 - Decisions/ADR-003 DuckDB + SQLite + ChromaDB local-only]]: ChromaDB role for news embeddings is taken over by DuckDB vss. ChromaDB may still be added in a later sprint for other use cases (e.g. document Q&A).

---

## Alternatives Considered and Rejected

| Alternative | Why rejected |
|---|---|
| ChromaDB embedded mode | Extra dependency; separate API for vector queries vs SQL for metadata; no join support |
| ChromaDB server mode | Adds server process; contradicts local-first design principle |
| SQLite + numpy cosine in Python | SQLite cannot store FLOAT[] natively; Python-side cosine loop does not scale even to moderate volumes |
| pgvector (PostgreSQL) | Requires PostgreSQL server; violates local-first / no-server constraint |
| FAISS + SQLite | Two separate stores (FAISS for vectors, SQLite for metadata); join requires Python bridge; operational overhead |

---

## Implementation Notes

- `LOAD vss;` added to `duckdb_store.py` connection setup — fires on every connection open
- Migration `003_news_pipeline.sql` creates tables with `FLOAT[384]` embedding columns
- `news_store.py` uses `array_cosine_similarity` in lineage queries (centroid ≥ 0.70 threshold)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`; model cached in `./data/models/`

---

## Cross-Links

- Supersedes (partially): [[02 - Decisions/ADR-003 DuckDB + SQLite + ChromaDB local-only]] (ChromaDB for news vectors)
- Code map: [[04 - Code Map/data — news_store]] · [[04 - Code Map/news — pipeline]]
- Build log: [[05 - Build Log/2026-04-29 — Sprint B-2a News Trend]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]] (B-2a)
