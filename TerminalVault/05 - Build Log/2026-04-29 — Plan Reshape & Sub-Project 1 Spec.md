# 2026-04-29 — Plan Reshape & Sub-Project 1 Spec

**TL;DR:** Planning-only session. input.md critique absorbed; build plan reshaped into 4 sub-projects. Sub-project #1 ("Foundation: Outcomes Ledger + Engine Taxonomy") fully specced and planned. No code shipped.

**Predecessor:** [[05 - Build Log/2026-04-29 — Sprint B-2a News Trend]]
**Active spec:** `docs/superpowers/specs/2026-04-29-foundation-outcomes-engines-design.md`
**Active plan:** `docs/superpowers/plans/2026-04-29-foundation-outcomes-engines.md`

---

## (a) input.md — Load-Bearing Critique

| Critique | Assessment |
|---|---|
| No way to prove the system makes money | **Correct and load-bearing** — the only critique that matters |
| Cut features / rename / focus | Downstream of the above gap; rejected as framing issues |

The critique is not about feature count. The system emits signals (news cluster momentum, analyst conviction tiers, etc.) but has no mechanism to track whether those signals predicted forward returns. Without a measurement layer, every output is unfalsifiable narrative.

---

## (b) 4-Sub-Project Decomposition

| # | Name | Status |
|---|---|---|
| 1 | Foundation: Outcomes Ledger + Engine Taxonomy | **Active — specced 2026-04-29** — see [[02 - Decisions/ADR-017 — Outcomes Ledger as the System's Moat]] |
| 2 | `/analyze` 5-engine card reshape | Blocked on #1 |
| 3 | `mgmt_claims` ledger (management claims scoring) | Blocked on #1 |
| 4 | Sentiment routing (Reflexivity engine wiring) | Blocked on #1 |

All four sub-projects are measurement or falsifiability work. No new analysis features added until sub-project #1 lands.

---

## (c) Dual-Pipeline Architectural Decision

See [[02 - Decisions/ADR-018 — Bhavcopy Market Data as Independent Peer Pipeline]] for full rationale.

| Pipeline | Source | Purpose | Owns |
|---|---|---|---|
| RSS / news (existing, B-2a) | Moneycontrol, Mint, ET, Reuters RSS | Narrative discovery — **what happened** | `news_clusters`, `news_stories` |
| NSE Bhavcopy daily zip (new, sub-project #1) | `nsearchives.nseindia.com` | Market truth — **whether the market cared** | `prices_eod`, `ingestion_log` |
| Outcomes ledger (new, sub-project #1) | Merges both above | **Did this signal predict forward returns vs Nifty 50?** | `signals`, `signal_outcomes` |

Merge point: `outcomes/backfill.py` reads `prices_eod` (owned by `market_data/`) to resolve forward returns for signals emitted by the news pipeline. The two upstream pipelines never import each other.

---

## What Comes Next

- Phase 2 B-2b (`/analyze` enrichment) is **paused** pending sub-project #1 — see [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- Sub-project #1 plan has 15 TDD tasks; implementation begins next coding session
- 173 tests currently passing; target: 173 + new coverage ≥ 80% for new modules

---

## Cross-Links

- ADR: [[02 - Decisions/ADR-017 — Outcomes Ledger as the System's Moat]]
- ADR: [[02 - Decisions/ADR-018 — Bhavcopy Market Data as Independent Peer Pipeline]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- Predecessor: [[05 - Build Log/2026-04-29 — Sprint B-2a News Trend]]
