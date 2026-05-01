# 2026-04-29 — Sprint B-2a: News & Trend Pipeline

**TL;DR:** Sprint B-2a ships the full news + trend pipeline on branch `feature/b2a-news-trend`. 173 tests passing. Seven new modules in `src/finterminal/news/`, one new agent, one new data store, NSE universe, DuckDB migration, two new commands, and a Momentum badge in the UI. ChromaDB rejected; DuckDB vss (bundled since v1.1) chosen for vector storage.

**Predecessor:** [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]]
**Next:** B-2b — `/analyze` enrichment + `/brief` command

---

## What Shipped

### New Modules — `src/finterminal/news/`

| Module | Role |
|---|---|
| `collector.py` | Fetches 11 RSS feeds (Moneycontrol ×4, Livemint ×2, ET ×3, Reuters India, BusinessLine) |
| `tagger.py` | Tags stories with ticker + sector via rapidfuzz `partial_ratio`; min_score 85; DEBUG logs hits in [70,85) |
| `dedupe.py` | MinHash LSH deduplication; drops story if Jaccard similarity ≥ 0.85 against existing set |
| `embedder.py` | Lazy-loads `sentence-transformers/all-MiniLM-L6-v2` (384-d); cached in `./data/models`; cold start ~8–12 s, warm <4 s |
| `cluster.py` | Agglomerative clustering with cosine distance; threshold 0.25 (tuning constant) |
| `lineage.py` | Day-over-day cluster matching via centroid cosine ≥ 0.70; records `story_count_delta` |
| `pipeline.py` | Orchestrates all stages; called by `/refresh-news` command |

### New Agent

| File | Role |
|---|---|
| `src/finterminal/agents/news_trend.py` | `NewsTrendAgent` — reads clusters + lineage; formats trend output for `/trends [sector]` |

Note: `analyze_flow.py` registry unchanged — still 3 agents. `NewsTrendAgent` is standalone.

### New Data Layer

| File | Role |
|---|---|
| `src/finterminal/data/news_store.py` | DuckDB read/write for `news_stories`, `news_clusters`, `cluster_lineage` tables |
| `src/finterminal/data/india/nse_universe.py` | NSE equity universe loader |
| `src/finterminal/data/india/sector_map.yaml` | Sector-to-ticker mapping for tagging |
| `src/finterminal/data/india/fixtures/EQUITY_L.csv` | NSE-listed equities fixture (seeded from exchange) |

### DuckDB Migration

| File | Detail |
|---|---|
| `src/finterminal/data/migrations/003_news_pipeline.sql` | `LOAD vss;` + 3 new tables: `news_stories`, `news_clusters`, `cluster_lineage` |
| `src/finterminal/data/duckdb_store.py` | `LOAD vss` added per connection (vss bundled in DuckDB ≥ 1.1) |

**Schema additions:**

| Table | Key columns |
|---|---|
| `news_stories` | `id`, `headline`, `url`, `source`, `published_at`, `ticker_tags`, `sector_tags`, `embedding` (384-d) |
| `news_clusters` | `id`, `date`, `sector`, `centroid`, `story_ids`, `label` |
| `cluster_lineage` | `cluster_id`, `prev_cluster_id`, `centroid_cosine`, `story_count_delta`, `date` |

### New Commands

| Command | Behaviour |
|---|---|
| `/refresh-news` | Runs full pipeline: collect → tag → dedupe → embed → cluster → lineage → persist |
| `/trends [sector]` | Renders clustered trend table with Momentum badge; sector is optional filter |

### New UI — Momentum Badge (`ui/panels.py` → `render_trends_table`)

| Condition | Display |
|---|---|
| Cluster grew | `▲N (Day M)` — green |
| Cluster shrank | `▼N (Day M)` — red |
| No change | `· (Day M)` — dim |

---

## Key Design Decisions

| Decision | Choice | Rejected |
|---|---|---|
| Vector store | DuckDB vss (bundled ≥ v1.1) | ChromaDB — extra dep, separate process |
| Embedding model | `all-MiniLM-L6-v2` (384-d, sentence-transformers) | — |
| Clustering | Agglomerative cosine, threshold 0.25 | — |
| Deduplication | MinHash LSH, Jaccard ≥ 0.85 | — |
| Entity matching (tagger) | rapidfuzz `partial_ratio`, min_score 85 | — |
| Lineage | Centroid cosine ≥ 0.70 day-over-day | — |
| Pipeline trigger | Explicit `/refresh-news` (daily batch) | Daemon / scheduler |

See [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]] for full rationale.

---

## Test Count

| State | Count |
|---|---|
| Before B-2a | 123 |
| After B-2a | 173 |
| New tests | +50 |

---

## Files Affected

| File | Change |
|---|---|
| `src/finterminal/news/collector.py` | New |
| `src/finterminal/news/tagger.py` | New |
| `src/finterminal/news/dedupe.py` | New |
| `src/finterminal/news/embedder.py` | New |
| `src/finterminal/news/cluster.py` | New |
| `src/finterminal/news/lineage.py` | New |
| `src/finterminal/news/pipeline.py` | New |
| `src/finterminal/agents/news_trend.py` | New |
| `src/finterminal/data/news_store.py` | New |
| `src/finterminal/data/india/nse_universe.py` | New |
| `src/finterminal/data/india/sector_map.yaml` | New |
| `src/finterminal/data/india/fixtures/EQUITY_L.csv` | New |
| `src/finterminal/data/migrations/003_news_pipeline.sql` | New |
| `src/finterminal/data/duckdb_store.py` | `LOAD vss` per connection |
| `src/finterminal/commands.py` | `/refresh-news` + `/trends` added |
| `src/finterminal/ui/panels.py` | `render_trends_table` + Momentum badge |
| `tests/news/*` | New |
| `tests/agents/test_news_trend_agent.py` | New |
| `tests/commands/test_trends_cmd.py` | New |
| `tests/data/test_news_pipeline_migration.py` | New |
| `tests/data/test_nse_universe.py` | New |

---

## Cross-Links

- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- ADR: [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]]
- Code map: [[04 - Code Map/news — pipeline]] · [[04 - Code Map/agents — news_trend]] · [[04 - Code Map/data — news_store]]
- Predecessor: [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]]
