# ADR-005 — Sentiment is an Optional, Feature-Flagged Module

> Back to [[Index]] | See also [[02 - Decisions/ADR-004 Grok over X API for Sentiment]] · [[01 - Architecture/Agent System]]

**Status:** Accepted
**Date:** 2026-04-27
**Source:** [PLAN.md §4.3 final paragraph](../docs/PLAN.md)

---

## Context

Sentiment via Grok Live Search is the highest-cost, highest-volatility input in the system. A Grok outage or pricing change should not break the daily research workflow. The terminal must be a complete product without sentiment.

---

## Decision

The entire sentiment module is gated by two conditions:

```
SENTIMENT_ENABLED=true   # in .env
GROK_API_KEY=<key>       # in .env
```

If either is absent or false:
- `/sentiment` prints a one-line "sentiment disabled" notice with setup instructions.
- Sentiment panels in the TUI are hidden or shown as "—".
- `/analyze` runs the full bull/bear flow on fundamentals + news only; the Critic flags "sentiment input unavailable" in the assumptions block.
- The Sentiment Agent is **not registered** with the CrewAI orchestrator at startup.
- Zero code paths require Grok.

---

## Rationale

| Factor | Reasoning |
|---|---|
| Cost control | Sentiment is the most expensive optional feature. Flag-off means $0 Grok cost with zero functional loss on core research. |
| Reliability | Grok outage ≠ terminal down. The daily workflow (fundamentals + news + critique) is the primary product. |
| A/B testability | Running weeks with sentiment OFF, then ON, lets you measure if it actually improves decision quality vs. adds noise. |
| Offline use | Terminal still works on a plane, in a data center, or without an xAI API key. |

---

## Implementation boundary

- `sentiment/` directory is a self-contained module under `src/finterminal/sentiment/`.
- `SentimentSource` interface (`source.py`) means if Grok is ever replaced (StockTwits, another provider), only `grok_source.py` changes.
- Phase 2.5 turns sentiment ON for the first time (after Phase 2.0 ships with it OFF).

---

## Consequences

- Sentiment timeline: OFF in Phase 1–2.0 → evaluate in Phase 2.5 → decide cadence at Phase 2.5 cut (hourly market sweep ~$5/mo vs. per-ticker hourly ~$95/mo per PLAN.md §9 Q2).
- Grok pricing risk: medium likelihood, low impact (flagged off).
- The Sentiment Agent (agent #6 in PLAN.md §5.1) is one of 13; its absence doesn't affect the other 12.
