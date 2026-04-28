

### The Problem
The keys you listed (FMP, Benzinga, Tiingo, Alpha Vantage, FRED, etc.) are **heavily US-centric**. Most of them have very limited or poor support for **Indian equities (NSE/BSE)** — especially for:
- Fundamentals (PE, EPS, balance sheet, ownership, etc.)
- Quality Indian news
- Corporate actions, transcripts, ownership flows (FII/DII, pledges), consensus estimates

FMP gives partial support for `.NS` but many fields require a paid plan. Others either timeout, return incomplete data, or have no India coverage at all.

### What You Should Do Instead (Recommended Strategy for FINTERMINAL)

#### 1. **Primary Approach: Build India-Specific Data Layer (Recommended)**
Don't rely only on OpenBB's global providers for Indian data. Create dedicated, robust sources for India in your terminal.

**Best Free / Low-Cost Sources for Indian Markets (2026):**

| Source                  | Best For                          | Type          | Cost          | Recommendation |
|-------------------------|-----------------------------------|---------------|---------------|----------------|
| **yfinance**            | Price, historical OHLCV, basic info | Library      | Free         | Use as primary for quotes & history |
| **NSE India + BSE**     | Corporate announcements, events   | Official     | Free         | Scrape / use public endpoints |
| **Screener.in**         | Excellent fundamentals, ratios, ownership | Website      | Free         | Scrape key pages (very reliable) |
| **Trendlyne**           | Screeners, ownership, broker reports, consensus | Website      | Free + Paid  | Scrape for ownership, pledges, consensus |
| **Moneycontrol / Economic Times** | News + some fundamentals     | Websites     | Free         | RSS + targeted scraping |
| **Upstox / ICICI Breeze APIs** | Market data & historical         | Broker APIs  | Free         | Good if you have demat account |
| **TrueData / Global Datafeeds** | Real-time & historical (paid)   | Commercial   | Paid         | Consider later for low-latency |

**Action Plan for Phase 1 & 2:**
- Keep **OpenBB + yfinance** for basic quotes and historical prices (`.NS` suffix works decently).
- Build custom scrapers / parsers for:
  - `src/finterminal/data/india/` folder
  - Fundamentals from Screener.in
  - Ownership + pledges from Trendlyne / NSE
  - News from Moneycontrol / Livemint RSS
- Use **BeautifulSoup + httpx** or **Playwright** for robust scraping (with proper delays and user-agent rotation).

#### 2. **Good Global APIs that Support India (Better than Current Ones)**
- **EODHD** — One of the better global APIs with decent India coverage (EOD + some fundamentals).
- **Finnhub** — Has India support in free tier (quotes, news, some fundamentals).
- **Twelve Data** — Supports India with reasonable coverage.
- **Marketstack** — Global including India (free tier available).

You can add these via OpenBB's provider system or directly in your custom India layer.

#### 3. **Immediate Practical Steps**
1. **Add yfinance fallback** in your `openbb_client.py` for Indian tickers.
2. **Create India-specific modules** early:
   - `india_fundamentals.py` (scrape Screener.in)
   - `india_ownership.py` (Trendlyne / NSE)
   - `india_news.py` (RSS + scraping)
3. In `config/models.yaml` and your router, keep the US-heavy keys but mark them clearly for Phase 3 (US expansion).
4. For now, disable or deprioritize providers that fail on `.NS` tickers and log a clear warning.

### Long-term Strategy for FINTERMINAL
Since your terminal's core value is **deep Indian equity research** (ownership flows, pledges, transcripts, forensic scores, consensus revisions, CEO signals), relying on generic US APIs will always be painful.

**Best path:**
- Build a strong **custom Indian data engine** (scraping + public NSE/BSE feeds + Screener.in/Trendlyne).
- Use OpenBB + yfinance + Finnhub/EODHD as supplements.
- Later (Phase 3), add paid low-latency providers like TrueData only if needed.

