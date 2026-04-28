# Code Map — data/india/ (custom Indian data layer)

> Back to [[Index]] | See also [[data — OpenBB + DuckDB]] · [[01 - Architecture/Data Sources]] · [[ADR-001 Indian Markets First]] · [[ADR-012 Custom Indian Data Layer]]

**Directory:** `src/finterminal/data/india/`
**Shipped:** 2026-04-28, commit `1232297`
**Driver:** [[input.md feedback (2026-04-28)]] — free OpenBB providers (FMP/Tiingo/AV) give weak/paid-only Indian coverage. Custom layer beats chasing US-centric APIs.

---

## File inventory

| File | Lines | Purpose |
|---|---:|---|
| `__init__.py` | 16 | Module docstring + Phase 2.5 roadmap (moneycontrol_rss, trendlyne_consensus, nse_filings, amfi_holdings) |
| `screener_in.py` | ~210 | Fundamentals scraper (PE / ROCE / ROE / D-E / revenue / net income) |
| `news_rss.py` | ~165 | News aggregator across Moneycontrol + Livemint + ET RSS feeds |

---

## `screener_in.py`

### Public surface
```python
fetch_fundamentals(symbol_bare: str) -> dict
```

`symbol_bare` is the bare ticker (e.g. `"RELIANCE"`). Strip `.NS`/`.BO` before calling. The wrapper in `openbb_client.fetch_fundamentals` does this automatically.

### Strategy
- URL: `https://www.screener.in/company/{symbol}/consolidated/` → falls back to standalone if 404
- Parses `#top-ratios` block (PE, ROCE, ROE, market cap, current price, book value)
- Parses `<section id="profit-loss">` last column (Sales, Net Profit; rightmost = most recent FY; ×1e7 for ₹Cr → INR)
- Parses `<section id="balance-sheet">` last column (Borrowings, Equity Capital, Reserves)
  - Computes `debt_to_equity = Borrowings / (Equity_Capital + Reserves)`
- Derives `eps_ttm = net_profit / (market_cap / current_price)`

### Robustness
- httpx + BeautifulSoup (lxml). 200 OK in ~230 ms.
- **Rate limit**: 1 request/sec process-wide (`_MIN_INTERVAL_S`)
- **Cache**: `@lru_cache(maxsize=64)` on the public function
- **User-Agent**: `FINTERMINAL/0.1 (+https://github.com/AjinkyaWagh9/Finance-Terminal)`
- **Per-field tolerance**: any unparseable value → None; partial dicts still return so the supervisor LLM has something to work with

### `_parse_number(s)` conventions
| Input | Output |
|---|---|
| `"₹1,389"` | `1389.0` |
| `"23.3"` | `23.3` |
| `"9.25%"` | `0.0925` (ratio convention matches yfinance) |
| `"₹18,79,327Cr."` | `1.879327e13` (×1e7 for crore) |
| `"-"` or `""` | `None` |

### Live validation (commit `1232297`)
| Ticker | PE | EPS | ROE | ROCE | D/E |
|---|---:|---:|---:|---:|---:|
| RELIANCE | 23.30 | 70.77 | 0.0925 | 0.105 | 0.44 |
| INFY | 15.40 | 72.65 | 0.322 | 0.403 | 0.099 |
| HDFCBANK | 15.80 | 51.49 | 0.138 | 0.0704 | None* |

\* Banks structure liabilities with deposits, not "Borrowings" — None is the correct answer here, not a bug.

---

## `news_rss.py`

### Public surface
```python
fetch_news(ticker: str, limit: int = 20) -> list[dict]
```

Returns items in `openbb_client.fetch_news` shape: `id, ticker, source, headline, url, published_at, body`.

### Sources (9 RSS feeds)
- Moneycontrol: Top News, Markets, Business, LatestNews
- Livemint: Markets, Companies
- Economic Times: Markets, Stocks, Earnings, Industry
- Business Standard: **disabled** — SSL handshake times out from this network. Re-enable if reachability is restored.

### Match logic
- Curated `_TICKER_ALIASES` dict (top-20 NIFTY): `RELIANCE → ["Reliance", "RIL", "Reliance Industries"]`, etc.
- Multi-word aliases: plain case-insensitive substring (e.g. `"hdfc bank"` in `"HDFC Bank Q4 results..."`)
- Single-word aliases: word-boundary regex `(?<![a-z0-9])alias(?![a-z0-9])` — prevents `"INFY"` matching `"informatics"`
- Searches headline + body (broader recall)
- Falls back to bare symbol as alias if ticker not in curated dict

### Caching
- `@lru_cache(maxsize=8)` on `_cached_feed(url, bucket)` where `bucket = int(time.time() // 600)`
- Effectively: each feed is fetched once per 10-minute window

### Phase 2 upgrade path
- Replace curated `_TICKER_ALIASES` with NSE `EQUITY_L.csv` autoload (~2,000 listed companies)
- Add Business Standard once IPv6 routing issue is resolved
- Move dedupe + storage into `news` DuckDB table for cross-session retention

---

## Module roadmap (Phase 2.5)

Per `__init__.py` docstring + [[ADR-008 Phase 2.5 Analyst-Grade Layer]]:

| Future module | Purpose | ADR |
|---|---|---|
| `trendlyne_consensus.py` | Broker consensus, target-price revisions, rating distribution | [[ADR-008 Phase 2.5 Analyst-Grade Layer]] |
| `nse_filings.py` | Corporate announcements, SAST disclosures, bulk/block deals | [[ADR-008 Phase 2.5 Analyst-Grade Layer]] |
| `amfi_holdings.py` | Mutual fund portfolio disclosures (monthly) | [[ADR-008 Phase 2.5 Analyst-Grade Layer]] |
| `nsdl_fii_flows.py` | FII/DII daily flow aggregates | [[ADR-008 Phase 2.5 Analyst-Grade Layer]] |
| `transcripts/` | Concall transcript ingestion (NSE → screener.in → YouTube → Whisper) | [[ADR-008 Phase 2.5 Analyst-Grade Layer]] |

---

## Cross-links

- ADR: [[ADR-001 Indian Markets First]] · [[ADR-012 Custom Indian Data Layer]] · [[ADR-008 Phase 2.5 Analyst-Grade Layer]]
- Architecture: [[01 - Architecture/Data Sources]] · [[01 - Architecture/System Diagram]]
- Build log: [[2026-04-28 - Indian Data Layer Shipped]] · [[2026-04-28 - Indian News Gap]]
- Adjacent code: [[data — OpenBB + DuckDB]] (the wrapper that routes here)
