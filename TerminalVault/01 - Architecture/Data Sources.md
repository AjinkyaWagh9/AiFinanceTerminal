# Data Sources

> Back to [[Index]] | See also [[ADR-001 Indian Markets First]] · [[ADR-004 Grok over X API for Sentiment]] · [[ADR-012 Custom Indian Data Layer]] · [[data — OpenBB + DuckDB]] · [[data — india module]]

---

## Source inventory by phase

### Phase 1 (active — commit `1232297`)

| Source | What it provides | Access |
|---|---|---|
| **OpenBB + yfinance** | NSE/BSE/US quotes; US fundamentals; fallback news | Free; `pip install openbb` |
| **Screener.in** *(Indian fundamentals)* | PE, EPS, ROE, ROCE, D/E, revenue, net income for `.NS`/`.BO` tickers | Free; scraping via `data/india/screener_in.py` |
| **Moneycontrol + Livemint + ET RSS** *(Indian news)* | 9 RSS feeds; alias-matched per ticker | Free; `data/india/news_rss.py` |
| **Benzinga** *(US news)* | Rich US-equity headlines via OpenBB | Free key in OpenBB Hub |
| **Finnhub** *(optional, dormant)* | Quotes + news fallback for any ticker | Free key; activates when `FINNHUB_API_KEY` set |
| **DuckDB** (local) | Cached quotes, fundamentals, analyses | Local |

**Known issue — yfinance Indian quote endpoint flakiness:** `obb.equity.price.quote()` for `.NS` tickers (yfinance backend) intermittently fails due to cookie/crumb authentication changes at Yahoo. `openbb_client.fetch_quote` falls back to `obb.equity.price.historical()` and synthesizes a quote from the most recent OHLCV bar. RELIANCE.NS returned `last_price=1388.90` via this path.

**Known issue — IPv6 timeouts:** Some hosts (FRED, Business Standard) time out from this Mac unless using `httpx`'s happy-eyeballs (curl defaults don't). Affects FRED key (still in `.env`, dormant) and Business Standard RSS (disabled in `data/india/news_rss.py`).

**Routing logic (`data/openbb_client.py`):**
- `_is_indian_ticker(ticker)` is True iff ticker ends `.NS`/`.BO`.
- Fundamentals: India → Screener.in, fallback yfinance. US → yfinance.
- News: India → RSS aggregator → Finnhub (if key) → Benzinga → yfinance. US → Benzinga → yfinance.

---

### Phase 2 (planned)

| Source | What it provides | Access |
|---|---|---|
| **RSS feeds** | Mint, MoneyControl, BloombergQuint/Quintype, Reuters India, ET Markets | Free; custom RSS parser |
| **NewsAPI.org** | Fallback for English financial news | Free tier (limited India coverage) |
| **ChromaDB** | Semantic embedding store for news clustering | Local |

**Why NewsAPI is fallback only:** Indian coverage (ET, Mint, MoneyControl, BS) scored only 3/5 in the decision matrix (PLAN.md §4.4). RSS aggregation scores 5/5 for Indian coverage.

---

### Phase 2.5 (planned — Indian-specific moat)

| Source | What it provides | Frequency | Free? |
|---|---|---|---|
| **NSE/BSE shareholding patterns** | Promoter %, FII %, DII %, public % | Quarterly (XBRL filings) | Yes |
| **SEBI SAST disclosures** | Substantial acquisitions, promoter buying/selling | Real-time | Yes |
| **NSE/BSE bulk & block deals** | Trades > 0.5% equity / > ₹10cr | Daily | Yes |
| **AMFI portfolio disclosures** | Mutual fund holdings per scheme | Monthly (10th of next month) | Yes |
| **NSDL/CDSL FII flows** | Aggregate net FII purchases by segment | Daily | Yes |
| **NSE/BSE pledge disclosures** | Promoter share pledges | Event-driven | Yes |
| **Trendlyne** | Consensus estimates, concall transcripts | Daily | Free (scraping) |
| **screener.in** | Consensus estimates, fundamentals | Daily | Free (scraping) |
| **YouTube Data API** | CEO / earnings call audio | Event-driven | Free (within quota) |
| **NSE/BSE corporate announcements** | Concall PDFs, earnings dates, ex-div, AGM | Event-driven | Yes |
| **RBI database** | India 10Y yield, macro series | Daily | Yes |
| **FRED (St. Louis Fed)** | US macro series (10Y, DXY, Brent baseline) | Daily | Free API |
| **xAI Grok Live Search** | X (Twitter) sentiment on tickers | On-demand | $5/1k calls (optional) |

**AMFI data lag note:** Portfolio data is monthly with a 10-day lag. The `as_of_date` is always displayed on ownership panels — never represents as real-time.

---

### Phase 3 (planned — US expansion)

| Source | What it provides |
|---|---|
| **Finnhub free tier** | US equity quotes, fundamentals |
| **SEC EDGAR** | 13F filings, 10-K, 10-Q, 8-K |
| **Broader RSS** | WSJ, FT, Bloomberg (free tier) |

---

## OpenBB as the abstraction layer

OpenBB wraps multiple data providers (yfinance, Finnhub, FMP, etc.) behind a unified API. Switching the underlying provider for a data type is a config change, not a code change. This aligns with the model-abstraction philosophy in [[LLM Abstraction Layer]].

---

## Scraping discipline

For Trendlyne, screener.in, NSE/BSE direct pages:
- Treat HTML parsers as a known-fragile boundary; isolate behind `ConsensusSource` / `OwnershipSource` interfaces.
- Store raw snapshots to detect layout changes.
- Schema-versioned parsers so layout changes don't silently corrupt data.
- Respect rate limits; no aggressive crawling.
