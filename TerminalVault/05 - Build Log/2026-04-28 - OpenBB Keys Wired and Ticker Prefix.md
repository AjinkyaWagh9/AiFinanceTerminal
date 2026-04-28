# 2026-04-28 — OpenBB keys wired, Benzinga news live, ticker prefix syntax

> 5 free OpenBB keys (FMP, FRED, Tiingo, AV, Benzinga) added via the Open Data Platform desktop app. The Python SDK shares the credential file (`~/.openbb_platform/user_settings.json`) so no plumbing was needed. Probed each — only **Benzinga (US news)** delivered a clean win. Added `EXCHANGE:SYMBOL` prefix syntax to disambiguate Indian default vs US tickers.

**Commit:** `09df8ff` — pushed to `main`.

---

## Provider probe results

| Key | Probe result | Verdict |
|---|---|---|
| **Benzinga** | `/news US:AAPL` → 20 clean headlines per call | ✅ Wired as primary US news provider |
| **FMP** | AAPL: 47/48 derived fields populated; RELIANCE.NS: **402 Premium endpoint** | ⚠️ Defer to Phase 3 — needs multi-endpoint US strategy |
| **FRED** | DNS resolves; HTTPS connection times out (Akamai edge unreachable from this Mac) | 🔧 Network-level — not a code/key issue. yfinance `^TNX` is interim workaround |
| **Tiingo** | News API is paid tier (`"You do not have permission"`); historical timed out | ❌ Skip; key retained for possible later |
| **Alpha Vantage** | Not registered in OpenBB's `equity.price.*` provider set | ❌ Key stored, no useful endpoints today |

## The FMP trap (worth remembering)

FMP's `obb.equity.fundamental.metrics()` returns *derived ratios* (ROCE, income quality, net debt/EBITDA) — beautiful inputs for forensic scoring — but **not** raw `pe_ttm` or `eps_ttm`. Putting FMP first in the fundamentals chain produced `None` for our headline numbers. To use FMP properly we need to call multiple endpoints (`metrics` + `ratios` + `multiples`) and merge — that's Phase 3 work, not a casual change. Reverted to `_FUNDAMENTAL_PROVIDERS = ["yfinance"]` with a clear in-file comment.

## Ticker prefix syntax (new)

`finterminal/src/finterminal/data/nse.py:9` now accepts:

| Form | Resolves to | Use |
|---|---|---|
| `RELIANCE` | `RELIANCE.NS` | Default — bare symbols are NSE (Indian-first) |
| `NSE:HDFC` | `HDFC.NS` | Explicit NSE |
| `BSE:RELIANCE` | `RELIANCE.BO` | Explicit BSE |
| `US:AAPL` | `AAPL` | US — bare for yfinance / FMP / Benzinga |

Help panel teaches the form; tests cover all four prefix branches.

## What changed in `/news` quality

| Ticker | Before (yfinance) | After |
|---|---|---|
| `US:AAPL` | thin, ~6 items | **20 Benzinga headlines per call** with date + source |
| `RELIANCE` | Reuters, Simply Wall St., TechCrunch | unchanged — falls back cleanly |

## Cross-links

- ADR: this is consistent with [[ADR-001 Indian Markets First]] (Indian default preserved) and [[ADR-008 Phase 2.5 Analyst-Grade Layer]] (the real Indian-fundamentals fix is the Trendlyne / screener.in scraping pipeline in §6.5.B, not API keys)
- Code map: [[data — OpenBB + DuckDB]] gets a note about the Benzinga source-default + nse prefix syntax
- Phase: [[Phase 1 - MVP]] hardens; [[Phase 3 - US + Routing]] is now meaningfully accelerated by FMP+Benzinga

## What's not changing

- Indian `/analyze` quality is still gated on Phase 2.5.B (Trendlyne scraping) — free OpenBB keys do not cover Indian fundamentals, EPS, or revenue. This was a real expectation-correction this session.
- Nothing else regressed.
