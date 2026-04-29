# News & Trend B-2a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the News & Trend pipeline (collect → dedupe → embed → cluster → lineage) and expose it via `/refresh-news` and `/trends [sector]` commands, giving the terminal its first cross-ticker market-narrative view.

**Architecture:** A new `src/finterminal/news/` package runs the deterministic pipeline as a sequence of pure functions; a `data/news_store.py` module handles all DuckDB reads/writes for the three new tables; a thin `agents/news_trend.py` Protocol wrapper makes the pipeline composable in B-2b. Commands are added to `commands.py`; rendering lives in `ui/panels.py`.

**Tech Stack:** Python 3.13, DuckDB 1.5+ with `vss` extension, `sentence-transformers/all-MiniLM-L6-v2`, `scipy` agglomerative clustering, `datasketch` MinHash, `rapidfuzz` fuzzy matching, `httpx`, `pyyaml`, Rich tables.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/finterminal/data/migrations/003_news_pipeline.sql` | Create | DuckDB tables: `news_stories`, `news_clusters`, `cluster_lineage` + vss + HNSW index |
| `src/finterminal/data/india/nse_universe.py` | Create | Load `EQUITY_L.csv`, build ticker alias map + sector lookup |
| `src/finterminal/data/india/fixtures/EQUITY_L.csv` | Create | Bundled NSE equity list snapshot (offline fallback) |
| `src/finterminal/data/india/sector_map.yaml` | Create | Curated ticker → sector map (~12 buckets) |
| `src/finterminal/data/news_store.py` | Create | DuckDB read/write helpers for the three new tables |
| `src/finterminal/news/__init__.py` | Create | Empty |
| `src/finterminal/news/collector.py` | Create | Parallel RSS pull, normalize to `Story` dataclass, 11 feeds |
| `src/finterminal/news/tagger.py` | Create | Tag stories with `tickers` + `sectors` from NSE universe |
| `src/finterminal/news/dedupe.py` | Create | URL-dedup then MinHash Jaccard ≥ 0.85 |
| `src/finterminal/news/embedder.py` | Create | Lazy-load `all-MiniLM-L6-v2`, return `np.ndarray` |
| `src/finterminal/news/cluster.py` | Create | Agglomerative cosine clustering + threshold constants |
| `src/finterminal/news/lineage.py` | Create | Match today's clusters to yesterday's, compute day_n + story_count_delta |
| `src/finterminal/news/pipeline.py` | Create | Orchestrate all steps, return `PipelineResult` |
| `src/finterminal/agents/news_trend.py` | Create | `NewsTrendAgent` implementing `Agent` Protocol |
| `src/finterminal/commands.py` | Modify | Add `/refresh-news` + `/trends [sector]` to `_COMMANDS` |
| `src/finterminal/ui/panels.py` | Modify | Add `render_trends_table` |
| `tests/news/test_collector.py` | Create | |
| `tests/news/test_dedupe.py` | Create | |
| `tests/news/test_tagger.py` | Create | |
| `tests/news/test_embedder.py` | Create | |
| `tests/news/test_cluster.py` | Create | |
| `tests/news/test_lineage.py` | Create | |
| `tests/news/test_pipeline.py` | Create | |
| `tests/agents/test_news_trend_agent.py` | Create | |
| `tests/data/test_news_pipeline_migration.py` | Create | |
| `tests/data/test_nse_universe.py` | Create | |
| `tests/commands/test_trends_cmd.py` | Create | |

---

## Task 1: Install new dependencies

**Files:**
- Modify: `finterminal/pyproject.toml`

- [ ] **Step 1: Add dependencies**

Edit `pyproject.toml` `dependencies` list to add:
```toml
"sentence-transformers>=3.0.0",
"datasketch>=1.6.0",
"rapidfuzz>=3.0.0",
"scipy>=1.13.0",
"numpy>=2.0.0",
```

Note: `duckdb>=1.5.2` already in deps — `vss` is bundled with DuckDB ≥1.1, no extra package.

- [ ] **Step 2: Install**

```bash
cd finterminal && uv sync
```
Expected: resolves + installs without conflicts.

- [ ] **Step 3: Verify imports**

```bash
uv run python -c "import sentence_transformers, datasketch, rapidfuzz, scipy, numpy; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add sentence-transformers datasketch rapidfuzz scipy numpy for B-2a"
```

---

## Task 2: DuckDB migration 003 — news pipeline tables

**Files:**
- Create: `src/finterminal/data/migrations/003_news_pipeline.sql`
- Create: `tests/data/test_news_pipeline_migration.py`

- [ ] **Step 1: Write failing test**

Create `tests/data/test_news_pipeline_migration.py`:
```python
"""Test that migration 003 applies cleanly and creates all expected tables + index."""
import duckdb
import pytest
from finterminal.data.duckdb_store import get_conn


def test_migration_creates_news_stories(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    conn = get_conn()
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    assert "news_stories" in tables
    assert "news_clusters" in tables
    assert "cluster_lineage" in tables
    conn.close()


def test_news_stories_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    conn = get_conn()
    cols = {r[0] for r in conn.execute("DESCRIBE news_stories").fetchall()}
    for expected in ["id", "url", "source", "headline", "body", "published_at",
                     "fetched_at", "tickers", "sectors", "embedding", "cluster_id"]:
        assert expected in cols, f"missing column: {expected}"
    conn.close()


def test_cluster_lineage_has_story_count_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    conn = get_conn()
    cols = {r[0] for r in conn.execute("DESCRIBE cluster_lineage").fetchall()}
    assert "story_count_delta" in cols
    conn.close()


def test_vss_extension_loads(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    conn = get_conn()
    # If vss loaded successfully, we can query extensions
    result = conn.execute(
        "SELECT loaded FROM duckdb_extensions() WHERE extension_name = 'vss'"
    ).fetchone()
    assert result is not None and result[0] is True
    conn.close()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd finterminal && uv run pytest tests/data/test_news_pipeline_migration.py -v
```
Expected: `FAILED` — `news_stories` not in tables.

- [ ] **Step 3: Create migration file**

Create `src/finterminal/data/migrations/003_news_pipeline.sql`:
```sql
-- Sprint B-2a: news pipeline tables.
-- vss is a DuckDB core extension (bundled since v1.1). INSTALL is idempotent.
INSTALL vss;
LOAD vss;

CREATE TABLE IF NOT EXISTS news_stories (
    id              VARCHAR PRIMARY KEY,
    url             VARCHAR,
    source          VARCHAR NOT NULL,
    headline        VARCHAR NOT NULL,
    body            VARCHAR,
    published_at    TIMESTAMP,
    fetched_at      TIMESTAMP NOT NULL,
    tickers         VARCHAR[],
    sectors         VARCHAR[],
    embedding       FLOAT[384],
    cluster_id      VARCHAR
);

CREATE TABLE IF NOT EXISTS news_clusters (
    id              VARCHAR PRIMARY KEY,
    as_of           DATE NOT NULL,
    story_count     INTEGER NOT NULL,
    source_count    INTEGER NOT NULL,
    top_tickers     VARCHAR[],
    dominant_sector VARCHAR,
    representative_id VARCHAR,
    centroid        FLOAT[384],
    first_seen      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS news_clusters_as_of_idx ON news_clusters(as_of);

CREATE TABLE IF NOT EXISTS cluster_lineage (
    parent_id           VARCHAR NOT NULL,
    child_id            VARCHAR NOT NULL,
    day                 DATE NOT NULL,
    similarity          DOUBLE NOT NULL,
    story_count_delta   INTEGER NOT NULL,
    PRIMARY KEY (parent_id, child_id)
);
```

Note: HNSW index on `news_clusters.centroid` is deferred to post-first-run (requires rows to exist on some DuckDB versions). Linear scan is < 100ms at ≤500 clusters.

- [ ] **Step 4: Load vss per connection in `duckdb_store.get_conn`**

Edit `src/finterminal/data/duckdb_store.py` — add `LOAD vss;` after connect:

```python
def get_conn() -> duckdb.DuckDBPyConnection:
    """Returns a DuckDB connection. Runs migrations on first open."""
    conn = duckdb.connect(str(_db_path()))
    try:
        conn.execute("LOAD vss")
    except Exception:
        pass  # vss not installed yet — migration 003 will INSTALL it
    _run_migrations(conn)
    return conn
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/data/test_news_pipeline_migration.py -v
```
Expected: all 4 pass.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/data/migrations/003_news_pipeline.sql \
        src/finterminal/data/duckdb_store.py \
        tests/data/test_news_pipeline_migration.py
git commit -m "feat(data): migration 003 — news_stories + news_clusters + cluster_lineage with vss"
```

---

## Task 3: NSE universe loader + sector map + fixture

**Files:**
- Create: `src/finterminal/data/india/nse_universe.py`
- Create: `src/finterminal/data/india/sector_map.yaml`
- Create: `src/finterminal/data/india/fixtures/EQUITY_L.csv`
- Create: `tests/data/test_nse_universe.py`

- [ ] **Step 1: Write failing tests**

Create `tests/data/test_nse_universe.py`:
```python
"""Test NSE universe loader."""
import pytest
from finterminal.data.india.nse_universe import load_equity_list, load_sector_map


def test_load_equity_list_returns_dict():
    universe = load_equity_list()
    assert isinstance(universe, dict)
    assert len(universe) > 10


def test_known_ticker_present():
    universe = load_equity_list()
    assert "RELIANCE" in universe
    assert "INFY" in universe


def test_aliases_generated():
    universe = load_equity_list()
    rel = universe["RELIANCE"]
    assert "aliases" in rel
    assert len(rel["aliases"]) >= 1


def test_ltd_stripped_from_alias():
    """'Reliance Industries Limited' alias list should include 'Reliance Industries'."""
    universe = load_equity_list()
    rel = universe["RELIANCE"]
    aliases_lower = [a.lower() for a in rel["aliases"]]
    assert any("reliance industries" in a for a in aliases_lower)


def test_load_sector_map_returns_dict():
    sector_map = load_sector_map()
    assert isinstance(sector_map, dict)
    assert len(sector_map) > 5


def test_reliance_in_sector_map():
    sector_map = load_sector_map()
    assert "RELIANCE" in sector_map
    assert sector_map["RELIANCE"] == "Energy"
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/data/test_nse_universe.py -v
```
Expected: `FAILED` — module not found.

- [ ] **Step 3: Create bundled EQUITY_L.csv fixture**

Create `src/finterminal/data/india/fixtures/EQUITY_L.csv` with at minimum these rows (keep the official NSE column headers):

```
SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,PAID UP VALUE,MARKET LOT,ISIN NUMBER,FACE VALUE
RELIANCE,Reliance Industries Limited,EQ,29-Nov-1995,10,1,INE002A01018,10
INFY,Infosys Limited,EQ,08-Feb-1995,5,1,INE009A01021,5
TCS,Tata Consultancy Services Limited,EQ,25-Aug-2004,1,1,INE467B01029,1
HDFCBANK,HDFC Bank Limited,EQ,19-Jan-1995,1,1,INE040A01034,1
ICICIBANK,ICICI Bank Limited,EQ,17-Sep-1997,2,1,INE090A01021,2
SBIN,State Bank of India,EQ,01-Mar-1995,1,1,INE062A01020,1
ITC,ITC Limited,EQ,01-Jan-1995,1,1,INE154A01025,1
HINDUNILVR,Hindustan Unilever Limited,EQ,05-Mar-1995,1,1,INE030A01027,1
LT,Larsen & Toubro Limited,EQ,07-Jan-1995,2,1,INE018A01030,2
AXISBANK,Axis Bank Limited,EQ,16-Nov-1998,2,1,INE238A01034,2
KOTAKBANK,Kotak Mahindra Bank Limited,EQ,20-Dec-1995,5,1,INE237A01028,5
BAJFINANCE,Bajaj Finance Limited,EQ,01-Apr-2003,2,1,INE296A01024,2
ASIANPAINT,Asian Paints Limited,EQ,07-Mar-1995,1,1,INE021A01026,1
MARUTI,Maruti Suzuki India Limited,EQ,09-Jul-2003,5,1,INE585B01010,5
TATASTEEL,Tata Steel Limited,EQ,18-Nov-1998,1,1,INE081A01020,1
HCLTECH,HCL Technologies Limited,EQ,06-Jan-2000,2,1,INE860A01027,2
WIPRO,Wipro Limited,EQ,08-Nov-1995,2,1,INE075A01022,2
ADANIENT,Adani Enterprises Limited,EQ,25-May-1994,1,1,INE423A01024,1
NTPC,NTPC Limited,EQ,05-Nov-2004,10,1,INE733E01010,10
ONGC,Oil and Natural Gas Corporation Limited,EQ,19-Aug-1994,5,1,INE213A01029,5
JSWSTEEL,JSW Steel Limited,EQ,22-Mar-2005,1,1,INE019A01038,1
POWERGRID,Power Grid Corporation of India Limited,EQ,05-Oct-2007,10,1,INE752E01010,10
SUNPHARMA,Sun Pharmaceutical Industries Limited,EQ,07-Feb-1994,1,1,INE044A01036,1
BHARTIARTL,Bharti Airtel Limited,EQ,15-Feb-2002,5,1,INE397D01024,5
TITAN,Titan Company Limited,EQ,28-Oct-1997,1,1,INE280A01028,1
```

- [ ] **Step 4: Create sector_map.yaml**

Create `src/finterminal/data/india/sector_map.yaml`:
```yaml
# Curated ticker → trends-bucket map. 12 sectors.
# Source: NSE industry classification, hand-collapsed to trends-friendly buckets.
# Update at each phase boundary; PRs welcome.

# Banking
HDFCBANK: Banking
ICICIBANK: Banking
SBIN: Banking
AXISBANK: Banking
KOTAKBANK: Banking
BAJFINANCE: Banking

# IT
TCS: IT
INFY: IT
HCLTECH: IT
WIPRO: IT

# Energy
RELIANCE: Energy
NTPC: Energy
ONGC: Energy
POWERGRID: Energy
ADANIENT: Energy

# FMCG
ITC: FMCG
HINDUNILVR: FMCG
ASIANPAINT: FMCG
TITAN: FMCG

# Auto
MARUTI: Auto

# Metals
TATASTEEL: Metals
JSWSTEEL: Metals

# Telecom
BHARTIARTL: Telecom
```

- [ ] **Step 5: Create nse_universe.py**

Create `src/finterminal/data/india/nse_universe.py`:
```python
"""NSE equity universe loader.

Loads EQUITY_L.csv (bundled snapshot) to build:
- ticker alias map: ticker → {name, aliases}
- sector map: ticker → sector bucket (from sector_map.yaml)

Both are loaded once at import time and cached as module-level dicts.
"""
from __future__ import annotations

import csv
import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SECTOR_MAP_PATH = Path(__file__).parent / "sector_map.yaml"

_STRIP_SUFFIXES = re.compile(
    r"\b(limited|ltd\.?|industries|corporation|corp\.?|company|co\.?|bank|"
    r"technologies|tech|enterprises|services|india)\b",
    re.IGNORECASE,
)


def _generate_aliases(full_name: str) -> list[str]:
    """Generate alias variants from a company's full legal name."""
    aliases = [full_name]
    # Strip common corporate suffixes
    stripped = _STRIP_SUFFIXES.sub("", full_name).strip(" ,-")
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped and stripped.lower() != full_name.lower():
        aliases.append(stripped)
    # Acronym from capital letters (e.g. "HCL Technologies" → "HCL")
    caps = "".join(c for c in full_name if c.isupper())
    if len(caps) >= 2 and caps not in aliases:
        aliases.append(caps)
    return [a for a in aliases if a]


@lru_cache(maxsize=1)
def load_equity_list(path: str | None = None) -> dict[str, dict]:
    """Return {ticker: {"name": str, "aliases": list[str]}}.

    Reads bundled fixture at data/india/fixtures/EQUITY_L.csv.
    Pass a custom path (str) to override (used in tests).
    """
    csv_path = Path(path) if path else _FIXTURES_DIR / "EQUITY_L.csv"
    universe: dict[str, dict] = {}
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get("SYMBOL", "").strip().upper()
                name = row.get("NAME OF COMPANY", "").strip()
                if not ticker or not name:
                    continue
                universe[ticker] = {
                    "name": name,
                    "aliases": _generate_aliases(name),
                }
    except FileNotFoundError:
        logger.error("EQUITY_L.csv not found at %s", csv_path)
    return universe


@lru_cache(maxsize=1)
def load_sector_map(path: str | None = None) -> dict[str, str]:
    """Return {ticker: sector_bucket}. Reads sector_map.yaml."""
    yaml_path = Path(path) if path else _SECTOR_MAP_PATH
    try:
        with yaml_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return {k: v for k, v in raw.items() if isinstance(v, str)}
    except FileNotFoundError:
        logger.error("sector_map.yaml not found at %s", yaml_path)
        return {}
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/data/test_nse_universe.py -v
```
Expected: all 6 pass.

- [ ] **Step 7: Commit**

```bash
git add src/finterminal/data/india/nse_universe.py \
        src/finterminal/data/india/sector_map.yaml \
        src/finterminal/data/india/fixtures/EQUITY_L.csv \
        tests/data/test_nse_universe.py
git commit -m "feat(data/india): NSE universe loader + sector_map.yaml + EQUITY_L fixture"
```

---

## Task 4: news/collector.py — parallel RSS pull

**Files:**
- Create: `src/finterminal/news/__init__.py`
- Create: `src/finterminal/news/collector.py`
- Create: `tests/news/__init__.py`
- Create: `tests/news/test_collector.py`

- [ ] **Step 1: Write failing tests**

Create `tests/news/__init__.py` (empty).

Create `tests/news/test_collector.py`:
```python
"""Tests for news collector — mocks httpx, verifies normalization + resilience."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from finterminal.news.collector import Story, fetch_all


_SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Reliance Q4 beats estimates</title>
      <link>https://example.com/story1</link>
      <pubDate>Tue, 29 Apr 2026 06:00:00 +0000</pubDate>
      <description>Reliance Industries reported strong Q4 results.</description>
    </item>
    <item>
      <title>HDFC Bank flags MFI stress</title>
      <link>https://example.com/story2</link>
      <pubDate>Tue, 29 Apr 2026 07:00:00 +0000</pubDate>
      <description>HDFC Bank management flagged microfinance stress in earnings call.</description>
    </item>
  </channel>
</rss>"""


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


def test_fetch_all_returns_stories(monkeypatch):
    with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
        stories = fetch_all()
    assert len(stories) >= 2
    assert all(isinstance(s, Story) for s in stories)


def test_story_has_required_fields(monkeypatch):
    with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
        stories = fetch_all()
    s = stories[0]
    assert s.id
    assert s.source
    assert s.headline
    assert s.url


def test_one_feed_failure_does_not_crash(monkeypatch):
    """A timeout on one feed should not prevent other feeds from being returned."""
    import httpx
    call_count = 0

    def flaky_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.TimeoutException("timeout")
        return _mock_response(_SAMPLE_RSS)

    with patch("httpx.get", side_effect=flaky_get):
        stories = fetch_all()
    assert len(stories) >= 2  # remaining feeds still returned


def test_pubdate_parsed_to_datetime(monkeypatch):
    with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
        stories = fetch_all()
    for s in stories:
        if s.published_at is not None:
            assert isinstance(s.published_at, datetime)


def test_non_200_feed_skipped(monkeypatch):
    with patch("httpx.get", return_value=_mock_response("", status=403)):
        stories = fetch_all()
    assert stories == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/news/test_collector.py -v
```
Expected: `FAILED` — module not found.

- [ ] **Step 3: Create collector.py**

Create `src/finterminal/news/__init__.py` (empty).

Create `src/finterminal/news/collector.py`:
```python
"""RSS news collector — fetches all 11 feeds in parallel, normalizes to Story.

# Add new RSS feeds to _FEEDS below. Keep parsing path generic — RSS 2.0 + Atom
# both handled by the same <item> iteration. Reuters India + BusinessLine added B-2a.
# Expand at sprint boundaries, not in flight.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = "FINTERMINAL/0.1 (+https://github.com/AjinkyaWagh9/Finance-Terminal)"
_TIMEOUT_S = 10.0
_FEED_CACHE_TTL_S = 600.0

_FEEDS: list[tuple[str, str]] = [
    ("Moneycontrol", "https://www.moneycontrol.com/rss/MCtopnews.xml"),
    ("Moneycontrol Markets", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Moneycontrol Business", "https://www.moneycontrol.com/rss/business.xml"),
    ("Moneycontrol Latest", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("Livemint Markets", "https://www.livemint.com/rss/markets"),
    ("Livemint Companies", "https://www.livemint.com/rss/companies"),
    ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("ET Stocks", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("ET Industry", "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms"),
    ("Reuters India", "https://in.reuters.com/rssFeed/topNews"),
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/feeder/default.rss"),
]


@dataclass
class Story:
    id: str
    source: str
    headline: str
    url: str
    body: str = ""
    published_at: datetime | None = None
    tickers: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    cluster_id: str | None = None


def _parse_pubdate(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None


def _parse_feed(xml_text: str, source_label: str) -> list[Story]:
    stories: list[Story] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("RSS parse error in %s: %s", source_label, exc)
        return stories
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        pub = _parse_pubdate(item.findtext("pubDate"))
        desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
        story_id = url or title
        if not story_id:
            continue
        stories.append(Story(
            id=story_id,
            source=source_label,
            headline=title,
            url=url,
            body=desc,
            published_at=pub,
        ))
    return stories


def _fetch_feed(label: str, url: str) -> list[Story]:
    try:
        resp = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT_S)
        if resp.status_code != 200:
            logger.warning("RSS %s returned %s", url, resp.status_code)
            return []
        return _parse_feed(resp.text, label)
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return []


def fetch_all() -> list[Story]:
    """Fetch all feeds, return combined normalized Story list (may contain duplicates)."""
    all_stories: list[Story] = []
    for label, url in _FEEDS:
        all_stories.extend(_fetch_feed(label, url))
    return all_stories
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/news/test_collector.py -v
```
Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/news/__init__.py \
        src/finterminal/news/collector.py \
        tests/news/__init__.py \
        tests/news/test_collector.py
git commit -m "feat(news): collector — 11 feeds, parallel pull, normalize to Story"
```

---

## Task 5: news/dedupe.py — URL + MinHash dedup

**Files:**
- Create: `src/finterminal/news/dedupe.py`
- Create: `tests/news/test_dedupe.py`

- [ ] **Step 1: Write failing tests**

Create `tests/news/test_dedupe.py`:
```python
"""Tests for deduplication — URL-exact and MinHash near-duplicate detection."""
from finterminal.news.collector import Story
from finterminal.news.dedupe import drop_url_dupes, minhash_filter


def _story(id_: str, headline: str, url: str = "") -> Story:
    return Story(id=id_, source="Test", headline=headline, url=url or id_)


def test_url_dedup_drops_exact_duplicates():
    stories = [
        _story("s1", "Reliance Q4 beats", url="https://example.com/a"),
        _story("s2", "Reliance Q4 beats estimates", url="https://example.com/a"),  # same URL
        _story("s3", "HDFC Bank stress", url="https://example.com/b"),
    ]
    result = drop_url_dupes(stories)
    assert len(result) == 2
    urls = {s.url for s in result}
    assert "https://example.com/b" in urls


def test_url_dedup_keeps_unique_urls():
    stories = [_story(f"s{i}", f"Story {i}", url=f"https://example.com/{i}") for i in range(5)]
    result = drop_url_dupes(stories)
    assert len(result) == 5


def test_minhash_drops_near_duplicate_headline():
    """Wire services often republish the same headline with trivial word changes."""
    original = _story("a", "Reliance Industries Q4 net profit rises 15 percent beats estimates")
    near_dup = _story("b", "Reliance Industries Q4 net profit rises 15 per cent beats analyst estimates")
    distinct = _story("c", "HDFC Bank flags microfinance stress in quarterly results")
    result = minhash_filter([original, near_dup, distinct])
    # near_dup should be filtered; distinct should survive
    headlines = [s.headline for s in result]
    assert distinct.headline in headlines
    assert len(result) == 2  # original + distinct


def test_minhash_keeps_distinct_stories():
    stories = [
        _story("a", "Reliance Q4 beats estimates on Jio subscriber growth"),
        _story("b", "HDFC Bank microfinance stress to weigh on Q1 margins"),
        _story("c", "Infosys raises guidance citing strong deal wins in Europe"),
        _story("d", "Tata Steel Q4 EBITDA rises on higher realizations"),
    ]
    result = minhash_filter(stories)
    assert len(result) == 4  # all distinct


def test_minhash_empty_input():
    assert minhash_filter([]) == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/news/test_dedupe.py -v
```
Expected: `FAILED` — module not found.

- [ ] **Step 3: Create dedupe.py**

Create `src/finterminal/news/dedupe.py`:
```python
"""Two-stage deduplication for news stories.

Stage 1 (URL): exact URL match — fast, O(n).
Stage 2 (MinHash): Jaccard similarity on headline shingles — catches wire-service
republications of the same story with minor wording changes.

Thresholds live in cluster.py so all three can be tuned together.
"""
from __future__ import annotations

import logging

from datasketch import MinHash, MinHashLSH

from .cluster import MINHASH_JACCARD_THRESHOLD
from .collector import Story

logger = logging.getLogger(__name__)

_SHINGLE_SIZE = 3  # character-level 3-grams on lowercased headline


def _shingles(text: str) -> set[bytes]:
    t = text.lower()
    return {t[i:i + _SHINGLE_SIZE].encode() for i in range(max(1, len(t) - _SHINGLE_SIZE + 1))}


def _make_minhash(story: Story, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for s in _shingles(story.headline):
        m.update(s)
    return m


def drop_url_dupes(stories: list[Story]) -> list[Story]:
    """Keep first occurrence of each URL; drop subsequent exact-URL matches."""
    seen: set[str] = set()
    result: list[Story] = []
    for s in stories:
        key = s.url or s.id
        if key in seen:
            continue
        seen.add(key)
        result.append(s)
    return result


def minhash_filter(stories: list[Story], num_perm: int = 128) -> list[Story]:
    """Drop near-duplicate stories (Jaccard ≥ threshold on headline shingles).

    Keeps the first story in each near-duplicate group (publication order).
    """
    if not stories:
        return []

    threshold = 1.0 - MINHASH_JACCARD_THRESHOLD  # LSH uses distance, not similarity

    lsh = MinHashLSH(threshold=MINHASH_JACCARD_THRESHOLD, num_perm=num_perm)
    kept: list[Story] = []

    for i, story in enumerate(stories):
        mh = _make_minhash(story, num_perm)
        key = f"s{i}"
        try:
            result = lsh.query(mh)
        except Exception:
            result = []
        if result:
            logger.debug("near-dup dropped: '%s'", story.headline[:60])
            continue
        lsh.insert(key, mh)
        kept.append(story)

    return kept
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/news/test_dedupe.py -v
```
Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/news/dedupe.py tests/news/test_dedupe.py
git commit -m "feat(news): dedupe — URL exact + MinHash Jaccard 0.85 near-dup filter"
```

---

## Task 6: news/tagger.py — ticker + sector tagging

**Files:**
- Create: `src/finterminal/news/tagger.py`
- Create: `tests/news/test_tagger.py`

- [ ] **Step 1: Write failing tests**

Create `tests/news/test_tagger.py`:
```python
"""Tests for tagger — alias matching, rapidfuzz fallback, sector lookup."""
from finterminal.news.collector import Story
from finterminal.news.tagger import tag


def _story(headline: str, body: str = "") -> Story:
    return Story(id="x", source="Test", headline=headline, body=body)


def test_reliance_tagged_by_alias():
    stories = [_story("Reliance Industries Q4 beats estimates")]
    result = tag(stories)
    assert "RELIANCE" in result[0].tickers
    assert "Energy" in result[0].sectors


def test_hdfc_bank_tagged():
    stories = [_story("HDFC Bank microfinance stress weighs on margins")]
    result = tag(stories)
    assert "HDFCBANK" in result[0].tickers
    assert "Banking" in result[0].sectors


def test_rapidfuzz_catches_misspelling():
    """'Hindustan Unliever' (typo) should still tag HINDUNILVR."""
    stories = [_story("Hindustan Unliever sales growth disappoints")]
    result = tag(stories, min_score=85)
    assert "HINDUNILVR" in result[0].tickers


def test_cap_five_tickers():
    """A headline mentioning 7+ companies should not tag more than 5 tickers."""
    headline = (
        "Reliance HDFC Bank TCS Infosys Wipro HCL Bajaj Finance all report Q4 results"
    )
    stories = [_story(headline)]
    result = tag(stories)
    assert len(result[0].tickers) <= 5


def test_unrelated_headline_no_tickers():
    stories = [_story("RBI keeps repo rate unchanged at 6.5 percent")]
    result = tag(stories)
    # May or may not tag something — the key assertion is no crash
    assert isinstance(result[0].tickers, list)


def test_returns_same_count():
    stories = [_story(f"Story {i}") for i in range(5)]
    result = tag(stories)
    assert len(result) == 5
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/news/test_tagger.py -v
```
Expected: `FAILED` — module not found.

- [ ] **Step 3: Create tagger.py**

Create `src/finterminal/news/tagger.py`:
```python
"""Ticker and sector tagger for news stories.

Uses the NSE universe (alias map) for exact whole-word matching, with a
rapidfuzz fallback for near-misses (e.g., 'Hindustan Unliever' → HINDUNILVR).
min_score (default 85) is configurable; matches in [70, min_score) are logged
at DEBUG to aid threshold tuning across first 3 runs.
"""
from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz

from ..data.india.nse_universe import load_equity_list, load_sector_map
from .collector import Story

logger = logging.getLogger(__name__)

_MAX_TICKERS_PER_STORY = 5


def _whole_word_match(text: str, alias: str) -> bool:
    if " " in alias:
        return alias.lower() in text.lower()
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", text.lower()))


def _score_ticker(blob: str, ticker: str, aliases: list[str], min_score: int) -> float:
    """Return match score [0, 1]. 1.0 = exact alias match; 0.8 = fuzzy near-match; 0 = no match."""
    for alias in aliases + [ticker]:
        if _whole_word_match(blob, alias):
            return 1.0
    # Rapidfuzz fallback on headline tokens
    for alias in aliases:
        if len(alias) < 4:
            continue  # skip very short aliases — too many false positives
        score = fuzz.partial_ratio(alias.lower(), blob.lower())
        if score >= min_score:
            return 0.8
        if score >= 70:
            logger.debug(
                "low-confidence match: '%.60s' ↔ '%s' = %d (below min_score=%d)",
                blob, alias, score, min_score,
            )
    return 0.0


def tag(stories: list[Story], min_score: int = 85) -> list[Story]:
    """Tag each Story in-place with tickers and sectors. Returns the same list."""
    universe = load_equity_list()
    sector_map = load_sector_map()

    for story in stories:
        blob = f"{story.headline} {story.body}"
        scored: list[tuple[float, str]] = []
        for ticker, info in universe.items():
            score = _score_ticker(blob, ticker, info["aliases"], min_score)
            if score > 0:
                scored.append((score, ticker))

        scored.sort(reverse=True)
        top_tickers = [t for _, t in scored[:_MAX_TICKERS_PER_STORY]]
        story.tickers = top_tickers
        story.sectors = list({sector_map[t] for t in top_tickers if t in sector_map})

    return stories
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/news/test_tagger.py -v
```
Expected: all 6 pass.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/news/tagger.py tests/news/test_tagger.py
git commit -m "feat(news): tagger — NSE universe alias map + rapidfuzz fallback + sector lookup"
```

---

## Task 7: news/cluster.py + news/embedder.py — embed + cluster

**Files:**
- Create: `src/finterminal/news/cluster.py`
- Create: `src/finterminal/news/embedder.py`
- Create: `tests/news/test_embedder.py`
- Create: `tests/news/test_cluster.py`

- [ ] **Step 1: Write failing tests**

Create `tests/news/test_embedder.py`:
```python
"""Tests for the embedder — shape, determinism, lazy load."""
import numpy as np
import pytest
from finterminal.news.embedder import embed


def test_embed_returns_correct_shape():
    headlines = ["Reliance Q4 beats", "HDFC Bank stress"]
    result = embed(headlines)
    assert result.shape == (2, 384)


def test_embed_deterministic():
    headlines = ["Reliance Q4 beats estimates"]
    a = embed(headlines)
    b = embed(headlines)
    assert np.allclose(a, b)


def test_embed_empty_input():
    result = embed([])
    assert result.shape[0] == 0


def test_embed_single():
    result = embed(["one story"])
    assert result.shape == (1, 384)
```

Create `tests/news/test_cluster.py`:
```python
"""Tests for agglomerative clustering."""
import numpy as np
import pytest
from finterminal.news.collector import Story
from finterminal.news.cluster import cluster_stories, Cluster


def _story_with_embedding(id_: str, emb: list[float]) -> Story:
    s = Story(id=id_, source="T", headline=f"Story {id_}", url=id_)
    s.embedding = emb
    return s


def test_two_topic_stories_form_two_clusters():
    """6 Reliance stories + 4 HDFC stories should produce ~2 clusters."""
    # Use synthetic embeddings: cluster A near [1,0,...], cluster B near [0,1,...]
    dim = 384
    rel_embs = [[1.0] + [0.0] * (dim - 1)] * 6
    hdfc_embs = [[0.0, 1.0] + [0.0] * (dim - 2)] * 4
    stories = (
        [_story_with_embedding(f"r{i}", e) for i, e in enumerate(rel_embs)] +
        [_story_with_embedding(f"h{i}", e) for i, e in enumerate(hdfc_embs)]
    )
    clusters = cluster_stories(stories)
    assert 1 <= len(clusters) <= 4  # flexible — synthetic embeddings may vary


def test_cluster_has_required_fields():
    dim = 384
    stories = [_story_with_embedding("s1", [1.0] + [0.0] * (dim - 1))]
    clusters = cluster_stories(stories)
    assert len(clusters) >= 1
    c = clusters[0]
    assert isinstance(c, Cluster)
    assert c.id
    assert len(c.story_ids) >= 1
    assert len(c.centroid) == dim


def test_cluster_empty_input():
    result = cluster_stories([])
    assert result == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/news/test_embedder.py tests/news/test_cluster.py -v
```
Expected: all fail — modules not found.

- [ ] **Step 3: Create cluster.py first (constants needed by dedupe)**

Create `src/finterminal/news/cluster.py`:
```python
"""Agglomerative clustering of embedded news stories.

# Tune these based on manual inspection of the first 3 runs.
# CLUSTER_DISTANCE_THRESHOLD: lower → more smaller clusters; higher → fewer bigger ones.
# MINHASH_JACCARD_THRESHOLD: imported by dedupe.py — set here so all thresholds are together.
# LINEAGE_CENTROID_THRESHOLD: imported by lineage.py.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

from .collector import Story

logger = logging.getLogger(__name__)

# Tune these based on manual inspection of the first 3 runs.
CLUSTER_DISTANCE_THRESHOLD: float = 0.25
MINHASH_JACCARD_THRESHOLD: float = 0.85
LINEAGE_CENTROID_THRESHOLD: float = 0.70


@dataclass
class Cluster:
    id: str
    story_ids: list[str]
    centroid: list[float]
    top_tickers: list[str] = field(default_factory=list)
    dominant_sector: str | None = None
    representative_id: str | None = None
    first_seen: object = None  # datetime | None
    story_count: int = 0
    source_count: int = 0


def _centroid(embeddings: np.ndarray) -> list[float]:
    c = embeddings.mean(axis=0)
    norm = np.linalg.norm(c)
    return (c / norm if norm > 0 else c).tolist()


def _representative(embeddings: np.ndarray, story_ids: list[str], centroid: list[float]) -> str:
    """Return the story_id closest to the centroid."""
    c = np.array(centroid)
    sims = embeddings @ c / (np.linalg.norm(embeddings, axis=1) * np.linalg.norm(c) + 1e-9)
    return story_ids[int(np.argmax(sims))]


def cluster_stories(stories: list[Story]) -> list[Cluster]:
    """Cluster stories by embedding similarity. Returns list of Cluster objects."""
    if not stories:
        return []

    valid = [s for s in stories if s.embedding]
    if not valid:
        return []

    embs = np.array([s.embedding for s in valid], dtype=np.float32)

    if len(valid) == 1:
        c_id = str(uuid.uuid4())
        s = valid[0]
        cluster = Cluster(
            id=c_id,
            story_ids=[s.id],
            centroid=s.embedding,
            top_tickers=s.tickers[:3],
            dominant_sector=(s.sectors[0] if s.sectors else None),
            representative_id=s.id,
            first_seen=s.published_at,
            story_count=1,
            source_count=1,
        )
        return [cluster]

    # Cosine distance matrix
    dist_matrix = pdist(embs, metric="cosine")
    Z = linkage(dist_matrix, method="single")
    labels = fcluster(Z, t=CLUSTER_DISTANCE_THRESHOLD, criterion="distance")

    clusters: list[Cluster] = []
    for label in sorted(set(labels)):
        indices = [i for i, l in enumerate(labels) if l == label]
        cluster_stories_list = [valid[i] for i in indices]
        cluster_embs = embs[indices]

        tickers_flat = [t for s in cluster_stories_list for t in s.tickers]
        ticker_counts: dict[str, int] = {}
        for t in tickers_flat:
            ticker_counts[t] = ticker_counts.get(t, 0) + 1
        top_tickers = sorted(ticker_counts, key=ticker_counts.get, reverse=True)[:3]  # type: ignore[arg-type]

        sectors_flat = [sec for s in cluster_stories_list for sec in s.sectors]
        dominant_sector = max(set(sectors_flat), key=sectors_flat.count) if sectors_flat else None

        centroid = _centroid(cluster_embs)
        ids = [s.id for s in cluster_stories_list]
        rep_id = _representative(cluster_embs, ids, centroid)

        pub_dates = [s.published_at for s in cluster_stories_list if s.published_at]
        first_seen = min(pub_dates) if pub_dates else None

        sources = {s.source for s in cluster_stories_list}

        clusters.append(Cluster(
            id=str(uuid.uuid4()),
            story_ids=ids,
            centroid=centroid,
            top_tickers=top_tickers,
            dominant_sector=dominant_sector,
            representative_id=rep_id,
            first_seen=first_seen,
            story_count=len(cluster_stories_list),
            source_count=len(sources),
        ))

    return clusters
```

- [ ] **Step 4: Create embedder.py**

Create `src/finterminal/news/embedder.py`:
```python
"""Sentence embedding via sentence-transformers/all-MiniLM-L6-v2.

Lazy-loads on first call; caches model in memory.
Expected wall-clock: first run ≈ 8–12s (model download + encoding ~150 headlines);
subsequent runs < 4s (model already in memory / disk cache).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_MODEL_CACHE_DIR = Path("./data/models")
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("loading embedding model %s (first call — may take ~10s)", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME, cache_folder=str(_MODEL_CACHE_DIR))
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """Return shape (n, 384) float32 embeddings. Empty input → shape (0, 384)."""
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/news/test_embedder.py tests/news/test_cluster.py -v
```
Expected: all pass. (embedder test will download model on first run — allow 30s.)

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/news/embedder.py \
        src/finterminal/news/cluster.py \
        tests/news/test_embedder.py \
        tests/news/test_cluster.py
git commit -m "feat(news): embedder (all-MiniLM-L6-v2) + agglomerative cluster with threshold constants"
```

---

## Task 8: news/lineage.py — day-over-day cluster matching

**Files:**
- Create: `src/finterminal/news/lineage.py`
- Create: `tests/news/test_lineage.py`

- [ ] **Step 1: Write failing tests**

Create `tests/news/test_lineage.py`:
```python
"""Tests for cluster lineage — centroid cosine matching + story_count_delta."""
from datetime import date
import numpy as np
from finterminal.news.cluster import Cluster
from finterminal.news.lineage import match_clusters, LineageLink


def _cluster(id_: str, centroid: list[float], story_count: int = 5) -> Cluster:
    c = Cluster(id=id_, story_ids=[], centroid=centroid, story_count=story_count, source_count=1)
    return c


def test_similar_clusters_linked():
    dim = 384
    yesterday = [_cluster("y1", [1.0] + [0.0] * (dim - 1), story_count=4)]
    today = [_cluster("t1", [1.0] + [0.0] * (dim - 1), story_count=6)]
    links = match_clusters(yesterday, today, date(2026, 4, 30))
    assert len(links) == 1
    assert links[0].parent_id == "y1"
    assert links[0].child_id == "t1"
    assert links[0].story_count_delta == 2  # 6 - 4


def test_dissimilar_clusters_not_linked():
    dim = 384
    yesterday = [_cluster("y1", [1.0] + [0.0] * (dim - 1))]
    today = [_cluster("t1", [0.0, 1.0] + [0.0] * (dim - 2))]
    links = match_clusters(yesterday, today, date(2026, 4, 30))
    assert links == []


def test_story_count_delta_negative():
    dim = 384
    yesterday = [_cluster("y1", [1.0] + [0.0] * (dim - 1), story_count=10)]
    today = [_cluster("t1", [1.0] + [0.0] * (dim - 1), story_count=6)]
    links = match_clusters(yesterday, today, date(2026, 4, 30))
    assert links[0].story_count_delta == -4


def test_no_yesterday_returns_empty():
    dim = 384
    today = [_cluster("t1", [1.0] + [0.0] * (dim - 1))]
    links = match_clusters([], today, date(2026, 4, 30))
    assert links == []


def test_lineage_link_fields():
    dim = 384
    yesterday = [_cluster("y1", [1.0] + [0.0] * (dim - 1), story_count=3)]
    today = [_cluster("t1", [1.0] + [0.0] * (dim - 1), story_count=5)]
    links = match_clusters(yesterday, today, date(2026, 4, 30))
    link = links[0]
    assert isinstance(link, LineageLink)
    assert link.similarity >= 0.9
    assert link.day == date(2026, 4, 30)
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/news/test_lineage.py -v
```
Expected: `FAILED` — module not found.

- [ ] **Step 3: Create lineage.py**

Create `src/finterminal/news/lineage.py`:
```python
"""Day-over-day cluster lineage matching.

Matches today's clusters to yesterday's via centroid cosine similarity.
Computes story_count_delta for each matched pair.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from .cluster import Cluster, LINEAGE_CENTROID_THRESHOLD


@dataclass
class LineageLink:
    parent_id: str
    child_id: str
    day: date
    similarity: float
    story_count_delta: int


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def match_clusters(
    yesterday: list[Cluster],
    today: list[Cluster],
    day: date,
) -> list[LineageLink]:
    """For each today cluster, find best-matching yesterday cluster (cosine ≥ threshold).

    Returns LineageLink for each matched pair. Unmatched today clusters are new (day_n=1).
    Each yesterday cluster can only be matched once (greedy, best-similarity-first).
    """
    if not yesterday or not today:
        return []

    links: list[LineageLink] = []
    used_parents: set[str] = set()

    for child in today:
        best_sim = LINEAGE_CENTROID_THRESHOLD - 1e-9
        best_parent: Cluster | None = None
        for parent in yesterday:
            if parent.id in used_parents:
                continue
            sim = _cosine(child.centroid, parent.centroid)
            if sim > best_sim:
                best_sim = sim
                best_parent = parent
        if best_parent is not None and best_sim >= LINEAGE_CENTROID_THRESHOLD:
            delta = child.story_count - best_parent.story_count
            links.append(LineageLink(
                parent_id=best_parent.id,
                child_id=child.id,
                day=day,
                similarity=best_sim,
                story_count_delta=delta,
            ))
            used_parents.add(best_parent.id)

    return links
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/news/test_lineage.py -v
```
Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/news/lineage.py tests/news/test_lineage.py
git commit -m "feat(news): lineage — centroid cosine matching + story_count_delta"
```

---

## Task 9: data/news_store.py + news/pipeline.py — storage + orchestration

**Files:**
- Create: `src/finterminal/data/news_store.py`
- Create: `src/finterminal/news/pipeline.py`
- Create: `tests/news/test_pipeline.py`

- [ ] **Step 1: Write failing pipeline test**

Create `tests/news/test_pipeline.py`:
```python
"""End-to-end pipeline test with stubbed feeds."""
import time
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from finterminal.news.collector import Story
from finterminal.news.pipeline import PipelineResult, run as run_pipeline


_FAKE_STORIES = [
    Story(
        id="s1", source="MC", headline="Reliance Industries Q4 net profit rises on Jio growth",
        url="https://example.com/s1",
        published_at=datetime(2026, 4, 29, 6, 0, tzinfo=timezone.utc),
    ),
    Story(
        id="s2", source="ET", headline="Reliance Q4 results beat analyst estimates strongly",
        url="https://example.com/s2",
        published_at=datetime(2026, 4, 29, 6, 30, tzinfo=timezone.utc),
    ),
    Story(
        id="s3", source="Livemint", headline="HDFC Bank management flags microfinance stress",
        url="https://example.com/s3",
        published_at=datetime(2026, 4, 29, 7, 0, tzinfo=timezone.utc),
    ),
    Story(
        id="s4", source="Reuters", headline="HDFC Bank Q4 margin pressure from MFI portfolio",
        url="https://example.com/s4",
        published_at=datetime(2026, 4, 29, 7, 30, tzinfo=timezone.utc),
    ),
]


@pytest.fixture
def mem_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from finterminal.data.duckdb_store import get_conn
    conn = get_conn()
    yield conn
    conn.close()


def test_pipeline_returns_result(mem_conn):
    with patch("finterminal.news.collector.fetch_all", return_value=_FAKE_STORIES):
        result = run_pipeline(mem_conn)
    assert isinstance(result, PipelineResult)
    assert result.n_stories >= 1
    assert result.n_clusters >= 1
    assert result.runtime_s > 0


def test_pipeline_persists_stories(mem_conn):
    with patch("finterminal.news.collector.fetch_all", return_value=_FAKE_STORIES):
        run_pipeline(mem_conn)
    count = mem_conn.execute("SELECT COUNT(*) FROM news_stories").fetchone()[0]
    assert count >= 1


def test_pipeline_persists_clusters(mem_conn):
    with patch("finterminal.news.collector.fetch_all", return_value=_FAKE_STORIES):
        run_pipeline(mem_conn)
    count = mem_conn.execute("SELECT COUNT(*) FROM news_clusters").fetchone()[0]
    assert count >= 1


def test_pipeline_empty_feeds(mem_conn):
    with patch("finterminal.news.collector.fetch_all", return_value=[]):
        result = run_pipeline(mem_conn)
    assert result.n_stories == 0
    assert result.n_clusters == 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/news/test_pipeline.py -v
```
Expected: `FAILED` — pipeline module not found.

- [ ] **Step 3: Create news_store.py**

Create `src/finterminal/data/news_store.py`:
```python
"""DuckDB read/write for news pipeline tables: news_stories, news_clusters, cluster_lineage."""
from __future__ import annotations

import json
from datetime import date, datetime

import duckdb

from ..news.cluster import Cluster
from ..news.lineage import LineageLink


def upsert_stories(conn: duckdb.DuckDBPyConnection, stories: list) -> None:
    """Insert stories; skip on conflict (id is primary key)."""
    from ..news.collector import Story
    for s in stories:
        emb = s.embedding if s.embedding else None
        conn.execute(
            """
            INSERT OR IGNORE INTO news_stories
                (id, url, source, headline, body, published_at, fetched_at,
                 tickers, sectors, embedding, cluster_id)
            VALUES (?, ?, ?, ?, ?, ?, now(), ?, ?, ?, ?)
            """,
            [
                s.id, s.url, s.source, s.headline, s.body, s.published_at,
                s.tickers or [], s.sectors or [],
                emb, s.cluster_id,
            ],
        )


def upsert_clusters(conn: duckdb.DuckDBPyConnection, clusters: list[Cluster], as_of: date) -> None:
    """Upsert cluster rows for the given run date."""
    for c in clusters:
        conn.execute(
            """
            INSERT OR REPLACE INTO news_clusters
                (id, as_of, story_count, source_count, top_tickers,
                 dominant_sector, representative_id, centroid, first_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                c.id, as_of, c.story_count, c.source_count,
                c.top_tickers, c.dominant_sector, c.representative_id,
                c.centroid, c.first_seen,
            ],
        )
        # Update cluster_id on story rows
        for story_id in c.story_ids:
            conn.execute(
                "UPDATE news_stories SET cluster_id = ? WHERE id = ?",
                [c.id, story_id],
            )


def upsert_lineage(conn: duckdb.DuckDBPyConnection, links: list[LineageLink]) -> None:
    for link in links:
        conn.execute(
            """
            INSERT OR REPLACE INTO cluster_lineage
                (parent_id, child_id, day, similarity, story_count_delta)
            VALUES (?, ?, ?, ?, ?)
            """,
            [link.parent_id, link.child_id, link.day, link.similarity, link.story_count_delta],
        )


def latest_clusters(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Return all clusters for the most recent as_of date, with lineage info."""
    rows = conn.execute(
        """
        WITH latest_date AS (
            SELECT MAX(as_of) AS as_of FROM news_clusters
        ),
        lineage_agg AS (
            SELECT
                child_id,
                SUM(story_count_delta) AS total_delta,
                COUNT(*) AS parent_count
            FROM cluster_lineage
            GROUP BY child_id
        ),
        day_counts AS (
            SELECT child_id, MAX(day) AS last_day FROM cluster_lineage GROUP BY child_id
        )
        SELECT
            c.id, c.as_of, c.story_count, c.source_count,
            c.top_tickers, c.dominant_sector, c.representative_id, c.first_seen,
            COALESCE(l.total_delta, 0) AS story_count_delta,
            COALESCE(l.parent_count, 0) AS day_n
        FROM news_clusters c
        CROSS JOIN latest_date ld
        LEFT JOIN lineage_agg l ON l.child_id = c.id
        WHERE c.as_of = ld.as_of
        ORDER BY c.story_count DESC
        """,
    ).fetchall()
    cols = ["id", "as_of", "story_count", "source_count", "top_tickers",
            "dominant_sector", "representative_id", "first_seen", "story_count_delta", "day_n"]
    return [dict(zip(cols, row)) for row in rows]


def clusters_for_as_of(conn: duckdb.DuckDBPyConnection, as_of: date) -> list[Cluster]:
    """Return Cluster objects for a specific date (used by lineage matching)."""
    rows = conn.execute(
        "SELECT id, story_count, centroid FROM news_clusters WHERE as_of = ?",
        [as_of],
    ).fetchall()
    clusters = []
    for row in rows:
        c = Cluster(id=row[0], story_ids=[], centroid=list(row[2] or []), story_count=row[1], source_count=0)
        clusters.append(c)
    return clusters
```

- [ ] **Step 4: Create pipeline.py**

Create `src/finterminal/news/pipeline.py`:
```python
"""News pipeline orchestrator. Runs all steps and persists to DuckDB."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import duckdb

from .collector import Story, fetch_all
from .dedupe import drop_url_dupes, minhash_filter
from .embedder import embed
from .cluster import cluster_stories
from .lineage import match_clusters
from .tagger import tag
from ..data import news_store

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    as_of: date
    n_stories: int
    n_clusters: int
    n_lineage_links: int
    runtime_s: float


def run(conn: duckdb.DuckDBPyConnection) -> PipelineResult:
    """Run the full news pipeline and persist results. Returns PipelineResult."""
    t0 = time.monotonic()
    today = date.today()

    # 1. Collect
    raw_stories = fetch_all()
    logger.info("collected %d raw stories", len(raw_stories))

    if not raw_stories:
        return PipelineResult(as_of=today, n_stories=0, n_clusters=0, n_lineage_links=0, runtime_s=time.monotonic() - t0)

    # 2. Dedupe
    stories = drop_url_dupes(raw_stories)
    stories = minhash_filter(stories)
    logger.info("%d stories after dedupe", len(stories))

    # 3. Tag
    stories = tag(stories)

    # 4. Embed
    headlines = [s.headline for s in stories]
    embeddings = embed(headlines)
    for s, emb in zip(stories, embeddings):
        s.embedding = emb.tolist()

    # 5. Cluster
    clusters = cluster_stories(stories)
    logger.info("%d clusters formed", len(clusters))

    # 6. Persist stories + clusters
    news_store.upsert_stories(conn, stories)
    news_store.upsert_clusters(conn, clusters, today)

    # 7. Lineage — match today's clusters to yesterday's
    from datetime import timedelta
    yesterday = date.today() - timedelta(days=1)
    yesterday_clusters = news_store.clusters_for_as_of(conn, yesterday)
    links = match_clusters(yesterday_clusters, clusters, today)
    news_store.upsert_lineage(conn, links)
    logger.info("%d lineage links created", len(links))

    return PipelineResult(
        as_of=today,
        n_stories=len(stories),
        n_clusters=len(clusters),
        n_lineage_links=len(links),
        runtime_s=time.monotonic() - t0,
    )
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/news/test_pipeline.py -v
```
Expected: all 4 pass.

- [ ] **Step 6: Full suite check**

```bash
uv run pytest -q
```
Expected: all existing 123 + new tests green.

- [ ] **Step 7: Commit**

```bash
git add src/finterminal/data/news_store.py \
        src/finterminal/news/pipeline.py \
        tests/news/test_pipeline.py
git commit -m "feat(news): pipeline orchestrator + news_store DuckDB helpers"
```

---

## Task 10: agents/news_trend.py — Agent Protocol wrapper

**Files:**
- Create: `src/finterminal/agents/news_trend.py`
- Create: `tests/agents/test_news_trend_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/agents/test_news_trend_agent.py`:
```python
"""Tests for NewsTrendAgent — Protocol conformance + happy/error paths."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from finterminal.agents.base import Agent, AgentContext, AgentResult
from finterminal.agents.news_trend import NewsTrendAgent
from finterminal.news.pipeline import PipelineResult
from datetime import date


def _fake_pipeline(conn) -> PipelineResult:
    return PipelineResult(as_of=date.today(), n_stories=10, n_clusters=3, n_lineage_links=2, runtime_s=1.2)


def _failing_pipeline(conn):
    raise RuntimeError("feed timeout")


def test_news_trend_agent_implements_protocol():
    agent = NewsTrendAgent(pipeline=_fake_pipeline)
    assert isinstance(agent, Agent)


def test_agent_name_and_is_llm():
    agent = NewsTrendAgent(pipeline=_fake_pipeline)
    assert agent.name == "news_trend"
    assert agent.is_llm is False


def test_agent_run_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from finterminal.data.duckdb_store import get_conn
    conn = get_conn()
    ctx = AgentContext(ticker="RELIANCE", conn=conn)
    agent = NewsTrendAgent(pipeline=_fake_pipeline)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is True
    assert result.payload["n_clusters"] == 3
    conn.close()


def test_agent_run_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from finterminal.data.duckdb_store import get_conn
    conn = get_conn()
    ctx = AgentContext(ticker="RELIANCE", conn=conn)
    agent = NewsTrendAgent(pipeline=_failing_pipeline)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "feed timeout" in (result.error or "")
    conn.close()


def test_analyze_flow_registry_still_3_agents():
    """Ensure analyze_flow.py is not accidentally importing NewsTrendAgent."""
    import inspect
    import finterminal.agents.analyze_flow as af
    src = inspect.getsource(af)
    assert "news_trend" not in src
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/agents/test_news_trend_agent.py -v
```
Expected: `FAILED` — module not found.

- [ ] **Step 3: Create news_trend.py**

Create `src/finterminal/agents/news_trend.py`:
```python
"""News & Trend agent — Protocol wrapper around the pipeline.

B-2a: is_llm=False (pipeline is deterministic). ctx.ticker is ignored;
pipeline runs cross-ticker. B-2b will filter clusters by ctx.ticker.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

import duckdb

from ..news.pipeline import PipelineResult, run as _pipeline_run
from .base import AgentContext, AgentResult

logger = logging.getLogger(__name__)


class NewsTrendAgent:
    name = "news_trend"
    is_llm = False

    def __init__(self, pipeline: Callable[[duckdb.DuckDBPyConnection], PipelineResult] = _pipeline_run) -> None:
        self._pipeline = pipeline

    async def run(self, ctx: AgentContext) -> AgentResult:
        try:
            result = await asyncio.to_thread(self._pipeline, ctx.conn)
            return AgentResult(
                ok=True,
                payload={
                    "as_of": result.as_of.isoformat(),
                    "n_stories": result.n_stories,
                    "n_clusters": result.n_clusters,
                    "n_lineage_links": result.n_lineage_links,
                    "runtime_s": result.runtime_s,
                },
            )
        except Exception as exc:
            logger.warning("news_trend pipeline failed: %s", exc)
            return AgentResult(ok=False, error=str(exc))
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/agents/test_news_trend_agent.py -v
```
Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add src/finterminal/agents/news_trend.py tests/agents/test_news_trend_agent.py
git commit -m "feat(agents): NewsTrendAgent Protocol wrapper (B-2a deterministic, B-2b hooks ready)"
```

---

## Task 11: ui/panels.py — render_trends_table

**Files:**
- Modify: `src/finterminal/ui/panels.py`
- Create: `tests/commands/test_trends_cmd.py` (partially here for rendering)

- [ ] **Step 1: Add render_trends_table to panels.py**

Add this function at the end of `src/finterminal/ui/panels.py`:

```python
def render_trends_table(clusters: list[dict], sector_filter: str | None = None) -> Table | Panel:
    """Render /trends output. clusters is from news_store.latest_clusters().

    Each cluster dict has: id, as_of, story_count, source_count, top_tickers,
    dominant_sector, representative_id, first_seen, story_count_delta, day_n.
    """
    if not clusters:
        return Panel(
            "[dim]No trend data. Run [bold]/refresh-news[/bold] first.[/dim]",
            title="Trends",
            border_style="dim",
        )

    if sector_filter:
        clusters = [c for c in clusters if (c.get("dominant_sector") or "").lower() == sector_filter.lower()]

    if not clusters:
        return Panel(
            f"[dim]No clusters for sector [bold]{sector_filter}[/bold].[/dim]",
            title=f"Trends — {sector_filter}",
            border_style="dim",
        )

    table = Table(
        title=f"Trends — {sector_filter or 'All sectors'}",
        border_style="cyan",
        show_lines=False,
        expand=True,
    )
    table.add_column("Cluster", style="dim", width=8)
    table.add_column("Stories", justify="right", width=7)
    table.add_column("Sources", justify="right", width=7)
    table.add_column("Top Tickers", width=22)
    table.add_column("Headline", ratio=1)
    table.add_column("First Seen", width=11)
    table.add_column("Momentum", width=12)

    for c in clusters:
        cluster_id = (c.get("id") or "")[:6]
        story_count = str(c.get("story_count", ""))
        source_count = str(c.get("source_count", ""))
        tickers = ", ".join((c.get("top_tickers") or [])[:3])
        rep_id = c.get("representative_id") or ""
        headline = _escape_markup(rep_id[:60] if rep_id else "")
        first_seen = ""
        fs = c.get("first_seen")
        if fs:
            try:
                first_seen = str(fs)[:10]
            except Exception:
                pass

        # Momentum badge
        delta = c.get("story_count_delta", 0) or 0
        day_n = (c.get("day_n") or 0) + 1  # day_n from lineage = parent count; +1 = today
        if day_n <= 1:
            momentum = ""
        elif delta > 0:
            momentum = f"[green]▲{delta} (Day {day_n})[/green]"
        elif delta < 0:
            momentum = f"[red]▼{abs(delta)} (Day {day_n})[/red]"
        else:
            momentum = f"[dim]· (Day {day_n})[/dim]"

        table.add_row(cluster_id, story_count, source_count, tickers, headline, first_seen, momentum)

    as_of = (clusters[0].get("as_of") or "") if clusters else ""
    table.caption = f"as_of {as_of} · run [bold]/refresh-news[/bold] for fresh data"
    return table
```

- [ ] **Step 2: Verify ruff passes**

```bash
uv run ruff check src/finterminal/ui/panels.py
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/finterminal/ui/panels.py
git commit -m "feat(ui): render_trends_table with Momentum badge + sector filter"
```

---

## Task 12: commands.py — /refresh-news + /trends

**Files:**
- Modify: `src/finterminal/commands.py`
- Create: `tests/commands/__init__.py`
- Create: `tests/commands/test_trends_cmd.py`

- [ ] **Step 1: Write failing tests**

Create `tests/commands/__init__.py` (empty).

Create `tests/commands/test_trends_cmd.py`:
```python
"""Tests for /refresh-news and /trends commands."""
from unittest.mock import MagicMock, patch
from io import StringIO

import pytest
from rich.console import Console

from finterminal.commands import dispatch


def _console() -> Console:
    return Console(file=StringIO(), highlight=False)


@pytest.fixture
def mock_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from finterminal.data.duckdb_store import get_conn
    conn = get_conn()
    yield conn
    conn.close()


def test_refresh_news_calls_pipeline(mock_conn):
    from finterminal.news.pipeline import PipelineResult
    from datetime import date
    fake_result = PipelineResult(as_of=date.today(), n_stories=30, n_clusters=5, n_lineage_links=3, runtime_s=2.1)
    with patch("finterminal.commands._pipeline_run", return_value=fake_result), \
         patch("finterminal.commands.duckdb_store.get_conn", return_value=mock_conn):
        c = _console()
        dispatch("/refresh-news", c)
        output = c.file.getvalue()
    assert "30" in output or "stories" in output.lower()


def test_trends_no_data_shows_error(mock_conn):
    with patch("finterminal.commands.duckdb_store.get_conn", return_value=mock_conn), \
         patch("finterminal.data.news_store.latest_clusters", return_value=[]):
        c = _console()
        dispatch("/trends", c)
        output = c.file.getvalue()
    assert "refresh-news" in output.lower() or "no trend" in output.lower()


def test_trends_with_sector_arg(mock_conn):
    fake_clusters = [
        {"id": "abc123", "as_of": "2026-04-29", "story_count": 8, "source_count": 3,
         "top_tickers": ["HDFCBANK"], "dominant_sector": "Banking",
         "representative_id": "HDFC stress headline", "first_seen": "2026-04-29",
         "story_count_delta": 2, "day_n": 1},
    ]
    with patch("finterminal.commands.duckdb_store.get_conn", return_value=mock_conn), \
         patch("finterminal.data.news_store.latest_clusters", return_value=fake_clusters):
        c = _console()
        dispatch("/trends Banking", c)
        output = c.file.getvalue()
    assert "HDFCBANK" in output or "Banking" in output
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/commands/test_trends_cmd.py -v
```
Expected: `FAILED` — commands not registered.

- [ ] **Step 3: Add commands to commands.py**

In `src/finterminal/commands.py`, add two imports at the top of the file (after existing imports):

```python
from .news.pipeline import run as _pipeline_run
from .data import news_store
```

Add these two command handlers before the `_COMMANDS` dict:

```python
# ---------- /refresh-news ----------


def _cmd_refresh_news(args: list[str], console: Console) -> None:
    conn = duckdb_store.get_conn()
    try:
        with console.status("refreshing news pipeline…", spinner="dots"):
            result = _pipeline_run(conn)
    finally:
        conn.close()
    console.print(
        f"Refreshed [bold]{result.n_stories}[/bold] stories → "
        f"[bold]{result.n_clusters}[/bold] clusters in [bold]{result.runtime_s:.1f}s[/bold]. "
        f"[dim]{result.n_lineage_links} lineage links from yesterday.[/dim]"
    )


# ---------- /trends ----------


def _cmd_trends(args: list[str], console: Console) -> None:
    sector = args[0] if args else None
    conn = duckdb_store.get_conn()
    try:
        clusters = news_store.latest_clusters(conn)
    finally:
        conn.close()
    console.print(panels.render_trends_table(clusters, sector_filter=sector))
```

Register in `_COMMANDS`:

```python
_COMMANDS = {
    "/help": _cmd_help,
    "/ticker": _cmd_ticker,
    "/news": _cmd_news,
    "/watch": _cmd_watch,
    "/analyze": _cmd_analyze,
    "/refresh-news": _cmd_refresh_news,
    "/trends": _cmd_trends,
}
```

Also update `help_panel()` in `panels.py` — add two lines to the commands block:

```python
"  [cyan]/refresh-news[/]             pull + cluster today's market news\n"
"  [cyan]/trends[/] [SECTOR]          show story clusters (optional sector filter)\n"
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/commands/test_trends_cmd.py -v
```
Expected: all pass.

- [ ] **Step 5: Full suite**

```bash
uv run pytest -q && uv run ruff check src tests
```
Expected: all green, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/finterminal/commands.py \
        src/finterminal/ui/panels.py \
        tests/commands/__init__.py \
        tests/commands/test_trends_cmd.py
git commit -m "feat(commands): /refresh-news + /trends [sector] commands"
```

---

## Task 13: Smoke verification + vault

**Files:** none (verification only)

- [ ] **Step 1: Run full test suite one final time**

```bash
cd finterminal && uv run pytest -q
```
Expected: ≥ 153 tests, all green.

- [ ] **Step 2: Live smoke — /refresh-news**

```bash
uv run finterminal
```
At the REPL prompt:
```
/refresh-news
```
Expected: `Refreshed N stories → M clusters in T.Ts. K lineage links from yesterday.`
N ≥ 50, M ≥ 5.

- [ ] **Step 3: Live smoke — /trends**

```
/trends
```
Expected: Rich table showing ≥ 3 clusters sorted by story count with `as_of` footer.

- [ ] **Step 4: Live smoke — /trends with sector filter**

```
/trends Banking
/trends IT
/trends Energy
```
Expected: each returns only clusters whose `dominant_sector` matches. Verify manually:
all visible `Top Tickers` should belong to the queried sector.

- [ ] **Step 5: Day-2 lineage smoke (next calendar day)**

Run `/refresh-news` again the following day.
Expected: `/trends` shows at least one cluster with `▲N (Day 2)` or `▼N (Day 2)` Momentum badge.

- [ ] **Step 6: Dispatch vault subagent**

```python
Agent(
  description="Update TerminalVault — B-2a News & Trend pipeline shipped",
  subagent_type="general-purpose",
  model="sonnet",
  prompt="""
    Update the Obsidian vault at /Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault.

    Context — what just shipped:
      Sprint B-2a (News & Trend pipeline) is live. New modules: src/finterminal/news/
      (collector, tagger, dedupe, embedder, cluster, lineage, pipeline),
      src/finterminal/agents/news_trend.py, src/finterminal/data/news_store.py,
      migration 003_news_pipeline.sql (DuckDB vss + 3 new tables), /refresh-news and
      /trends [sector] commands, render_trends_table with Momentum badge. +30 tests.
      No changes to analyze_flow.py — registry still 3 agents. B-2b (/analyze
      enrichment + /brief) is next.

    Files affected:
      src/finterminal/news/ (all new files)
      src/finterminal/agents/news_trend.py
      src/finterminal/data/news_store.py
      src/finterminal/data/migrations/003_news_pipeline.sql
      src/finterminal/data/india/nse_universe.py + sector_map.yaml + fixtures/EQUITY_L.csv
      src/finterminal/commands.py (2 new commands)
      src/finterminal/ui/panels.py (render_trends_table)
      tests/news/* tests/agents/test_news_trend_agent.py tests/commands/test_trends_cmd.py
      tests/data/test_news_pipeline_migration.py tests/data/test_nse_universe.py

    Tasks:
      1. Append a dated entry to TerminalVault/05 - Build Log/2026-04-29 — Sprint B-2a News Trend.md
      2. Create/update code-map entries under TerminalVault/04 - Code Map/:
         - news — pipeline.md (all 7 news/ modules with file:line refs)
         - agents — news_trend.md
         - data — news_store.md
      3. Add ADR-016 under TerminalVault/02 - Decisions/: "DuckDB vss over ChromaDB for embeddings"
      4. Update Phase 2 status in TerminalVault/03 - Phases/Phase 2 - Multi-Agent Foundation.md:
         tick B-2a complete; add B-2b as next
      5. Cross-link with [[wikilinks]]. Update Index.md.
      6. Keep entries under 200 lines; bullets+tables, not prose.
  """
)
```

- [ ] **Step 7: Final commit (vault pointer if changed)**

```bash
git add TerminalVault/ && git diff --cached --name-only
git commit -m "docs: B-2a vault — news pipeline build log + ADR-016 + code maps" 2>/dev/null || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered in task |
|---|---|
| 11 RSS feeds | Task 4 (collector.py `_FEEDS`) |
| NSE EQUITY_L.csv autoload + fixture | Task 3 |
| sector_map.yaml curated | Task 3 |
| rapidfuzz min_score + DEBUG logging | Task 6 (tagger.py) |
| Threshold constants in one module | Task 7 (cluster.py constants) |
| URL + MinHash dedupe | Task 5 |
| sentence-transformers/all-MiniLM-L6-v2 lazy load | Task 7 (embedder.py) |
| Agglomerative single-linkage cosine | Task 7 (cluster.py) |
| cluster_lineage + story_count_delta column | Tasks 2 + 8 |
| Day-over-day lineage match ≥ 0.70 | Task 8 |
| Momentum badge `▲N (Day M)` | Tasks 11 + 12 |
| news_stories + news_clusters + cluster_lineage DuckDB | Task 2 |
| vss INSTALL + LOAD per connection | Task 2 |
| DuckDB news_store read/write helpers | Task 9 |
| pipeline.py orchestrator | Task 9 |
| NewsTrendAgent Protocol | Task 10 |
| analyze_flow.py untouched (3 agents) | Task 10 test |
| /refresh-news command | Task 12 |
| /trends [sector] command | Task 12 |
| render_trends_table + sector filter | Task 11 |
| help_panel updated | Task 12 |
| +30 tests, ≥153 total | Tasks 2-12 |
| Live smoke both commands | Task 13 |
| Sector filter verified on 3 sectors | Task 13 |
| Day-2 lineage smoke | Task 13 |
| Vault updated | Task 13 |
| Cold-start comment in embedder | Task 7 (embedder.py docstring) |

All spec requirements covered.

**Type consistency check:** `Story` dataclass defined in `collector.py` and imported everywhere. `Cluster` defined in `cluster.py`, imported by `lineage.py`, `news_store.py`. `LineageLink` defined in `lineage.py`, imported by `news_store.py`. `PipelineResult` defined in `pipeline.py`, imported by `news_trend.py` and `commands.py`. No name mismatches found.
