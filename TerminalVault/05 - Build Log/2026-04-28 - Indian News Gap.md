# 2026-04-28 — Known Gap: Indian News Coverage via yfinance

> Back to [[Index]] | See also [[05 - Build Log/2026-04-28 - Phase 1 REPL Wiring Complete]]
> Related: [[03 - Phases/Phase 1 - MVP]] · [[01 - Architecture/Data Sources]]

---

## Problem

yfinance returns empty or near-empty news for Indian tickers (e.g. `INFY.NS`, `RELIANCE.NS`).

**Impact on Phase-1 exit criteria:**
- Criterion 2 — "≥10 headlines from ≥2 sources for a watched ticker" — **currently fails**.
- `/news INFY` renders an empty table with "[dim]no news returned[/]" — graceful, not an error.
- `/analyze` context block gets `## Recent News\n- data unavailable\n` — LLM has no news signal.

---

## Root cause

yfinance's news endpoint scrapes Yahoo Finance. Indian ticker pages on Yahoo Finance have sparse English-language news coverage compared to US tickers.

---

## Mitigation in place

`commands._cmd_news` (commands.py:94–98) catches `RuntimeError` from `openbb_client.fetch_news` and renders an empty table rather than crashing. No user-visible error.

---

## Fix required (pre-Phase-2)

Per PLAN.md §4.4: build an RSS aggregator layer covering:

| Source | Feed type | Language |
|---|---|---|
| Mint | RSS | English |
| MoneyControl | RSS | English |
| Economic Times Markets | RSS | English |
| BloombergQuint / BQ Prime | RSS | English |

Implementation steps:
1. Add `src/finterminal/data/rss_client.py` — fetch + normalize RSS feeds by ticker keyword
2. Extend `openbb_client.fetch_news` fallback or add a separate `rss_client.fetch_news(ticker)`
3. Merge results in `commands._cmd_news` — deduplicate by URL hash
4. Recheck Phase-1 exit criterion 2

**Owner:** pre-Phase-2 sprint
**Blocker for:** Phase-1 "done" sign-off on news criterion
