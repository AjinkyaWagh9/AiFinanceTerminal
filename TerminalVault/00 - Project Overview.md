# Project Overview

> Back to [[Index]]

A local-first, AI-augmented equity research terminal. Not a trading platform. Not a robo-advisor. A daily-driver that makes "what's moving TICKER today and why?" answerable in under 15 seconds — without opening six browser tabs.

---

## What it does (four capabilities)

1. **Live market data + fundamentals** — NSE/BSE (Phase 1), US (Phase 3) via OpenBB.
2. **News + topic clustering** — financial press, regulatory filings, macro feeds. RSS + OpenBB connectors.
3. **X sentiment** via xAI Grok Live Search — **optional, feature-flagged**. Terminal is a complete product without it.
4. **CEO / leader signal tracking** — Jensen Huang, Jamie Dimon, Larry Fink, Satya Nadella, Sundar Pichai + Indian leaders (Ambani, Chandrasekaran, Kotak, Kamath, Bajaj). Earnings calls, conferences, podcasts.
5. **Analyst-grade layer (Phase 2.5)** — transcripts, consensus estimates + revisions, ownership flows, forensic quality scores, peer comps, macro overlay. What a buy-side analyst at a Mumbai fund opens at 8 AM.

---

## Goals (priority order)

| # | Goal | Target |
|---|---|---|
| G1 | Daily-driver utility | Faster than 6 browser tabs for a ticker check-in |
| G2 | Signal extraction | Detect non-obvious cross-asset narratives |
| G3 | Bull/bear discipline | Every analysis ends with confidence score + dissenting view + explicit assumptions |
| G4 | Local-first privacy | Watchlist and queries never leave machine unless routed to Claude/NIM |

---

## Success metrics (Phase 2 target)

| Metric | Target |
|---|---|
| Time to answer "should I look at $TICKER today?" | < 15 seconds |
| Tickers tracked simultaneously | ≥ 25 |
| News articles processed daily | ≥ 500 |
| X posts analyzed daily (when enabled) | ≥ 1,000 |
| CEO transcript ingestions per week | ≥ 5 |
| Self-critique on every recommendation | 100% |
| Local-model fallback when Claude unavailable | Works offline |

---

## Differentiators vs. just-using-OpenBB

- Sentiment + CEO signals fused into the same surface as price/fundamentals.
- Self-critique loop on every recommendation (confidence score, dissenting view).
- Investment-philosophy framing baked into prompts: Rich Dad asset/liability lens, Stoic uncertainty, Munger inversion.

---

## Non-goals (Phase 1–3)

- Order execution / brokerage integration
- Full backtesting platform (light hooks only in Phase 3)
- Mobile/web clients
- Options analytics, derivatives chains

See `BACKLOG.md` for the full list with rationale and "revisit when" triggers.

---

## Monthly cost estimate (Phase 2.5, sentiment OFF)

| Item | Cost |
|---|---|
| Claude API (Sonnet 4.6) | $30–90 |
| Grok (optional, off) | $0 |
| Everything else (OpenBB, NSE/BSE, Trendlyne, SEBI, AMFI, YouTube, NIM free tier) | $0 |
| **Floor** | **$30–90** |

---

## Related pages

- [[01 - Architecture/System Diagram]] — how the components connect
- [[03 - Phases/Phase 1 - MVP]] — what's being built right now
- [[02 - Decisions/ADR-007 No DCF no alt-data no backtesting]] — why the non-goals exist
