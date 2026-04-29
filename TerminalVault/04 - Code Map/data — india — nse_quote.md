# Code Map — data/india/nse_quote.py

> Back to [[Index]] | See also [[data — india module]] · [[data — OpenBB + DuckDB]] · [[02 - Decisions/ADR-015 Provider Chain Pattern for Fallthrough]]

**File:** `src/finterminal/data/india/nse_quote.py`
**Shipped:** 2026-04-29, commit `bc269cb`
**Driver:** Q-5 — yfinance throttle caused entire quote chain to bail; NSE public API added as fallback

---

## Purpose

Fetches a live equity quote directly from NSE's public JSON API (`/api/quote-equity`) when yfinance is throttled or returns `EmptyDataError`. Returns the same dict shape as `openbb_client.fetch_quote` so the upstream caller can use the result interchangeably.

Indian tickers only (`.NS` / `.BO`). NSE does not cover US symbols.

---

## Public API

```python
fetch_nse_quote(ticker: str) -> dict
```

`ticker` may be bare (`RELIANCE`) or suffixed (`RELIANCE.NS` / `RELIANCE.BO`). The suffix is stripped internally.

Return shape matches `openbb_client.fetch_quote`:

| Field | Type | Source |
|---|---|---|
| `ticker` | `str` | Input ticker (preserved as-is) |
| `as_of` | `datetime (UTC)` | `datetime.now(timezone.utc)` at call time |
| `last_price` | `float \| None` | `priceInfo.lastPrice` |
| `change_pct` | `float \| None` | `priceInfo.pChange` |
| `volume` | `int \| None` | `priceInfo.totalTradedVolume` → fallback `marketDeptOrderBook.tradeInfo.totalTradedVolume` |
| `market_cap` | `float \| None` | `marketDeptOrderBook.tradeInfo.totalMarketCap` × 100,000 (lakhs → rupees) → fallback `securityInfo.issuedSize × lastPrice` |
| `provider` | `str` | `"nse"` |
| `raw` | `dict` | Full NSE JSON response |

---

## NSE Session Warmup Pattern

NSE's API requires a session cookie before serving quote JSON (`nse_quote.py:62–74`).

```
Step 1: GET nseindia.com/get-quotes/equity?symbol=X   # seeds cookies
Step 2: GET nseindia.com/api/quote-equity?symbol=X    # returns JSON; cookies travel automatically
```

Both requests share a single `httpx.Client` so the cookies set in step 1 are sent automatically in step 2.

**User-Agent requirement:** NSE blocks the default `python-httpx/...` User-Agent. The module uses a browser-like Chrome UA (`nse_quote.py:27–36`). Without it, step 1 returns 403 / redirect loop and step 2 returns empty or 401.

---

## Error Types

| Exception | When raised | File:line |
|---|---|---|
| `NSEQuoteError` | Any failure path (HTTP error, timeout, parse error, missing `priceInfo`) | `nse_quote.py:39` |
| `NSEQuoteError` subcase | HTTP 429 (throttle) | `nse_quote.py:81` |
| `NSEQuoteError` subcase | HTTP 404 (symbol not listed on NSE) | `nse_quote.py:83` |
| `NSEQuoteError` subcase | HTTP ≥ 400 (other) | `nse_quote.py:85` |
| `NSEQuoteError` subcase | Non-JSON body | `nse_quote.py:90` |
| `NSEQuoteError` subcase | `priceInfo` block missing from response | `nse_quote.py:93–96` |

`openbb_client.fetch_quote` catches all exceptions from `fetch_nse_quote` (including `NSEQuoteError`) and logs a warning before continuing — a thrown `NSEQuoteError` means both providers failed and `fetch_quote` will raise `RuntimeError`.

---

## NSE Response Shape Decisions (`nse_quote.py:92–133`)

| Decision | Line | Rationale |
|---|---|---|
| `priceInfo.lastPrice` for price | :98 | Primary live-price field; present on all equity quotes |
| `priceInfo.pChange` for change_pct | :99 | NSE's own percentage change; no recomputation needed |
| Volume: `priceInfo.totalTradedVolume` first | :100 | Directly on `priceInfo`; most quotes have it here |
| Volume fallback: `marketDeptOrderBook.tradeInfo.totalTradedVolume` | :103–104 | Some quotes omit it from `priceInfo`; same field in trade info block |
| Market cap: `marketDeptOrderBook.tradeInfo.totalMarketCap` × 100,000 | :110–116 | NSE reports in lakhs (1 lakh = 100,000); multiply to get rupees |
| Market cap fallback: `securityInfo.issuedSize × lastPrice` | :118–123 | Used when `totalMarketCap` absent; `issuedSize` = shares outstanding |

---

## Constants

| Name | Value | Purpose |
|---|---|---|
| `_BASE_URL` | `https://www.nseindia.com` | NSE base URL |
| `_WARMUP_PATH` | `/get-quotes/equity` | Cookie-seeding URL path |
| `_API_PATH` | `/api/quote-equity` | Actual data endpoint |
| `_REQUEST_TIMEOUT_S` | `15.0` | Per-request timeout (seconds) |

---

## Integration Point

`openbb_client.fetch_quote` imports `fetch_nse_quote` lazily (`openbb_client.py:137–140`) and calls it only when:
1. The current provider in the loop is `"nse"`, and
2. `_is_indian_ticker(ticker)` returns True

This means `nse_quote.py` is only imported when actually needed — OpenBB's slow cold start is not affected.

---

## Cross-Links

- ADR: [[02 - Decisions/ADR-015 Provider Chain Pattern for Fallthrough]] · [[02 - Decisions/ADR-012 Custom Indian Data Layer]]
- Adjacent code: [[data — OpenBB + DuckDB]] · [[data — india module]]
- Build log: [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]] (Q-5)
