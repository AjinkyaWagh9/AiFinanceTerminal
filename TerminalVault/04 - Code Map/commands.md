# Code Map — commands.py

> Back to [[Index]] | See also [[04 - Code Map/agents — supervisor]] · [[04 - Code Map/ui — Rich-Textual]] · [[04 - Code Map/data — OpenBB + DuckDB]]

**File:** `src/finterminal/commands.py`
**Role:** Sync REPL dispatcher. Receives a raw input line from `terminal.py`, routes to one of the five command handlers, handles errors uniformly.

---

## Key functions

| Function | Line | Purpose |
|---|---|---|
| `dispatch(line, console)` | :21 | Entry point. `line.split()` → cmd lookup → call handler or error panel |
| `_cmd_help(args, console)` | :54 | Renders `panels.help_panel()` |
| `_cmd_ticker(args, console)` | :61 | `normalize_ticker` → `fetch_quote` + `fetch_fundamentals` → DuckDB upsert → `ticker_panel` |
| `_cmd_news(args, console)` | :87 | `fetch_news` → DuckDB upsert (if non-empty) → `news_table`; empty case: renders empty table, no error |
| `_cmd_watch(args, console)` | :113 | Subcommands: `add` / `list` / `remove` → DuckDB watchlist ops |
| `_cmd_analyze(args, console)` | :148 | `normalize_ticker` → `asyncio.run(analyze_ticker(...))` → `analysis_panel` |

---

## Design notes

- **All handlers are sync.** Only `_cmd_analyze` bridges to async via `asyncio.run()` per [[02 - Decisions/ADR-009 Synchronous REPL with asyncio.run]].
- **Uniform error boundary:** `dispatch` catches `_UsageError` (user mistakes) and bare `Exception` (unexpected); both render via `panels.error_panel`. Last-resort guard tagged `# noqa: BLE001`.
- **`_UsageError`** is a private exception class (line :41) for clean usage messages without stack traces.
- **`_COMMANDS` dict** (line :166) maps `/cmd` strings → handler functions. Adding a command = one entry here + one `_cmd_*` function.

---

## Data flow per command

```
/ticker RELIANCE
  normalize_ticker → "RELIANCE.NS"
  openbb_client.fetch_quote + fetch_fundamentals
  duckdb_store.upsert_quote + upsert_fundamentals
  panels.ticker_panel(quote, fundamentals)

/news INFY
  normalize_ticker → "INFY.NS"
  openbb_client.fetch_news (may return [])
  duckdb_store.upsert_news (skipped if empty)
  panels.news_table(items, ticker)

/watch add RELIANCE [notes]
  normalize_ticker → "RELIANCE.NS"
  duckdb_store.add_to_watchlist(conn, ticker, notes)
  panels.info_panel("added RELIANCE.NS")

/analyze RELIANCE
  normalize_ticker → "RELIANCE.NS"
  asyncio.run(supervisor.analyze_ticker(ticker, conn))
  panels.analysis_panel(result)
```

---

## Dependencies

- `finterminal.data.duckdb_store` — all DB ops
- `finterminal.data.openbb_client` — market data
- `finterminal.data.nse.normalize_ticker` — ticker normalization
- `finterminal.ui.panels` — all renderers
- `finterminal.agents.supervisor.analyze_ticker` — lazy import inside `_cmd_analyze`
