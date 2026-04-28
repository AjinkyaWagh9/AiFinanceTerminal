# 2026-04-28 — Indian data layer shipped (Screener.in + RSS + Finnhub)

> The Indian-fundamentals gap that hobbled `/analyze` is closed. PE, EPS, ROE, ROCE, D/E, revenue, net income — all populated for any NSE/BSE ticker via the new `data/india/` module. News quality also lifted dramatically (Moneycontrol + Livemint + ET feeds vs the thin yfinance default). `/analyze RELIANCE` now produces analyst-grade output citing today's broker target hikes.

**Commit:** `1232297` pushed to `main`. **+626 LOC** across three new modules.

---

## What shipped

| Module | Source | Closes |
|---|---|---|
| `data/india/screener_in.py` | screener.in scraping | PE/ROCE/ROE/D-E/revenue/net-income gap |
| `data/india/news_rss.py` | Moneycontrol + Livemint + ET RSS (9 feeds) | Indian news quality |
| `data/finnhub_client.py` | Finnhub direct HTTP (OpenBB ships no extension) | Optional fallback; supports India+US |

Wiring in `data/openbb_client.py`:
- **`fetch_fundamentals`**: `.NS` / `.BO` → screener.in first → yfinance fallback
- **`fetch_news`**: `.NS` / `.BO` → india RSS → Finnhub (if key) → Benzinga → yfinance
- **`_is_indian_ticker()`** helper

## Before vs after on RELIANCE.NS

| Field | Before (yfinance only) | After (Screener.in) |
|---|---|---|
| PE (TTM) | 23.20 ✓ | 23.30 ✓ |
| EPS (TTM) | — | 70.77 |
| ROE | 0.091 | 0.0925 |
| ROCE | — | 0.105 |
| Debt/Equity | 36.65 (wrong unit) | 0.44 (correct ratio) |
| Revenue (TTM) | — | ₹10,57,219 cr |
| Net Income (TTM) | — | ₹95,754 cr |
| News count | 6-8 yfinance items | 4 ET/Moneycontrol items including today's broker target hike |

The yfinance D/E of 36.65 was reported as a percentage; Screener gives the actual ratio. Order-of-magnitude correctness now lives in our schema.

## Surprising / worth remembering

| Finding | Detail |
|---|---|
| **IPv6 timeout pattern** | Same root cause for FRED earlier and screener.in / business-standard.com today. Mac prefers IPv6 routes that hang; `httpx` handles it via happy-eyeballs but `curl` defaults don't. Going forward, expect any new external source to need a quick `httpx` smoke test before assuming it's reachable. |
| **HDFCBANK D/E = None is correct** | Banks structure their balance sheet with deposits, not "Borrowings". Trying to compute D/E from the row labels would mislead. Surfacing None is the right answer. |
| **Trendlyne deferred** | Tempting to ship as part of this batch, but Phase 2.5.B (consensus + ownership + pledges) deserves proper schema design + caching strategy, not a quick hack. |
| **gpt-5-mini's behavior changes with better data** | Earlier `/analyze` had to write around missing fields ("data unavailable"). With Screener.in numbers in the context, it cites them directly and constructs falsifiable triggers ("ROE materially below current 0.092"). Same prompt, same model, much sharper output. |

## What's not changing yet

- **Trendlyne** — Phase 2.5.B (per [[ADR-008 Phase 2.5 Analyst-Grade Layer]])
- **NSE EQUITY_L.csv ticker→name autoload** — Phase 2 (Phase 1 ships with curated 20-name table)
- **Synthesis Layer** (Regime Detector, Scenario Engine, Calibration Loop) — Phase 3 per [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]]
- **Finnhub key** — user opted not to add; client is in place, dormant until `FINNHUB_API_KEY` set in `.env`

## Cross-links

- ADR: this commit operationally validates [[ADR-001 Indian Markets First]] (custom data layer beats chasing US-centric global APIs)
- ADR: [[ADR-008 Phase 2.5 Analyst-Grade Layer]] — Trendlyne consensus/ownership stays the next big push
- Code map: should add `[[data — india module]]` next session
- Phase: [[Phase 1 - MVP]] is now genuinely usable for Indian research, not just structurally complete
