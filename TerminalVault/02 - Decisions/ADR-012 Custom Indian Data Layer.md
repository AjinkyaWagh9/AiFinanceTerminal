# ADR-012 — Custom Indian Data Layer (over global APIs)

> Build a dedicated `data/india/` module (Screener.in scraping + Moneycontrol/Livemint/ET RSS) instead of relying on US-centric global APIs (FMP, Tiingo, Alpha Vantage, Finnhub) for Indian fundamentals and news. Trendlyne and NSE-deep ingestion remain Phase 2.5.B work.

**Status:** Accepted
**Date:** 2026-04-28
**Implemented in:** commit `1232297`
**Drivers:** [[input.md feedback (2026-04-28)]]; live probe results from [[2026-04-28 - OpenBB Keys Wired and Ticker Prefix]] showing FMP free tier 402's on `.NS`, Tiingo News is paid, AV unwired, FRED unreachable.

---

## Context

After Phase 1 shipped, the `/analyze RELIANCE.NS` output had 4 of 7 fundamentals fields blank ("data unavailable"). The natural reflex was to add API keys: FMP, Tiingo, Alpha Vantage, Finnhub, FRED — all advertised as covering "global markets."

Live probing revealed the gap is structural, not configurational:

| Provider | Indian fundamentals | Indian news | Indian quote |
|---|---|---|---|
| FMP free | ❌ 402 Premium endpoint on `.NS` | ❌ US-only | ⚠️ patchy |
| Tiingo | ❌ no India coverage in free | ❌ News API is paid tier | ❌ |
| Alpha Vantage | ❌ not wired into OpenBB endpoints | ❌ | ⚠️ |
| Benzinga | ❌ US-only | ❌ US-only | ❌ |
| FRED | ❌ macro only (US Treasury, etc.) | n/a | n/a |
| Finnhub free | ⚠️ basic | ⚠️ thin | ✅ |
| **yfinance** | ⚠️ basic (PE, ROE only) | ⚠️ thin | ✅ |

The only paths to deep Indian fundamentals are **paid services** (EODHD ~$20/mo, Trendlyne paid tier) or **direct ingestion from Indian-native free sources** (Screener.in, Moneycontrol, Livemint, NSE/BSE filings).

This is consistent with [[ADR-001 Indian Markets First]]'s logic: India's data moat is in *free public sources that US-centric APIs don't bother indexing*, and that gap is a feature for us — not a bug to engineer around with paid keys.

---

## Decision

Build a custom `data/india/` module with three free sources for Phase 1 closure:

1. **`screener_in.py`** — fundamentals scraping
   - URL: `screener.in/company/{symbol}/consolidated/`
   - Stable HTML (decade-old structure); section IDs unchanged for years
   - Extracts: PE, ROCE, ROE, debt-to-equity (computed), revenue, net income, EPS (derived)
   - Polite scraping: 1 req/sec, identifying UA, LRU cache

2. **`news_rss.py`** — news aggregation across 9 RSS feeds
   - Moneycontrol (4 feeds), Livemint (2), Economic Times (4)
   - No scraping; RSS is public, stable, no API key
   - Curated alias map for ticker → company-name matching (Phase 2 swaps to NSE EQUITY_L.csv autoload)

3. **`finnhub_client.py`** — direct HTTP optional fallback
   - OpenBB ships no Finnhub extension as of v4.7
   - Free tier covers India + US, 60 calls/min
   - Dormant unless `FINNHUB_API_KEY` is set

The `openbb_client.py` wrapper routes `.NS` / `.BO` tickers through India-first chains, falling back to existing yfinance/Benzinga paths if the India layer fails.

**Deferred (Phase 2.5.B per [[ADR-008 Phase 2.5 Analyst-Grade Layer]]):**
- Trendlyne scrape for consensus + ownership + pledges
- NSE corporate-announcements feed for events + SAST
- AMFI mutual fund portfolio disclosures
- NSDL/CDSL FII flow aggregates
- Concall transcript ingestion pipeline

These are Phase 2.5.B because they need proper schema design (multi-week tables for revisions, ownership deltas) and caching strategy, not a quick Phase-1 fix.

---

## Consequences

### Positive
- **Indian `/analyze` output transforms** — every numeric field now populated, citing real EPS, D/E, today's broker target hikes from ET. Bear cases now have falsifiable triggers ("ROE materially below current 0.092") instead of "data unavailable" hand-waves.
- **Architectural alignment** — validates [[ADR-001 Indian Markets First]] as a *data layer* decision, not just a roadmap statement.
- **Cost stays free** — no paid tier needed for Phase 1 closure.
- **Phase 2.5.B gets a foundation** — `data/india/` exists; Trendlyne / NSE / AMFI modules drop in alongside `screener_in.py`.

### Negative / risks
- **Scraping fragility** — Screener.in HTML could change. Mitigations: section-ID parsing (more robust than CSS classes), per-field tolerance (return partial dicts on parse failure), 1 req/sec rate limit + identifying UA reduces ban risk.
- **RSS feed silence** — feeds occasionally return zero matches for a given ticker (TCS in early testing). Mitigations: 9 sources + alias matching + 14-day window via Finnhub fallback. Body-text matching (not just headlines) widens recall.
- **Curated ticker→name table is incomplete** — covers top 20 NIFTY only. Phase 2 swaps to NSE EQUITY_L.csv autoload (~2,000 listed). Documented in `news_rss.py` docstring + [[data — india module]] roadmap.
- **No Trendlyne yet** — consensus, ownership, pledges still gap-areas. This is acknowledged: deferred to Phase 2.5.B by design, not by accident.
- **Network dependency on Indian sources** — observed during this session: IPv6 routing causes timeouts to some hosts (FRED, Business Standard). httpx uses happy-eyeballs and works; curl defaults don't. Documented in [[2026-04-28 - Indian Data Layer Shipped]].

### What this does NOT change
- Phase 1 still complete; gpt-5-mini supervisor unchanged
- Phase 2 multi-agent foundation unchanged
- Phase 2.5 spec (`§6.5.B` consensus, `§6.5.C` ownership) unchanged
- Phase 3 Synthesis Layer ([[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]]) unchanged
- Non-goals (no DCF, no alt-data, no backtesting platform) stand

---

## Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| **EODHD subscription** (~$20/mo, decent India coverage) | Not justified yet — free layer covers Phase 1 needs. Revisit if quality plateau hit. |
| **Trendlyne scrape included in this commit** | Deferred to Phase 2.5.B per [[ADR-008 Phase 2.5 Analyst-Grade Layer]] — needs its own schema (consensus_snapshots over time, ownership deltas, pledge history). Half-implementing today would be worse than waiting. |
| **Wait for an OpenBB India provider** | OpenBB has shown no interest in deep Indian fundamentals; they're a US/global tool. Waiting is unbounded; building is finite. |
| **Use only the keys user has paid for** | Probing showed those keys don't fix the Indian gap. Adding more keys is the wrong axis. |
| **Stop at yfinance** | Original Phase 1 attempt — produced "data unavailable" 4 of 7 fields. Insufficient for real research. |

---

## Cross-links

- Triggered by [[input.md feedback (2026-04-28)]]
- Operationally validates [[ADR-001 Indian Markets First]]
- Foundation for [[ADR-008 Phase 2.5 Analyst-Grade Layer]] consensus + ownership work
- Implementation: [[data — india module]] code map; build log [[2026-04-28 - Indian Data Layer Shipped]]
- Adjacent: [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] (uses the data this layer produces)
