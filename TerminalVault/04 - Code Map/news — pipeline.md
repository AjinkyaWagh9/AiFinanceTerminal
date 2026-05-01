# Code Map — news/ pipeline (7 modules)

> Back to [[Index]] | See also [[agents — news_trend]] · [[data — news_store]] · [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]]

**Base path:** `src/finterminal/news/`
**Shipped:** 2026-04-29, Sprint B-2a (`feature/b2a-news-trend`)
**Entry point:** `pipeline.py` — called by `/refresh-news` command

---

## Module Overview

| Module | File | Role |
|---|---|---|
| Collector | `news/collector.py` | Fetches 11 RSS feeds; returns raw story list |
| Tagger | `news/tagger.py` | Attaches ticker + sector tags via rapidfuzz |
| Dedupe | `news/dedupe.py` | MinHash LSH; drops near-duplicate stories |
| Embedder | `news/embedder.py` | Generates 384-d sentence embeddings |
| Cluster | `news/cluster.py` | Groups stories into topic clusters |
| Lineage | `news/lineage.py` | Links today's clusters to yesterday's |
| Pipeline | `news/pipeline.py` | Orchestrates all stages end-to-end |

---

## `collector.py`

**Feeds (11 total):**

| Source | Feed count |
|---|---|
| Moneycontrol | 4 |
| Livemint | 2 |
| Economic Times | 3 |
| Reuters India | 1 |
| BusinessLine | 1 |

- Returns list of `{"headline", "url", "source", "published_at"}` dicts
- HTTP timeouts handled per feed; a feed failure does not abort the run

---

## `tagger.py`

- Uses `rapidfuzz.fuzz.partial_ratio` to match headlines against NSE universe names + sector keywords
- `min_score = 85` — tags applied above this threshold
- Range `[70, 85)` — DEBUG-logged but not tagged (tuning visibility)
- Attaches `ticker_tags: list[str]` and `sector_tags: list[str]` to each story
- Uses [[data — india module]] (`nse_universe.py` + `sector_map.yaml`) for the lookup corpus

---

## `dedupe.py`

- MinHash LSH deduplication
- Jaccard similarity threshold: **≥ 0.85** — story dropped if it matches an existing story in the daily set
- Applied before embedding (saves compute on duplicates)
- Stateless per pipeline run; does not persist the LSH index

---

## `embedder.py`

| Property | Value |
|---|---|
| Model | `sentence-transformers/all-MiniLM-L6-v2` |
| Dimensions | 384 |
| Loading | Lazy — loaded on first call |
| Cache | `./data/models/` (persists across runs) |
| Cold start | ~8–12 s (first run; model download) |
| Warm start | <4 s (model already cached) |

- Returns `np.ndarray` of shape `(n_stories, 384)`
- Thread-safe: model object is module-level singleton after first load

---

## `cluster.py`

| Property | Value |
|---|---|
| Algorithm | Agglomerative clustering (Ward linkage) |
| Distance metric | Cosine |
| Threshold | **0.25** — module-level constant; tune here for looser/tighter clusters |

- Input: story embeddings
- Output: list of cluster objects `{"story_ids", "centroid", "label", "sector"}`
- Centroid = mean of member embeddings (not re-optimised)
- Cluster label derived from most-frequent tagger output in member stories

---

## `lineage.py`

| Property | Value |
|---|---|
| Match criterion | Centroid cosine similarity **≥ 0.70** between today's and yesterday's cluster centroids |
| Delta field | `story_count_delta = today.story_count − yesterday.story_count` |

- Reads yesterday's clusters from [[data — news_store]] (`news_store.py`)
- Writes `cluster_lineage` rows (one per matched pair)
- Unmatched clusters get no lineage row (new topic)

---

## `pipeline.py`

**Execution order:**

```
collect → tag → dedupe → embed → cluster → lineage → persist
```

- Called by `/refresh-news` REPL command
- Daily batch; no daemon or scheduler
- All stages run synchronously in sequence
- Returns summary dict `{"stories_fetched", "stories_after_dedupe", "clusters_created", "lineage_links"}`

---

## Constants (tuning reference)

| Constant | Location | Value | Effect |
|---|---|---|---|
| Jaccard threshold | `dedupe.py` | 0.85 | Higher = less aggressive dedup |
| Cluster distance threshold | `cluster.py` | 0.25 | Higher = larger/fewer clusters |
| Tagger min score | `tagger.py` | 85 | Lower = more (noisy) tags |
| Lineage cosine threshold | `lineage.py` | 0.70 | Lower = more cross-day links |
| Embedding dim | `embedder.py` | 384 | Fixed by model choice |

---

## Cross-Links

- Agent that consumes output: [[agents — news_trend]]
- Storage: [[data — news_store]]
- NSE universe used by tagger: [[data — india module]]
- ADR: [[02 - Decisions/ADR-016 — DuckDB vss over ChromaDB]]
- Build log: [[05 - Build Log/2026-04-29 — Sprint B-2a News Trend]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]] (B-2a)
