# FINTERMINAL — Backlog

Things deliberately not in `PLAN.md` Phases 1–3. Captured so nothing gets lost. Reviewed at every phase boundary.

**Last updated:** 2026-04-28

---

## How to use this file

- **Active deferrals** — will probably build, just not yet. Each has a target phase and a trigger condition that says "build this when X."
- **Cut, may revisit** — considered and rejected for now. Low ROI today; revisit only if the trigger fires.
- **Hard nos (non-goals)** — explicitly out of scope for the project. Listed so the answer to "should we add X?" is fast.
- **Open decisions** — questions that block scope; resolve before adding the dependent feature.

When promoting an item from backlog → plan: copy the row to `PLAN.md`, add a decision matrix and component spec, then strike it through here with the date.

---

## 1. Active deferrals (will build, later phase)

### 1.1 Sell-side research aggregation
- **Target phase:** 3
- **What:** scrape/aggregate broker reports, consensus rating distribution, target-price range, recent rating changes. Sources: Smartkarma snippets, Moneycontrol broker views, ICICI Direct/HDFC Sec free notes.
- **Why deferred:** depends on scraping infrastructure (rotating user agents, captcha handling, schema-versioned parsers) that Phase 2.5 doesn't need. Solving it now would slow 2.5 down.
- **Trigger:** after Phase 2.5 ships and you find yourself manually checking Moneycontrol broker views ≥3 times a week.
- **Effort:** ~5 days.

### 1.2 LangGraph migration of `/analyze` flow
- **Target phase:** 3
- **What:** rewrite the `/analyze` cycle in LangGraph for proper conditional re-fetch (e.g., if critic flags missing data, route back to Data Agent instead of completing with a gap).
- **Why deferred:** CrewAI is good enough through 2.5. Migration cost is real; do it once when the cyclical-critique requirement actually bites.
- **Trigger:** when ≥30% of `/analyze` runs need a re-fetch round, or when you want human-in-loop checkpoints.
- **Effort:** ~7 days.

### 1.3 ~~Probabilistic bull/bear with explicit weights~~ **PROMOTED to Phase 3 core (PLAN §6.6.2)**
- **Status:** No longer backlog. Promoted 2026-04-28 after input.md feedback established this as a competitive necessity, not a nice-to-have.
- **Now lives at:** PLAN.md §6.6.2 (Scenario Engine) as one of five Synthesis Layer components alongside Regime Detector, Signal Weighter, Calibration Loop, Bias Auditor.
- See [Promotion log](#5-promotion-log).

### 1.4 US market expansion
- **Target phase:** 3
- **What:** US tickers via Finnhub free tier, broader CEO list (Dimon, Fink, Pichai, Nadella). 13F holdings via SEC EDGAR. US event calendar (CPI, jobs, FOMC).
- **Why deferred:** Indian market mastery first — that's where you have edge and where data is uniquely free.
- **Trigger:** Phase 2.5 exit criteria met on Indian watchlist.
- **Effort:** ~7 days.

### 1.5 Light backtesting hooks
- **Target phase:** 3
- **What:** `/backtest <strategy>` runs vectorbt on the historical OHLCV in DuckDB. Output: equity curve, max drawdown, Sharpe. Strategies expressed as small Python files in `src/finterminal/strategies/`.
- **Why deferred:** non-goal per §2. But "light" hooks are worth it once you have screens (Phase 2.5) — natural to ask "would this screen have worked?"
- **Trigger:** Magic Formula / GARP screens are running and you want to validate them.
- **Effort:** ~4 days for hooks; bottomless rabbit hole if you let it grow.

### 1.6 Background alert scheduler
- **Target phase:** 3 *(promoted from Phase 4 — needed for regime-change push alerts)*
- **What:** daemon that watches the watchlist and fires alerts on configurable triggers (price move, sentiment flip, pledge change, transcript topic shift, consensus revision, **regime change from Detector**). Notification channels: macOS notifications, Telegram bot, optional email.
- **Why upgraded:** the Regime Detector (PLAN §6.6.1) is most valuable when it can wake you up at 9 AM IST if global flipped to risk-off overnight. Polling at the terminal misses pre-market regime shifts.
- **Trigger:** Phase 3 Scenario Engine + Regime Detector working.
- **Effort:** ~4 days.

### 1.7 ~~Confidence calibration tracking~~ **PROMOTED to Phase 3 core (PLAN §6.6.4)**
- **Status:** No longer backlog. Promoted 2026-04-28.
- **Now lives at:** PLAN.md §6.6.4 (Calibration Loop) — the trust-building layer that JP Morgan structurally cannot build for itself (career risk for analysts).
- **What's new vs. the old backlog entry:** explicit Brier scoring, reliability diagram, tier-by-tier calibration; surfaced in every `/analyze` footer, not just `/calibration`.
- See [Promotion log](#5-promotion-log).

### 1.8 Export reports (Markdown + PDF)
- **Target phase:** 4
- **What:** `/report RELIANCE` produces a Markdown analyst-style note with citations; optional Pandoc → PDF. Useful for sharing or for your own archive outside the terminal.
- **Why deferred:** read-only use is fine until you want to send the work to someone.
- **Trigger:** first time you want to send analysis to another person.
- **Effort:** ~2 days.

### 1.9 Caching layer (DiskCache or Redis)
- **Target phase:** 4
- **What:** explicit cache layer in front of OpenBB and scrapers. TTL per data type (quotes 60s, fundamentals 24h, ownership weekly).
- **Why deferred:** DuckDB itself is the cache for now. Add a real cache when API rate limits or scraping politeness force it.
- **Trigger:** OpenBB / Trendlyne / SEBI rate-limit you, or fetch latency exceeds 1s on warm queries.
- **Effort:** ~2 days.

### 1.10 exo distributed inference
- **Target phase:** 3+
- **What:** cluster M4 Air with a second Apple device (Mac mini, iPad, second laptop) via exo to run 70B-class models locally.
- **Why deferred:** single-machine + Claude + NIM cover the gap. Pure speculative until you actually own a second device.
- **Trigger:** acquire a second Apple device AND find a workload that NIM/Claude can't cover well.
- **Effort:** ~3 days setup + tuning.

### 1.11 Quant screen library expansion
- **Target phase:** 3
- **What:** beyond the 5 canonical screens in Phase 2.5 (Magic Formula, GARP, Dividend, QARP, Distress) — add Acquirer's Multiple, Greenblatt + Quality, Net-Net, low-vol factor, momentum + quality combo.
- **Why deferred:** 5 screens cover 80% of canonical retail strategies. Diminishing returns past that.
- **Trigger:** you're modifying existing screens for personal twists ≥3 times a month.
- **Effort:** ~1 day per screen.

### 1.12 Regime-tilted screen overlays
- **Target phase:** 3 (after Regime Detector ships)
- **What:** screens auto-tilt their thresholds based on current regime. In `risk_off`: defensive cyclicals + low D/E + dividend-yielders bubble up. In `risk_on` early-cycle: high-beta + cap-light growth. The same `/screen garp` returns different results in different regimes.
- **Why deferred:** depends on §6.6.1 Regime Detector landing first.
- **Trigger:** Regime Detector running for ≥30 days with reasonable rule-based stability.
- **Effort:** ~3 days.

### 1.13 Promoter behavioral inference (forensic add-on)
- **Target phase:** 3
- **What:** layer on top of §6.5.C Ownership data. Detects: clusters of promoter sells over rolling 90d, repeat guidance miss patterns, history of restating financials, frequent auditor changes, related-party transaction spikes.
- **Why deferred:** §6.5.C provides the raw inputs (SAST, pledges, shareholding); inference layer adds scoring/alerting on top.
- **Trigger:** Phase 2.5 ownership ingestion has ≥4 quarters of history.
- **Effort:** ~5 days.
- **Why this is Indian-specific alpha:** US disclosure regimes are stricter; Indian markets have repeat patterns (Vakrangee, Manpasand, DHFL, Yes Bank) where promoter behavior leaked the issue 6+ months before price discovery.

### 1.14 Per-ticker macro factor exposure (replaces sectoral betas)
- **Target phase:** 3 *(can ship with §6.5.F2 Banking Health if the data pipeline overlaps)*
- **What:** replace coarse sectoral beta table with per-ticker rolling-window factor regression. INFY's USD/INR β ≠ TCS's. ONGC's Brent β ≠ HPCL's. Surfaces in `/factor TICKER FACTOR` and feeds the Signal Weighter.
- **Why deferred from immediate Phase 2.5:** sectoral betas (in §6.5.F current schema as `sector_macro_betas`) are good enough to start; per-ticker is a straightforward upgrade once the macro_series table is populated.
- **Trigger:** Phase 2.5.F lands with ≥1y of macro_series rows.
- **Effort:** ~3 days.

### 2.1 DCF / SOTP modeling layer
- **Why cut:** analysts live in Excel for this. Replicating well = months of work. Even a "light" version is uncannily error-prone (revenue drivers, segment reporting, terminal value sensitivity, tax shields, cross-holding adjustments).
- **Revisit if:** you genuinely stop opening Excel for valuation work, OR you find yourself building DCFs in DuckDB by hand.
- **What "light" might look like (if revisited):** `/dcf RELIANCE` pulls 5Y financials, applies templated growth/margin/WACC defaults, outputs implied per-share value with sensitivity table on growth and discount rate. No segment-level modeling.
- **Effort if pursued:** 10 days for light, 30+ days for usable.

### 2.2 Alternative data (LinkedIn hiring, SimilarWeb, app downloads)
- **Why cut:** most APIs are paid (Yipit, Sensor Tower, SimilarWeb Pro). Free LinkedIn scraping is fragile (rate limits, account bans). Signal-to-noise is genuinely high but cost/maintenance kills it for individual use.
- **Revisit if:** a free, sustainable source emerges, OR you're willing to spend ≥$500/mo, OR you find a niche (e.g., specific company you can do deep channel checks on manually).
- **What might survive:** Google Trends for ticker/brand search interest is free and stable — could fold into the sentiment module.
- **Effort if pursued:** 5–15 days depending on sources.

### 2.3 Tegus-style expert call network
- **Why cut:** can't replicate. Tegus has paid expert networks, NDAs, proprietary call library. No free analog exists.
- **Revisit:** never. Substitute = company concall transcripts (already in 2.5) + industry conference YouTube uploads (CEO Tracker).

### 2.4 Geospatial / satellite imagery for supply chains
- **Why cut:** mentioned in `context.md` Phase 3 as "deprioritize if complex." It is complex. Free satellite data (Sentinel, Landsat) requires geospatial pipeline expertise; commercial (Planet, Orbital Insight) is expensive.
- **Revisit if:** you find a specific supply-chain question worth answering (e.g., port congestion at Mundra, parking lot fill at malls).
- **Effort if pursued:** 10+ days, plus subject-matter judgment.

### 2.5 Mobile / web clients
- **Why cut:** terminal is the product. Mobile/web means rebuilding the UI in React Native / Next.js — duplicates effort, dilutes focus.
- **Revisit if:** the terminal is the daily driver and you genuinely need read-only mobile access. Even then, prefer a "send report to phone" hook over a full mobile app.

### 2.6 Order execution / brokerage integration
- **Why cut:** regulatory burden (SEBI broker license, KYC integration), no analytical edge from execution. The terminal informs decisions; humans execute.
- **Revisit:** never as a project goal. **Read-only** Zerodha Kite portfolio overlay is a separate question (see §4 below).

### 2.7 Options analytics, derivatives chains
- **Why cut:** different mental model from equity research; would dilute the analyst-grade focus. Adding Greeks, IV surfaces, strategy P&L visualizers is a project of its own.
- **Revisit if:** your investing style genuinely shifts to options-led.
- **Effort if pursued:** 15+ days.

### 2.8 Multi-user / multi-portfolio
- **Why cut:** single-user tool. Adding auth, isolation, multi-tenancy would 3× the codebase for zero personal benefit.
- **Revisit:** only if open-sourcing AND community asks (see §4 Q6).

### 2.9 Internal "research notes" / journaling
- **Why cut:** Obsidian, Notion, Apple Notes already exist and are better at this. The terminal can *export* to a notes app; it shouldn't try to *be* one.
- **Mitigation:** `/report` (§1.8) covers the "save my analysis" use case.

### 2.10 Slack / Telegram chat bot front-end
- **Why cut:** chat-as-UI loses the dense Bloomberg-style dashboard. Reasonable for *alerts* (see §1.6) but not for queries.

---

## 3. Hard nos (non-goals)

These are out of scope for the project's lifetime, not just this phase. If a feature request maps to one of these, the answer is no — refer to this list.

| # | Non-goal | Why |
|---|---|---|
| 3.1 | Order execution | Regulatory + zero analytical edge |
| 3.2 | Robo-advisory / portfolio recommendations | Liability, not the point |
| 3.3 | Multi-tenant SaaS | Single-user product |
| 3.4 | Real-time tick-level market data | Bloomberg's moat; price-prohibitive; not needed for research-grade work |
| 3.5 | Crypto / NFTs | Different domain, different data, different mental model |
| 3.6 | News-feed-as-product (i.e., competing with Moneycontrol/ET) | Aggregation is a means, not the product |
| 3.7 | Auto-trading / signal-driven execution | See 3.1 + survivorship bias risk |

---

## 4. Open decisions (block specific scope)

| # | Question | Blocks | Owner | Target date |
|---|---|---|---|---|
| Q3 | Zerodha Kite read-only portfolio overlay? | Whether `/portfolio` becomes a Phase 3 command or stays in backlog | You | Before Phase 3 kickoff |
| Q4 | Final 10-name CEO list for Phase 2.5 | CEO Tracker scope | You | Before Phase 2.5 kickoff (~week 5) |
| Q5 | Realistic time budget — full-time, or part-time around day job? | Phase durations in §6 | You | Before Phase 1 kickoff |
| Q6 | Open-source the project? | Repo visibility, README polish, license choice, community-facing decisions | You | Before Phase 4 |

---

## 5. Promotion log

When an item moves from backlog → `PLAN.md`, log it here.

| Date | Item | Promoted to | Notes |
|---|---|---|---|
| 2026-04-28 | §1.3 Probabilistic bull/bear with explicit weights | PLAN §6.6.2 Scenario Engine | Driven by input.md feedback. Promoted from "deferred Phase 3" to Phase 3 *core*. Now part of the Synthesis Layer that's the actual edge over JP Morgan. |
| 2026-04-28 | §1.7 Confidence calibration tracking | PLAN §6.6.4 Calibration Loop | Same driver. Calibration is the trust-building layer that JP analysts can't have for career reasons. Promoted to Phase 3 core. |
| 2026-04-28 | §1.6 Background alert scheduler | PLAN §6.6.1 (regime alerts) + Phase 3 | Promoted from Phase 4 → Phase 3. The Regime Detector is most valuable when it can wake you up at 9 AM IST on a regime flip. |
