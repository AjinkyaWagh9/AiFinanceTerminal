# ADR-007 — Non-Goals: No DCF, No Alt-Data, No Backtesting

> Back to [[Index]] | See also [[02 - Decisions/ADR-008 Phase 2.5 Analyst-Grade Layer]]

**Status:** Accepted
**Date:** 2026-04-27
**Source:** [BACKLOG.md §2 (Cut, may revisit), §3 (Hard nos)](../docs/BACKLOG.md)

---

## Context

As the Phase 2.5 Analyst-Grade Layer spec was written (PLAN.md §6.5.2), a decision matrix scored 14 capabilities. Three scored too low or too complex to include in Phases 1–3. Capturing them as an explicit ADR prevents scope creep.

---

## Decision

The following capabilities are **out of scope for Phases 1–3**:

| Capability | Decision | BACKLOG.md ref |
|---|---|---|
| DCF / SOTP modeling | Cut, may revisit (Phase 4 light only) | §2.1 |
| Alternative data (LinkedIn hiring, SimilarWeb, app downloads) | Cut, may revisit | §2.2 |
| Full backtesting platform | Hard no (light vectorbt hooks Phase 3 only) | §3, §1.5 |
| Order execution / brokerage integration | Hard no | §3.1, §3.7 |
| Mobile / web clients | Cut, may revisit (Phase 4+) | §2.5 |
| Multi-user / multi-portfolio | Hard no | §2.8 |
| Crypto / NFTs | Hard no | §3.5 |
| Real-time tick-level market data | Hard no | §3.4 |

---

## Rationale per category

### DCF (§2.1)
- Replicating Excel-quality DCF = months of work. Segment reporting, SOTP, terminal value sensitivity are each full sub-problems.
- "Light" version is uncannily error-prone; risk of misleading output outweighs value.
- Revisit if: genuinely stop opening Excel for valuation, OR Phase 4 cleanup has capacity.

### Alt data (§2.2)
- Most alt-data APIs are paid (Yipit, SimilarWeb Pro). Free LinkedIn scraping is fragile.
- Cost/maintenance kills ROI for individual use.
- Survival: Google Trends for ticker/brand interest (free, stable) — may fold into sentiment module.

### Backtesting (§1.5, §3 hard nos)
- Full backtesting platform = survivorship bias risk + scope explosion.
- Light vectorbt hooks in Phase 3 are acceptable for validating screens.
- Non-goal per PLAN.md §2 Goals.

### Order execution (§3.1, §3.7)
- SEBI broker license + KYC integration = regulatory burden with zero analytical edge.
- Terminal informs decisions; humans execute.
- Read-only Zerodha Kite portfolio overlay is a separate open question (BACKLOG.md Q3).

---

## Enforcement

When a feature request maps to this list, the answer is "no" — refer to `BACKLOG.md §3` (Hard Nos). Any scope expansion requires a new ADR and decision matrix.
