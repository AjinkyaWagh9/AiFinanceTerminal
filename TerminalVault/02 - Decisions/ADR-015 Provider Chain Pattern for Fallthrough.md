# ADR-015 — Provider chain pattern for fallthrough on data-source failure

> Adopt an ordered provider list (`_QUOTE_PROVIDERS`) with silent fallthrough so a single data-source failure never kills an analysis run.

**Status:** Accepted
**Date:** 2026-04-29
**Source:** Q-5 root-cause analysis · Sprint B-1 spec `docs/superpowers/specs/2026-04-29-data-layer-hardening-q5-q6.md`
**Drivers:** yfinance throttled `RELIANCE.NS` and `ITC.NS` multiple times on 2026-04-29; `EmptyDataError` propagated out of `fetch_quote` and terminated analysis runs that would otherwise have succeeded via an alternate source.

---

## Context

Before this ADR, `_QUOTE_PROVIDERS = ["yfinance"]` in `openbb_client.py:29`. Both the live-quote endpoint and the historical-bars fallback shared yfinance — so the "fallback" was not a real fallback at the provider level. One throttle event killed the entire quote chain.

NSE's public `/api/quote-equity` endpoint covers all NSE-listed equities with no authentication, reasonable latency, and a stable JSON shape. It is an appropriate second provider for Indian tickers.

---

## Decision

- `_QUOTE_PROVIDERS = ["yfinance", "nse"]` — ordered list; tried in sequence.
- `fetch_quote()` iterates the list; returns on first success; continues on any exception.
- The `nse` entry is gated by `_is_indian_ticker(ticker)` — NSE does not cover US symbols; skip silently for non-Indian tickers.
- On all-providers-failed: raise `RuntimeError` with the **last** error, not the first.
- New module `src/finterminal/data/india/nse_quote.py` implements the NSE provider.

---

## Consequences

### Positive
- Single yfinance throttle no longer terminates analysis for Indian tickers.
- Pattern is extensible: adding a third provider is a one-line change to `_QUOTE_PROVIDERS` plus a new `if provider == "..."` branch.
- Same pattern is already used in `fetch_news` (`_NEWS_PROVIDERS = ["benzinga", "yfinance"]`) — consistent across the data layer.

### Negative / risks
- NSE API is public and undocumented; it could change shape or add auth without notice.
- Each additional provider adds latency to the failure path (yfinance failure + NSE attempt). Acceptable — both are fast HTTP calls.

### What this does NOT change
- `_FUNDAMENTAL_PROVIDERS = ["yfinance"]` — screener.in is already the India-first fundamental path (not a chain entry); no change needed.
- US tickers: `nse` skipped via `_is_indian_ticker` gate; behavior unchanged.
- Finnhub, Benzinga, and the news chain are unaffected.

---

## Why propagate LAST error, not first

Propagating the last error means the raised `RuntimeError` describes the failure of the final provider attempted — the most recent context for diagnosis. The first error is typically the expected "provider throttled / empty" case; the last error is the unexpected one worth investigating.

---

## Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Add `_FUNDAMENTAL_PROVIDERS = ["yfinance", "nse"]` (NSE for fundamentals too) | NSE `/api/quote-equity` returns price data only, not PE/ROCE/ROE. Not applicable. |
| Retry yfinance with exponential backoff | Adds latency and doesn't help when the throttle is sustained (as it was on 2026-04-29). A different source is more robust than repeated retries of the same throttled one. |
| Raise first error | Misleading — the first error is "yfinance throttled" (expected, non-surprising); last error is the actual diagnostic context. |

---

## Cross-Links

- Triggered by: Q-5 from [[05 - Build Log/2026-04-29 — C Sprint (FU-2 Q-1 Q-2 Smoke Green)]]
- Implementation: commits `cc16a01` (tests), `bc269cb` (feat) · [[05 - Build Log/2026-04-29 — Sprint A Live + B-1 Hardening]]
- Code map: [[04 - Code Map/data — OpenBB + DuckDB]] · [[04 - Code Map/data — india — nse_quote]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]] (Q-5)
- Related: [[02 - Decisions/ADR-012 Custom Indian Data Layer]]
