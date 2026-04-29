# Code Map — data/ (OpenBB + DuckDB + India layer)

> Back to [[Index]] | See also [[data — india module]] · [[data — india — nse_quote]] · [[01 - Architecture/Storage]] · [[01 - Architecture/Data Sources]] · [[ADR-003 DuckDB + SQLite + ChromaDB local-only]] · [[ADR-012 Custom Indian Data Layer]] · [[ADR-015 Provider Chain Pattern for Fallthrough]]

**Directory:** `src/finterminal/data/`

---

## File inventory

| File | Key exports | Role |
|---|---|---|
| `openbb_client.py` | `fetch_quote`, `fetch_fundamentals`, `fetch_news`, `_is_indian_ticker`, `_fetch_via_yfinance` | Provider router; .NS/.BO route through India-first chains; multi-provider fallthrough chain (Q-5) |
| `duckdb_store.py` | `get_conn`, `upsert_quote`, `latest_quote`, `upsert_fundamentals`, `upsert_news`, watchlist CRUD, `record_analysis` | All DuckDB read/write operations |
| `finnhub_client.py` | `is_available`, `fetch_quote`, `fetch_news` | Direct HTTP (OpenBB ships no extension); dormant unless `FINNHUB_API_KEY` set |
| `nse.py` | `normalize_ticker` | Ticker normalization with `EXCHANGE:SYMBOL` prefix syntax (NSE/BSE/US) |
| `india/` | `screener_in.fetch_fundamentals`, `news_rss.fetch_news` | See [[data — india module]] for the dedicated code map |
| `migrations/001_initial.sql` | — | Phase-1 DuckDB schema (6 tables) |

---

## `openbb_client.py` — key functions

### Provider chains (Q-5, commit `bc269cb`)

```python
_QUOTE_PROVIDERS = ["yfinance", "nse"]      # openbb_client.py:29
_FUNDAMENTAL_PROVIDERS = ["yfinance"]
_NEWS_PROVIDERS = ["benzinga", "yfinance"]
```

The `nse` provider fires only for `.NS` / `.BO` tickers (`_is_indian_ticker` gate). See [[ADR-015 Provider Chain Pattern for Fallthrough]] for the design rationale.

### `fetch_quote(ticker: str) -> dict`

Iterates `_QUOTE_PROVIDERS` in order; returns on first success; raises `RuntimeError` (with last error) only when all providers fail. Propagates the LAST error, not the first — see ADR-015.

**Provider 1 — yfinance (via `_fetch_via_yfinance`, line :50):**
- Tries `obb.equity.price.quote()` first.
- On empty/failure, falls back to `obb.equity.price.historical()` and synthesizes a quote from last two closes.
- Raises `RuntimeError` on all-paths-failed.

**Provider 2 — nse (`.NS` / `.BO` only, line :133–143):**
- Calls `india.nse_quote.fetch_nse_quote(ticker)` (lazy import).
- Two-step session warmup; browser-like UA required.
- See [[data — india — nse_quote]] for full field mapping.

Live validation (Q-5): yfinance timed out on `/analyze ITC` (2026-04-29); NSE fallthrough returned correct ITC quote numbers; analysis completed normally.

### `fetch_fundamentals(ticker: str) -> dict`

**Provider chain (commit `1232297`):**
- `.NS` / `.BO` → `india.screener_in.fetch_fundamentals()` first → yfinance fallback if Screener parse returns no PE/ROE
- US (no suffix) → yfinance only

Live numbers for `RELIANCE.NS` after this change: PE 23.30, EPS 70.77, ROE 0.0925, ROCE 0.105, D/E 0.44, Revenue ₹10,57,219 cr, Net Income ₹95,754 cr — every field populated. The previous yfinance-only path returned 4 of 7 fields blank.

### `fetch_news(ticker: str, limit=20) -> list[dict]`

**Provider chain (commit `1232297`):**
- `.NS` / `.BO` → `india.news_rss.fetch_news()` → Finnhub (if `FINNHUB_API_KEY` set) → Benzinga → yfinance
- US → Benzinga (rich, source-tagged) → yfinance fallback

Indian path live-tested on RELIANCE: returns ET Stocks ("Reliance share price target hiked to Rs 1,910 — Goldman/CLSA/Morgan Stanley"), Livemint, Moneycontrol items.

### `_is_indian_ticker(ticker: str) -> bool`

Returns True iff ticker ends with `.NS` or `.BO`. Used to gate India-specific routing.

---

## `duckdb_store.py` — key functions

| Function | Notes |
|---|---|
| `get_conn()` | Returns DuckDB connection; runs migrations on first open |
| `upsert_quote(ticker, as_of, ...)` | INSERT OR REPLACE into `quotes` table |
| `latest_quote(ticker)` | Returns most recent quote row or None |
| `upsert_fundamentals(ticker, as_of, ...)` | INSERT OR REPLACE into `fundamentals` |
| `latest_fundamentals(ticker)` | Returns most recent fundamentals row or None |
| `upsert_news(articles)` | Bulk insert; deduplication by `id` (hash of url+published_at) |
| `recent_news(ticker, limit)` | Returns recent news sorted by `published_at` DESC |
| `add_to_watchlist(ticker, notes)` | INSERT OR REPLACE into `watchlist` |
| `remove_from_watchlist(ticker)` | DELETE from `watchlist` |
| `list_watchlist()` | Returns all watchlist rows |
| `record_analysis(ticker, bull, bear, confidence, sources)` | INSERT into `analyses`; returns `analysis_id` |
| `latest_analysis(ticker)` | Returns most recent analysis or None |

---

## Migration: `001_initial.sql`

Path: `src/finterminal/data/migrations/001_initial.sql`

6 tables: `quotes`, `fundamentals`, `news`, `watchlist`, `analyses`, `llm_calls`.

**Column naming note:** `as_of` (not `asof`) — `asof` is a reserved keyword in DuckDB (`ASOF JOIN`). See [[01 - Architecture/Storage]] for the full gotcha note.

---

## Phase-2.5 additions (planned)

`002_phase25.sql` will add ~14 new tables. See [[ADR-008 Phase 2.5 Analyst-Grade Layer]] for the full list.
