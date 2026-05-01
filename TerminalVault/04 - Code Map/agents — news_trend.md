# Code Map — agents/news_trend.py

> Back to [[Index]] | See also [[news — pipeline]] · [[data — news_store]] · [[agents — analyze_flow]]

**File:** `src/finterminal/agents/news_trend.py`
**Shipped:** 2026-04-29, Sprint B-2a (`feature/b2a-news-trend`)
**Command:** `/trends [sector]`

---

## Purpose

Reads the current day's clusters and lineage from [[data — news_store]], formats them into a ranked trend table, and returns the result for rendering via `render_trends_table` in `ui/panels.py`.

Standalone agent — not part of the `analyze_flow.py` registry (registry stays at 3 agents).

---

## Inputs / Outputs

| | Detail |
|---|---|
| **Input** | Optional `sector: str` filter; `None` = all sectors |
| **Data read** | `news_clusters` + `cluster_lineage` from DuckDB via `NewsStore` |
| **Output** | List of trend rows consumed by `render_trends_table` |

---

## Trend Row Shape

| Field | Type | Source |
|---|---|---|
| `label` | `str` | Cluster label (derived from tagger majority) |
| `sector` | `str` | Sector tag |
| `story_count` | `int` | Number of stories in cluster |
| `story_count_delta` | `int \| None` | From `cluster_lineage.story_count_delta`; `None` if new cluster |
| `lineage_day` | `int \| None` | Day offset of predecessor cluster; `None` if new |
| `momentum_badge` | `str` | Formatted badge string (see UI section below) |

---

## Momentum Badge Logic

| Condition | Badge | Style |
|---|---|---|
| `story_count_delta > 0` | `▲N (Day M)` | green |
| `story_count_delta < 0` | `▼N (Day M)` | red |
| `story_count_delta == 0` or no lineage | `· (Day M)` | dim |

`N` = absolute delta; `M` = lineage day offset (days since predecessor)

Badge is computed in `news_trend.py`; rendered as Rich markup in `render_trends_table`.

---

## Integration

- `/trends [sector]` in `commands.py` instantiates `NewsTrendAgent`, calls `.run(sector=...)`, passes result to `render_trends_table`
- `/refresh-news` must be run first to populate data; agent returns empty list with a warning if no clusters exist for today

---

## Registry Note

`analyze_flow.py` `AgentRegistry` is unchanged:

| # | Agent |
|---|---|
| 1 | DataAgent |
| 2 | AnalystAgent |
| 3 | CriticAgent |

`NewsTrendAgent` is not registered in `analyze_flow`; it is invoked directly by its command handler.

---

## Cross-Links

- Pipeline that produces data: [[news — pipeline]]
- Storage: [[data — news_store]]
- UI renderer: [[04 - Code Map/ui — Rich-Textual]]
- Commands: [[04 - Code Map/commands]]
- Build log: [[05 - Build Log/2026-04-29 — Sprint B-2a News Trend]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]] (B-2a)
