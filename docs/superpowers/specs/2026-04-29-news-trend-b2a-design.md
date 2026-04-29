# Spec — Sprint B-2a: News & Trend pipeline + `/trends` command

**Date:** 2026-04-29
**Author:** Claude (Opus 4.7)
**Phase:** 2 — Multi-Agent Foundation, News & Trend agent (first half)
**Predecessor:** `2026-04-29-data-layer-hardening-q5-q6.md`
**Successor (planned):** B-2b — `/analyze` enrichment + `/brief` morning-brief command
**Time budget:** ~1 day (≈ half of the 4–7 day Sprint B-2 split into B-2a + B-2b per brainstorm)

---

## 1. Problem

PLAN.md §6 Phase-2 deliverable for News & Trend is unimplemented. Today, news is fetched per-ticker on every `/analyze` call (`agents/data.py:49`) using `news_rss.py:fetch_news` which case-insensitively filters 9 RSS feeds against a hardcoded 20-name alias table. There is no cross-ticker view, no deduplication beyond URL-equality, no embedding, no clustering, no narrative tracking. The terminal cannot answer "what stories are dominating Indian markets today" or "which sectors are heating up."

This blocks the Phase-2 exit criterion (PLAN §6, Phase 2): *"opening the terminal at 8 AM surfaces ≥3 actionable signals you wouldn't have found by browsing."* Without clustering you cannot reason at the story level — only the article level, which is noisy.

## 2. Scope

### In scope (B-2a)

1. **Collector** — pull all 11 RSS feeds in parallel, normalize into a single per-day story stream (no per-ticker filter).
2. **Tagger** — load NSE `EQUITY_L.csv` at startup, build full ticker alias map + sector map; tag each story with `tickers: list[str]` and `sectors: list[str]`.
3. **Dedupe** — two-stage: exact URL → MinHash (Jaccard ≥ 0.85) on shingled headlines to drop wire-republishes.
4. **Embedder** — `sentence-transformers/all-MiniLM-L6-v2` (384-d), local-only.
5. **Clusterer** — agglomerative (single linkage, cosine distance, threshold 0.25) on each day's deduped corpus.
6. **Narrative-arc lineage** — match each new cluster to yesterday's clusters by centroid cosine ≥ 0.7; persist parent→child lineage; compute story-count delta.
7. **DuckDB schema** — new tables `news_stories`, `news_clusters`, `cluster_lineage` via migration `003_news_pipeline.sql`. `vss` extension for ANN search on embeddings.
8. **Commands** — `/refresh-news` (run pipeline, persist snapshot) and `/trends [sector]` (read latest snapshot, render table).
9. **News & Trend agent** — wraps the pipeline behind `agents.base.Agent` Protocol so B-2b can compose it into the `/analyze` flow.
10. **Tests** — unit + integration coverage matching project bar (currently 123 green).

### Out of scope (deferred to B-2b)

- `/analyze` enrichment (injecting cluster context into Analyst prompt).
- `/brief` morning-brief command (LLM synthesis of cross-watchlist signals).
- LLM-generated "what changed today" narrative summary per cluster.
- Voyage-3-lite or other hosted embeddings — local model first, swap later if cluster quality is the bottleneck.
- Background daemon / scheduled refresh — explicit `/refresh-news` only.
- Textual TUI tabs — Phase 2 said Textual but Rich works; Textual migration is its own spec.

### Hard non-goals

- US news sources (Phase 3).
- Sentiment scoring (Phase 2.5).
- News-driven alerts / push notifications (BACKLOG §1.6, Phase 3).

---

## 3. Decisions (locked via brainstorm 2026-04-29)

| # | Decision | Choice | Why |
|---|---|---|---|
| 3.1 | Sprint scope | **D — decompose into B-2a + B-2b** | 7-day branches risk hard-to-bisect failures; smaller specs match the project's 4a/FU-2/Q-5/Q-6 cadence |
| 3.2 | Pipeline cadence | **B — daily snapshot via explicit `/refresh-news`** | Honest about cost, narrative-arc lineage clean, no daemon complexity |
| 3.3 | Storage + embeddings | **B — DuckDB + `vss` + `all-MiniLM-L6-v2`** | Single store; `vss` is stable since DuckDB v1.1; PLAN's ChromaDB line predates `vss` |
| 3.4 | RSS feed set | 11 feeds — existing 9 + Reuters India + The Hindu BusinessLine | Free, no auth, complementary editorial; skip BloombergQuint (paywall) |
| 3.5 | Story → ticker/sector tagging | NSE `EQUITY_L.csv` autoload → ticker alias map + curated `sector_map.yaml`; **`rapidfuzz` fallback** for low-confidence headline matches | Deterministic + scalable + handles spelling variants |
| 3.6 | Clustering | MinHash dedup (Jaccard ≥ 0.85) → agglomerative single-linkage cosine (threshold 0.25) | Simple, deterministic, fast at 50–200 stories/day |
| 3.7 | `/trends` table | Cluster, Stories, Sources, Top tickers, Representative headline, First seen, **Momentum** | Mirrors `/news` / `/watchlist`; column is short for clean table rendering and folds in Q8 story-count delta |
| 3.8 | Narrative-arc | Centroid cosine ≥ 0.7 → `cluster_lineage(parent_id, child_id, day, similarity, story_count_delta)`; render `▲N (Day M)` / `▼N (Day M)` badges where N = story_count_delta and M = consecutive-day count | Lineage + story-count delta is enough; LLM-generated arc summaries are B-2b. `story_count_delta` is a stored column (not computed at read time) so `/trends` queries stay simple |

---

## 4. Architecture

### 4.1 Module layout

```
src/finterminal/
├── news/                          # NEW — pipeline (deterministic, no LLM)
│   ├── __init__.py
│   ├── collector.py               # parallel RSS pull + normalize
│   ├── tagger.py                  # ticker + sector tagging via NSE universe
│   ├── dedupe.py                  # URL + MinHash
│   ├── embedder.py                # sentence-transformers wrapper, lazy load
│   ├── cluster.py                 # agglomerative on cosine distances
│   ├── lineage.py                 # day-over-day cluster matching
│   └── pipeline.py                # orchestrates the full run, persists rows
├── agents/
│   └── news_trend.py              # NEW — Agent Protocol wrapper
├── data/
│   ├── india/
│   │   ├── nse_universe.py        # NEW — EQUITY_L.csv loader + alias map
│   │   └── sector_map.yaml        # NEW — NSE industry → trends-bucket map (curated)
│   ├── migrations/
│   │   └── 003_news_pipeline.sql  # NEW — news_stories + news_clusters + cluster_lineage
│   └── news_store.py              # NEW — read/write helpers for the new tables
├── commands.py                    # add /refresh-news + /trends
└── ui/
    └── panels.py                  # add render_trends_table
```

Why split `news/` from `agents/news_trend.py`: the pipeline is deterministic Python (collect → embed → cluster); the agent is the thin Protocol-conforming wrapper that B-2b will compose into `analyze_flow`. Same separation as `data/openbb_client.py` (deterministic) vs `agents/data.py` (Protocol wrapper).

### 4.2 Pipeline data flow

```
[11 RSS feeds]
   → collector.fetch_all()        →  list[Story]            (raw, may dupe)
   → dedupe.drop_url_dupes()      →  list[Story]            (URL-unique)
   → tagger.tag(stories)          →  list[Story]            (+ tickers, sectors)
   → dedupe.minhash_filter()      →  list[Story]            (Jaccard < 0.85)
   → embedder.embed(stories)      →  list[Story]            (+ embedding[384])
   → cluster.cluster(stories)     →  list[Cluster]
   → lineage.match_to_yesterday() →  list[Cluster]          (+ parent_id, day_n)
   → news_store.persist(...)      →  rows in DuckDB
```

Each step is a pure function on the previous step's output, except `persist` (side-effecting). This means every step is unit-testable without mocking adjacent steps.

### 4.3 DuckDB schema (migration `003_news_pipeline.sql`)

`vss` extension setup: `INSTALL vss;` runs once inside migration `003`; `LOAD vss;` runs on every connection from `duckdb_store.get_conn()` (per-connection state, like extensions in Postgres). Document migration runner already executes statements idempotently.

```sql
-- One row per de-duped story, with embedding
CREATE TABLE IF NOT EXISTS news_stories (
    id              VARCHAR PRIMARY KEY,        -- sha256(url) or sha256(headline) fallback
    url             VARCHAR,
    source          VARCHAR NOT NULL,
    headline        VARCHAR NOT NULL,
    body            VARCHAR,
    published_at    TIMESTAMP,
    fetched_at      TIMESTAMP NOT NULL,
    tickers         VARCHAR[],                  -- e.g. ['RELIANCE', 'JIO']
    sectors         VARCHAR[],                  -- e.g. ['Energy', 'Telecom']
    embedding       FLOAT[384],
    cluster_id      VARCHAR                     -- FK to news_clusters.id
);

-- One row per cluster per day
CREATE TABLE IF NOT EXISTS news_clusters (
    id              VARCHAR PRIMARY KEY,        -- uuid
    as_of           DATE NOT NULL,              -- pipeline run date
    story_count     INTEGER NOT NULL,
    source_count    INTEGER NOT NULL,
    top_tickers     VARCHAR[],                  -- top 3 by story-count within cluster
    dominant_sector VARCHAR,                    -- mode of stories.sectors, ties broken alphabetically
    representative_id    VARCHAR,               -- story_id with min cosine to centroid
    centroid        FLOAT[384],
    first_seen      TIMESTAMP NOT NULL          -- min(published_at) within cluster
);

CREATE INDEX IF NOT EXISTS news_clusters_as_of_idx ON news_clusters(as_of);

-- Day-over-day lineage; one row per (parent, child) link
CREATE TABLE IF NOT EXISTS cluster_lineage (
    parent_id           VARCHAR NOT NULL,       -- yesterday's cluster
    child_id            VARCHAR NOT NULL,       -- today's cluster
    day                 DATE NOT NULL,          -- = today's as_of
    similarity          DOUBLE NOT NULL,        -- centroid cosine
    story_count_delta   INTEGER NOT NULL,       -- child.story_count - parent.story_count (signed)
    PRIMARY KEY (parent_id, child_id)
);

-- HNSW index for ANN — used by lineage.match_to_yesterday
CREATE INDEX IF NOT EXISTS news_clusters_hnsw
    ON news_clusters USING HNSW (centroid)
    WITH (metric = 'cosine');
```

`as_of` is `DATE` not `TIMESTAMP` per the project's "DuckDB column gotcha" note in CLAUDE.md.

### 4.3a Implementation notes for tunable steps

These three tunables surfaced in spec review; bake them into the code now so first-run tuning is mechanical:

- **`news/collector.py`** — feed list lives at module-level constant `_FEEDS: list[tuple[str, str]]` with a comment: `# Add new RSS feeds here. Keep parsing path generic — RSS 2.0 + Atom both supported. Reuters India + BusinessLine added in B-2a; expand at sprint boundaries, not in flight.`
- **`news/tagger.py`** — `min_score: int = 85` keyword arg on `tag()` (rapidfuzz threshold). When score is in `[70, min_score)`, log `DEBUG`-level: `low-confidence match: '<headline_snippet>' ↔ '<alias>' = <score>`. Helps tune the threshold across the first 3 runs without code changes.
- **`news/cluster.py`** — top-of-file constants:
  ```python
  # Tune these based on manual inspection of the first 3 runs.
  # 0.25 = single-linkage cosine threshold below which stories merge into one cluster.
  # Lower → more, smaller clusters; higher → fewer, broader clusters.
  CLUSTER_DISTANCE_THRESHOLD = 0.25
  MINHASH_JACCARD_THRESHOLD = 0.85       # dedupe.py imports this
  LINEAGE_CENTROID_THRESHOLD = 0.7       # lineage.py imports this
  ```
  All three thresholds in one module so a single PR can re-tune them.

### 4.4 NSE universe loader (`data/india/nse_universe.py`)

- `load_equity_list(path: Path | None = None) -> dict` — reads NSE's `EQUITY_L.csv` (~2000 rows: `SYMBOL`, `NAME OF COMPANY`, `SERIES`, ...). Bundles a snapshot at `data/india/fixtures/EQUITY_L.csv` so we work offline; falls back to that snapshot if NSE is unreachable.
- Returns `{ticker: {"name": str, "aliases": list[str]}}`. Aliases generated by simple rules: full name, name minus suffixes ("Limited", "Ltd", "Ltd.", "Industries", "Corp"), acronym from capitals.
- `load_sector_map(path: Path) -> dict[str, str]` — reads `sector_map.yaml`. Format: `RELIANCE: Energy`. We curate this file (not auto-derived) because NSE's industry classification is too granular (~80 buckets); we want ~12 trends-friendly buckets (Banking, IT, FMCG, Pharma, Auto, Energy, Metals, Telecom, Cement, Realty, Capital Goods, Other).

`tagger.tag()` algorithm:
1. For each story, score each (ticker, alias) pair: exact whole-word match → 1.0, `rapidfuzz` ratio ≥ 90 → 0.8, else 0.
2. Keep tickers with any positive score; sectors are union of those tickers' sectors.
3. Cap at 5 tickers per story (avoid index-update articles tagging every name).

### 4.5 News & Trend agent (`agents/news_trend.py`)

```python
class NewsTrendAgent:
    name = "news_trend"
    is_llm = False  # B-2a is deterministic; B-2b adds LLM summarization

    def __init__(self, pipeline: Callable[[duckdb.DuckDBPyConnection], PipelineResult]):
        self._pipeline = pipeline

    async def run(self, ctx: AgentContext) -> AgentResult:
        # B-2a: pipeline runs cross-ticker; ticker in ctx is ignored.
        # B-2b will use ctx.ticker to select clusters relevant to it.
        result = await asyncio.to_thread(self._pipeline, ctx.conn)
        return AgentResult(ok=True, payload=result)
```

`PipelineResult` is `dict[str, Any]` with: `as_of`, `n_stories`, `n_clusters`, `n_lineage_links`, `runtime_s`. Nothing the Analyst would consume in B-2a; the agent exists to keep the wiring uniform with `data` / `analyst` / `critic`.

### 4.6 Commands

`commands._cmd_refresh_news`:
- `news.pipeline.run(conn)` is a sync function — embedder load + clustering are CPU-bound but tractable; no asyncio at the command layer (matches `_cmd_analyze`'s `asyncio.run(...)` bridging pattern only where needed).
- Prints summary: `Refreshed N stories → M clusters in T.Ts. K lineage links from yesterday.`
- The Agent wrapper in §4.5 is what wraps the same `pipeline.run` in `asyncio.to_thread` for B-2b's async orchestrator; B-2a never goes through the Agent path.

`commands._cmd_trends`:
- Optional positional arg = sector (case-insensitive match against `sector_map.yaml` values).
- Reads latest `news_clusters` row by `max(as_of)`.
- Joins with `cluster_lineage` to compute trend-strength badge.
- Renders via `panels.render_trends_table`.

### 4.7 Momentum badge

For each cluster:
- `delta = today.story_count - sum(parents.story_count)` (delta vs. yesterday's matched clusters; 0 if no parents). Persisted as `cluster_lineage.story_count_delta` per (parent, child) row.
- `day_n = max(parent.day_n for p in parents) + 1`, else 1.
- Render: `▲{delta} (Day {day_n})` if delta > 0; `▼{abs(delta)} (Day {day_n})` if delta < 0; `· (Day {day_n})` if delta == 0; empty cell if day_n == 1.

### 4.8 `/trends` panel layout

```
┌─ Trends — as_of 2026-04-30 ────────────────────────────────────────────────┐
│ Cluster  Stories  Sources  Top tickers           Headline (representative) … First seen   Momentum │
│ #c01a    14       6        RELIANCE, JIO         Reliance Q4 beats on Jio …  2026-04-29   ▲5 (Day 3) │
│ #c02b    9        4        HDFCBANK              HDFC Bank flags MFI stress  2026-04-30                │
│ ...                                                                                              │
│ as_of 2026-04-30 08:14 IST · run /refresh-news for fresh data                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Bracket-escape via the existing `_escape_markup` helper from Q-6 — headlines often contain `[...]` text.

---

## 5. Test plan (TDD — red first, then green)

| File | Coverage |
|---|---|
| `tests/news/test_collector.py` | mock httpx; assert all 11 feeds attempted; one feed failure does not poison the batch; pubdate parsing handles RSS + ISO |
| `tests/news/test_dedupe.py` | URL dupes dropped; MinHash threshold catches "Reliance Q4 beats" duplicated across 4 wires; legit-similar-but-distinct headlines kept |
| `tests/news/test_tagger.py` | EQUITY_L fixture loads; "Reliance Industries" tags `RELIANCE` + sector `Energy`; "HDFC Bank" → `HDFCBANK` + `Banking`; rapidfuzz catches "Hindustan Unliever" → `HINDUNILVR`; cap-5 enforced |
| `tests/news/test_embedder.py` | model loads (cached after first call); shape == (n, 384); deterministic on fixed input |
| `tests/news/test_cluster.py` | 6 stories about Reliance + 4 about HDFC Bank → 2 clusters; threshold 0.25 separates topics; deterministic ordering |
| `tests/news/test_lineage.py` | yesterday's centroid vs today's, cosine ≥ 0.7 → matched; < 0.7 → orphan; story-count delta computed correctly |
| `tests/news/test_pipeline.py` | end-to-end with stubbed feeds → DuckDB rows in 3 tables; runtime assertion (< 10s on fixture) |
| `tests/agents/test_news_trend_agent.py` | Protocol conformance; AgentResult ok=True on happy path; ok=False with error on pipeline raise |
| `tests/data/test_news_pipeline_migration.py` | migration applies cleanly; vss extension loads; HNSW index creatable |
| `tests/data/test_nse_universe.py` | bundled fixture parses; alias generation rules (Ltd/Limited/Industries stripping) |
| `tests/commands/test_trends_cmd.py` | `/trends` with no snapshot → friendly error; with snapshot → table renders; `/trends Banking` filters; trend-strength badges render |

Target: **+30 tests** (123 → ~153), all green, ruff clean.

---

## 6. Rollout (commit plan)

1. `test: news pipeline + /trends + agent — failing skeleton (red)`
2. `feat(data): migration 003 — news_stories + news_clusters + cluster_lineage with vss`
3. `feat(data/india): NSE universe loader + sector_map.yaml + EQUITY_L.csv fixture`
4. `feat(news): collector — 11 feeds, parallel pull, normalize`
5. `feat(news): tagger — alias map + rapidfuzz fallback + sector lookup`
6. `feat(news): dedupe — URL + MinHash (Jaccard ≥ 0.85)`
7. `feat(news): embedder — sentence-transformers/all-MiniLM-L6-v2 with lazy load + cache`
8. `feat(news): cluster — agglomerative single-linkage cosine, threshold 0.25`
9. `feat(news): lineage — centroid cosine ≥ 0.7, story-count delta, day_n`
10. `feat(news): pipeline orchestrator — run() + persist`
11. `feat(agents): NewsTrendAgent Protocol wrapper`
12. `feat(commands): /refresh-news + /trends [sector]`
13. `feat(ui): render_trends_table with trend-strength badge`
14. `chore: smoke-verify /refresh-news + /trends across two days`
15. `chore: vault build-log entry — B-2a` (subagent)

---

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `vss` extension version pin issue on first install | Medium | Pin `duckdb` to ≥1.1 in `pyproject.toml`; install `vss` via `INSTALL vss FROM core_nightly` if needed; bundled migration tries `INSTALL vss; LOAD vss;` and falls back to a no-HNSW path (linear scan acceptable at 50–500 clusters) |
| sentence-transformers cold load is slow (~5s on first call) | High | Lazy-load on first `embed()`; cache to `./data/models/`; warm in `/refresh-news` not on every `/trends`. **Expected wall-clock: first run ≈ 8–12s for model download + 384-d encoding of ~150 headlines; subsequent runs < 4s due to model cache.** |
| NSE blocks `EQUITY_L.csv` fetch | Medium | Bundle a 2026-04 snapshot at `data/india/fixtures/EQUITY_L.csv`; loader prefers fresh, falls back silently |
| MinHash false positives on legit-distinct headlines | Medium | Jaccard ≥ 0.85 is conservative; fixture-based tests with 5 hand-picked near-miss pairs; threshold tunable in one constant |
| Agglomerative threshold (0.25) wrong for our corpus | High | First smoke run will surface this; threshold is a single constant in `cluster.py`. Acceptance: in a fixture of 30 stories about 4 known events, clustering must yield 4 clusters ±1 |
| `/trends` slow if HNSW unavailable | Low | At ≤500 clusters/day, linear cosine is < 100ms |
| Sector map staleness | Low | YAML lives in repo; PR-reviewable; covers Nifty500 + extras (~600 entries); re-curate at each phase boundary |
| News & Trend agent integrated into `/analyze` accidentally in B-2a | Low | B-2a does NOT touch `analyze_flow.py`. Test asserts `analyze_flow` registry has exactly 3 agents (data, analyst, critic). |

---

## 8. Done criteria

- [ ] All 15 commits land green
- [ ] `uv run pytest -q` passes (target ≥ 153 tests, currently 123)
- [ ] `uv run ruff check src tests` clean
- [ ] `uv run finterminal` → `/refresh-news` populates `news_stories` (≥ 50 rows on a real day) + `news_clusters` (≥ 5 clusters) in < 60s wall clock
- [ ] `/trends` shows ≥ 3 clusters, sorted by story count, with `as_of` footer
- [ ] `/trends Banking` filters to banking-only clusters (assert by inspection that all visible clusters' top tickers are in the Banking sector)
- [ ] **Sector filter manual verification across 3 sectors**: `/trends Banking`, `/trends IT`, `/trends Energy` each return only clusters whose `dominant_sector` matches; record screenshots/text in vault build-log
- [ ] Run `/refresh-news` on day 1, then again on day 2 → at least one cluster shows `(Day 2)` badge with non-zero story-count delta
- [ ] `analyze_flow.py` is unchanged (registry still 3 agents)
- [ ] Vault build-log entry committed in TerminalVault (subagent)

---

## 9. Hand-off to B-2b

B-2b builds on this snapshot. Specifically:
- `analyze_flow` will register `NewsTrendAgent`; the Analyst's context block gets a `news_clusters_for_ticker` section sourced via `WHERE list_contains(top_tickers, ?)`.
- `/brief` reads the same `news_clusters` table, filters to clusters intersecting the watchlist, and synthesizes 3+ signals via Claude.
- The NewsTrendAgent's `is_llm` flips to `True` when LLM-summarization lands.

No schema changes anticipated for B-2b; the schema in §4.3 is sized for the full feature.
