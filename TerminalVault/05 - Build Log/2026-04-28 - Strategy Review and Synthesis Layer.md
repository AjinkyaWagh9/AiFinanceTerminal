# 2026-04-28 — Strategy review + Synthesis Layer added (Phase 3 core)

> External feedback (input.md) flagged that flat macro dashboards produce no alpha. Restructured PLAN around a 3-layer heatmap and added a 5-component Synthesis Layer as Phase 3 *core*. Goal: compete with — not just imitate — JP Morgan-tier research tools.

**Trigger:** `input.md` review document. The author's correct push: probability + scenario + regime + signal-weighting beats information decoration. We extended further by identifying 3 capabilities JP can't structurally have (calibration tracking, bias auditor, variant-perception headline) — these become the moat.

---

## What changed (one commit, six edits)

| Edit | File | What |
|---|---|---|
| 1 | `finterminal/src/finterminal/prompts/analyst.md` | Prompt v2: factor hierarchy (6 ranked factors), Variant Perception headline, Conviction tiering replaces flat confidence |
| 2 | `docs/PLAN.md` §3 | Architecture diagram redrawn with Synthesis Layer + per-tier agent strip |
| 3 | `docs/PLAN.md` §6.5.F | Macro Overlay → 3-layer Heatmap (Global Risk / India Macro / Market Internals) + per-ticker factor betas |
| 4 | `docs/PLAN.md` §6.5.F2 | New Banking Health subsection — credit growth, GNPA/NNPA, CASA, NIM, deposits |
| 5 | `docs/PLAN.md` §6.6 | New Synthesis Layer: Regime Detector, Scenario Engine, Signal Weighter, Calibration Loop, Bias Auditor, Variant-Perception Checker, Pair/Relative |
| 6 | `docs/BACKLOG.md` | §1.3 + §1.7 promoted to Phase 3 core; §1.6 promoted Phase 4→3; new §1.12, §1.13, §1.14 |
| 6b | `TerminalVault/02 - Decisions/ADR-011 ...md` | Captures the design decision + cross-links |

## Strategic framing (the *why*)

A retail tool that imitates Bloomberg is automatically inferior — Bloomberg has more data and a 40-year head start. The asymmetric play is to do **what JP Morgan structurally can't**:

| Capability | Why JP can't / doesn't | We can |
|---|---|---|
| Calibration loop scoring own predictions | Career risk for analysts | No career — just track |
| Bias auditor surfacing systematic drift | Same | Same |
| Variant-perception headline (lead with disagreement) | Compliance + client-relationship hedging | Just tell yourself the truth |
| Hindi/regional sentiment via Grok | US-staffed desks miss it | Native via [[ADR-004 Grok over X API for sentiment]] |
| Promoter forensics with behavioral inference | Costly to license; less ROI per US dollar | High ROI in INR; data is free |

The first three are uncomfortable to publish externally. We don't publish; we just use them. That's the moat.

## What's NOT changing

- Phase 1 still complete; all current code stable
- Phase 2 multi-agent foundation unchanged
- Phase 2.5 analyst-grade layer unchanged in spec — only macro restructured
- Non-goals stand: no DCF, no alt-data, no backtesting platform, no execution. See [[ADR-007 Non-Goals — No DCF, No Alt-Data, No Backtesting]].

## Open questions (deferred to Phase 3 kickoff)
- Calibration Loop: claim→direction sufficient, or need paper-portfolio simulation? Lean simple-first.
- Bias Auditor cadence: weekly digest vs ambient `/analyze` warnings? Probably both.
- Scenario Engine: own LLM config or share supervisor? Probably own — higher stakes per call.

## Cross-links
- ADR: [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]]
- Affected pages: [[Phase 2.5 - Analyst-Grade Layer]] (Macro restructured), [[Phase 3 - US + Routing]] (now: Phase 3 — Synthesis + US)
- Original PLAN: [[00 - Project Overview]]
- Code changes (immediate): `finterminal/src/finterminal/prompts/analyst.md` v2 — every `/analyze` from now uses factor hierarchy + Variant Perception + Conviction tiers
