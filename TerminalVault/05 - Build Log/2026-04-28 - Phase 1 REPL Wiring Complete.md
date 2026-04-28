# 2026-04-28 — Phase 1 REPL Wiring Complete

> Back to [[Index]] | See also [[05 - Build Log/2026-04-28 — Phase 1 Day 1 bootstrap]]
> Related: [[03 - Phases/Phase 1 - MVP]] · [[04 - Code Map/commands]] · [[04 - Code Map/agents — supervisor]] · [[04 - Code Map/ui — Rich-Textual]]

---

## What changed

**Before:** `terminal.py` printed "not implemented yet" for every command.
**After:** All four Phase 1 data commands are wired end-to-end. 10 smoke tests pass.

---

## Files added / changed

| File | Status | What it does |
|---|---|---|
| `src/finterminal/commands.py` | NEW | Sync REPL dispatcher; one handler per command |
| `src/finterminal/agents/supervisor.py` | NEW | `/analyze` async LLM flow; parse + persist |
| `src/finterminal/ui/panels.py` | EXTENDED | All panel renderers + `build_context_block` helpers |
| `src/finterminal/terminal.py` | UPDATED | Stub body replaced with `dispatch(line, console)` + logging init |
| `tests/test_smoke.py` | EXTENDED | 4 new tests for parser and context-block tagging |

---

## Command status

| Command | Path | Verified live |
|---|---|---|
| `/help` | `panels.help_panel()` | yes |
| `/ticker RELIANCE` | `openbb_client` → DuckDB → `panels.ticker_panel` | yes |
| `/news INFY` | `openbb_client` → DuckDB → `panels.news_table` (empty-table path tested) | yes (empty case) |
| `/watch add|list|remove` | DuckDB watchlist table → `panels.watchlist_table` | yes |
| `/analyze RELIANCE` | supervisor → Claude → `panels.analysis_panel` | wired, NOT run live* |

*Not run live to avoid spending Anthropic API budget without explicit permission.

---

## `/analyze` data flow (end-to-end)

```
/analyze RELIANCE
  → commands._cmd_analyze
    → normalize_ticker("RELIANCE") → "RELIANCE.NS"
    → asyncio.run(supervisor.analyze_ticker("RELIANCE.NS", conn))
      → openbb_client.fetch_quote + fetch_fundamentals + fetch_news
      → duckdb_store.upsert_quote / upsert_fundamentals / upsert_news
      → panels.build_context_block(ticker, quote, fundamentals, news)
          → format_quote_for_context    (every field: [src: quote.*])
          → format_fundamentals_for_context (every field: [src: fundamentals.*])
          → format_news_for_context     (every item: [src: news[i]])
      → router.for_agent("supervisor") → Claude Sonnet 4.6
      → LLM returns 5-section analyst.md format
      → supervisor.parse_analysis(text) → {bull_case, bear_case, confidence, assumptions, what_would_change}
          → confidence clamped to [0, 1]
      → duckdb_store.record_analysis(conn, ...) → analysis_id
      → llm.budget.record("supervisor", completion)
    → panels.analysis_panel(result)
      → side-by-side bull/bear panels (green/red borders)
      → 20-cell confidence gauge (green ≥0.7 / yellow ≥0.4 / red <0.4)
      → assumptions + "what would change my mind" panels
```

---

## Verified vs unverified paths

| Path | Status | Notes |
|---|---|---|
| Quote fetch + DuckDB upsert | verified | `test_duckdb_migration_runs` + live `/ticker RELIANCE` |
| News empty-table render | verified | live `/news INFY.NS` (yfinance returns empty) |
| Watchlist add/list/remove | verified | smoke test + manual |
| `parse_analysis` 5 sections | verified | `test_analysis_parser_extracts_all_sections` |
| `parse_analysis` missing sections | verified | `test_analysis_parser_handles_missing_sections` |
| Confidence clamping [0,1] | verified | `test_analysis_parser_clamps_confidence` |
| `build_context_block` [src:] tags | verified | `test_context_block_tags_every_numeric` |
| Full `/analyze` live (LLM call) | NOT verified | needs Anthropic API key |

---

## Known gaps (pre-Phase-2 followup)

- **Indian news coverage gap** — yfinance returns thin/empty news for `INFY.NS`, `RELIANCE.NS`. Phase-1 exit criterion 2 (≥10 headlines from ≥2 sources) currently fails. The RSS aggregator (Mint, MoneyControl, ET, BloombergQuint) from PLAN.md §4.4 is not yet built. See [[05 - Build Log/2026-04-28 - Indian News Gap]] for the tracked issue.
- **Null fields from yfinance** — `change_pct` and `market_cap` return null for some Indian tickers. Data-source quirk; not a code bug.
- **US tickers broken by design** — `normalize_ticker()` auto-appends `.NS`; `/ticker AAPL` → `AAPL.NS` → fails. US is Phase 3.
- **`/analyze` prompt discipline unverified** — needs a live LLM call to confirm every numeric claim carries a `[src:]` tag and confidence stays 0.4–0.7 per Phase-1-Kickoff §5.4.

---

## Test run summary

```
10 passed in <3 s (no LLM calls, no network)
```

All tests mock at the OpenBB / DuckDB boundary. LLM path tested structurally (parser) not end-to-end.
