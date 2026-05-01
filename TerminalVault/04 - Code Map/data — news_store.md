# Code Map — data/news_store.py

> Back to [[Index]] | See also [[news — pipeline]] · [[data — OpenBB + DuckDB]] · [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]]

**File:** `src/finterminal/data/news_store.py`
**Shipped:** 2026-04-29, Sprint B-2a (`feature/b2a-news-trend`)
**Migration:** `src/finterminal/data/migrations/003_news_pipeline.sql`

---

## Purpose

DuckDB read/write interface for the three news pipeline tables. Wraps raw SQL with typed Python methods. Used by `pipeline.py` (write path) and `news_trend.py` (read path).

---

## Tables Managed

| Table | Purpose |
|---|---|
| `news_stories` | One row per deduplicated story; stores embedding as FLOAT[] |
| `news_clusters` | One row per cluster per day; stores centroid as FLOAT[] |
| `cluster_lineage` | One row per matched cluster pair across consecutive days |

### `news_stories` schema

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR | UUID, primary key |
| `headline` | VARCHAR | Raw headline text |
| `url` | VARCHAR | Source URL |
| `source` | VARCHAR | Feed name (e.g. `moneycontrol`, `et`) |
| `published_at` | TIMESTAMPTZ | From RSS feed |
| `ticker_tags` | VARCHAR[] | Matched tickers (may be empty) |
| `sector_tags` | VARCHAR[] | Matched sectors (may be empty) |
| `embedding` | FLOAT[384] | `all-MiniLM-L6-v2` embedding |
| `ingested_at` | TIMESTAMPTZ | Pipeline run timestamp |

### `news_clusters` schema

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR | UUID, primary key |
| `date` | DATE | Cluster date (pipeline run date) |
| `sector` | VARCHAR | Majority sector tag |
| `label` | VARCHAR | Human-readable topic label |
| `story_ids` | VARCHAR[] | Member story IDs |
| `centroid` | FLOAT[384] | Mean embedding of member stories |
| `story_count` | INTEGER | `len(story_ids)` |

### `cluster_lineage` schema

| Column | Type | Notes |
|---|---|---|
| `cluster_id` | VARCHAR | FK → `news_clusters.id` (today) |
| `prev_cluster_id` | VARCHAR | FK → `news_clusters.id` (yesterday) |
| `centroid_cosine` | FLOAT | Cosine similarity of centroids |
| `story_count_delta` | INTEGER | `today.story_count − yesterday.story_count` |
| `date` | DATE | Today's date |

---

## DuckDB vss Integration

- `duckdb_store.py` runs `LOAD vss;` on every new connection (vss bundled since DuckDB v1.1)
- `news_store.py` uses vss `array_cosine_similarity` for centroid-matching queries in lineage reads
- No separate vector DB process required

---

## Public API (key methods)

| Method | Direction | Used by |
|---|---|---|
| `insert_stories(stories: list[dict])` | Write | `pipeline.py` |
| `insert_clusters(clusters: list[dict])` | Write | `pipeline.py` |
| `insert_lineage(links: list[dict])` | Write | `pipeline.py` |
| `get_clusters_for_date(date, sector=None)` | Read | `news_trend.py` |
| `get_lineage_for_date(date)` | Read | `news_trend.py` |
| `get_yesterday_centroids()` | Read | `lineage.py` |

---

## Cross-Links

- Pipeline that writes data: [[news — pipeline]]
- Agent that reads data: [[agents — news_trend]]
- Base store: [[data — OpenBB + DuckDB]]
- ADR: [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]]
- Build log: [[05 - Build Log/2026-04-29 — Sprint B-2a News Trend]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]] (B-2a)
