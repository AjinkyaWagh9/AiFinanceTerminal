# ADR-001 — Indian Markets First

> Back to [[Index]] | See also [[03 - Phases/Phase 1 - MVP]] · [[02 - Decisions/ADR-004 Grok over X API for Sentiment]]

**Status:** Accepted
**Date:** 2026-04-27
**Source:** [PLAN.md §1, §2 Goals](../docs/PLAN.md)

---

## Context

The project targets two markets: NSE/BSE (India) and US equities. Both can't be built to full depth simultaneously. The owner has an Indian equities background and access to uniquely free, well-structured Indian data from public regulators (NSE, BSE, SEBI, AMFI, RBI).

---

## Decision

**NSE/BSE is the primary market for Phases 1–2.5.** US expansion starts in Phase 3.

---

## Rationale

| Factor | Reasoning |
|---|---|
| Free data advantage | NSE/BSE shareholding patterns, SEBI SAST disclosures, AMFI mutual-fund portfolios, and RBI macro data are all public and well-structured. Equivalent US data is partially gated behind paid APIs. |
| Owner edge | Indian market context, company familiarity, and news sources are already established — reduces validation effort. |
| Avoid split focus | Building robust Indian coverage (13 agents, 6 data source types) is already a full project. Attempting US simultaneously would halve the depth of both. |
| Comparable free tier | Finnhub free tier covers US quotes/fundamentals once the architecture is proven on India. |

---

## Consequences

- All Phase 1–2.5 tickers default to `.NS` (NSE) or `.BO` (BSE) suffixes.
- Data agents are tuned for SEBI/NSE filing formats, not SEC EDGAR.
- CEO Tracker Phase 2.5 covers 10 Indian + global leaders; US-only leaders (Dimon, Fink) deferred to Phase 3.
- US expansion in Phase 3 is low-friction: Finnhub client replaces NSE-specific data calls; no agent redesign.

---

## Alternatives considered

| Option | Why rejected |
|---|---|
| US-first | Poorer free data; no owner edge; NSE/BSE data would need re-integration later |
| Simultaneous | Both markets at half-depth; exit criteria harder to hit |

---

## Revisit trigger

Phase 2.5 exit criteria met on 25-name Indian watchlist (see [[02 - Decisions/ADR-008 Phase 2.5 Analyst-Grade Layer]]).
