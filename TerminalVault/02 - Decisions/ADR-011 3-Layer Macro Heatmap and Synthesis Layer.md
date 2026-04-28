# ADR-011 — 3-Layer Macro Heatmap + Synthesis Layer (Phase 3)

> Adopt a 3-layer Bloomberg-tier macro structure (Global Risk / India Macro / Market Internals) and add a five-component Synthesis Layer (Regime Detector, Scenario Engine, Signal Weighter, Calibration Loop, Bias Auditor) as Phase 3 *core* — not deferred.

**Status:** Accepted
**Date:** 2026-04-28
**Source:** PLAN.md §3 (revised diagram), §6.5.F (3-layer heatmap + Banking Health depth), §6.6 (Synthesis Layer)
**Drivers:** [[input.md feedback (2026-04-28)]] — external review flagged that flat macro overlays produce no alpha; "elite version" requires regime/probability/scenario/signal-weighting/backtesting, plus banking depth beyond Bank Nifty.

---

## Context

Prior PLAN had a single-section `§6.5.F Macro Overlay` listing ~12 macro tickers in a flat grid, with sectoral betas precomputed quarterly. This is what every retail dashboard does, and the input.md author correctly flagged it as **information decoration without alpha**:

> *Most retail dashboards look intelligent but produce no alpha. They are information decoration.*

The author's prescription:
1. Restructure macro into 3 layers: Global Risk, India Macro, Market Internals
2. Banking Health needs depth (credit growth, GNPA, CASA, NIM) — Bank Nifty alone is shallow
3. Build probability + scenario + regime + signal-weighting + light backtesting

We accept all three. We also push further to identify what specifically beats a JP Morgan analyst desk — capabilities that require *not* being a sell-side firm.

## Decision

### 1. Macro restructured into 3 layers (replaces single Macro Overlay)
- **Layer 1 — Global Risk** — S&P/Nasdaq + futures, US 2Y/10Y, DXY, Brent, gold, copper, VIX, India VIX
- **Layer 2 — India Macro** — CPI, WPI, PMI (mfg + services), IIP, GST collections, repo + OIS-implied repo expectations, India 10Y, USD/INR, FX reserves
- **Layer 3 — Market Internals** — FII/DII flows, A/D ratio, % above 50/200 DMA, sector rotation (relative strength), NIFTY PE percentile, EY-vs-bond-yield spread, NIFTY EPS revision velocity
- **Per-ticker factor betas** replace coarse sectoral betas — INFY's USD/INR β ≠ TCS's

### 2. Banking Health subsection (§6.5.F2)
Per-bank + system-wide: credit growth, GNPA/NNPA, restructured book, CASA, deposit growth, NIM, CET1, yield-on-advances, cost-of-funds. Sources: RBI weekly + monthly bulletin, bank quarterly results (already in transcripts pipeline).

### 3. Synthesis Layer (PLAN §6.6) — five Phase 3 core components
| Component | Purpose | JP-can't-do-this |
|---|---|---|
| **Regime Detector** | Tags every output `risk_on / risk_off / transition_*`. Rules-based v1 on Layer 1+2 z-scores | Macro strategists exist but aren't integrated into single-name calls |
| **Scenario Engine** | Explicit P(bull)/P(base)/P(bear) over 1m/3m/6m + price ranges per scenario | Sell-side notes give point targets, not probability distributions |
| **Signal Weighter** | Composite [-1,+1] with conviction tier (Conviction Long / Watch / Avoid / Conviction Short) and factor decomposition | Done internally but compliance prevents publishing variant tiers publicly |
| **Calibration Loop** | Brier score on own predictions, surfaces hit-rate by tier in every `/analyze` footer | Career risk to score analysts publicly on calibration |
| **Bias Auditor** | Weekly meta-analysis of own output drift (direction bias, sector bias, confidence drift) | Same career-risk constraint |

Plus the **Variant-Perception Checker** in the Critic agent: every `/analyze` opens with where you disagree with consensus, or flags itself as non-variant.

### 4. Default factor weights (input.md author's hierarchy)
Bull/bear synthesis prompt and Signal Weighter both use this as the default prior:

1. Global liquidity / regime fit — 25%
2. Earnings momentum + revisions — 25%
3. Valuation vs history — 20%
4. Domestic macro — 10%
5. Positioning / flows — 15%
6. News noise — 5%

Customizable in `config/weights.yaml`.

## Consequences

**Positive**
- Phase 3 stops being a vague "polish" bucket and becomes the actual moat
- Calibration Loop creates compounding trust — the longer it runs, the more useful it gets, structurally
- Bias Auditor is novel — most quant tools have it; most discretionary tools don't; sell-side never does
- Variant Perception focus front-loads alpha in every output, not buried in paragraph 4
- 3-layer heatmap maps cleanly to the regime-detection inputs
- Banking depth closes one of the project's biggest blind spots given Indian portfolio realities

**Negative / risks**
- More infrastructure: 5 new agents in §6.6, 4+ new schema tables (regime_history, scenarios, signal_scores, predictions, outcomes, calibration_summary)
- Calibration Loop only delivers value after ≥3 months of accumulated predictions — slow ramp
- Regime classifier rules-based v1 will misclassify obvious cases initially; needs hand-tuning before the alert daemon trusts it
- Bias Auditor depends on Calibration Loop having data; second-order dependency
- Scope creep risk: scenario engine could grow into DCF territory (§2.1 hard non-goal) — discipline needed

**What this does not change**
- Phase 1 is still complete (current state)
- Phase 2 multi-agent foundation is unchanged
- Phase 2.5 analyst-grade layer is unchanged in spec; only Macro section (§6.5.F) restructured
- Non-goals (no DCF, no alt-data, no backtesting platform, no execution) stand

## Promotions from BACKLOG (recorded in promotion log)
- §1.3 Probabilistic bull/bear → PLAN §6.6.2 (now Phase 3 core)
- §1.7 Confidence calibration tracking → PLAN §6.6.4 (now Phase 3 core)
- §1.6 Background alert scheduler → Phase 3 (was Phase 4) — driven by regime alert needs

## New BACKLOG entries from this ADR
- §1.12 Regime-tilted screen overlays
- §1.13 Promoter behavioral inference (forensic add-on)
- §1.14 Per-ticker macro factor exposure (replaces sectoral betas)

## Open
- **Q-ADR011-1:** does the Calibration Loop need a paper-portfolio component (i.e., simulated trades to score) or is `claim → realized direction` sufficient? Decide before §6.6.4 ships.
- **Q-ADR011-2:** Bias Auditor cadence — weekly digest vs ambient warnings inside `/analyze` panels. Probably both.
- **Q-ADR011-3:** does the Scenario Engine get its own LLM provider config (it's higher-stakes than `/analyze`) or share `supervisor`?

## Cross-links
- Triggered by [[input.md feedback (2026-04-28)]]
- Supersedes flat-macro-overlay framing in [[ADR-008 Phase 2.5 Analyst-Grade Layer]]
- Implements weights from `prompts/analyst.md` v2 (factor hierarchy added 2026-04-28)
- Affects: [[Phase 2.5 - Analyst-Grade Layer]] (§6.5.F restructured), [[Phase 3 - US + Routing]] (renamed conceptually to "Synthesis Layer")
- Related: [[ADR-007 Non-Goals — No DCF, No Alt-Data, No Backtesting]] (Scenario Engine must NOT cross into DCF)
