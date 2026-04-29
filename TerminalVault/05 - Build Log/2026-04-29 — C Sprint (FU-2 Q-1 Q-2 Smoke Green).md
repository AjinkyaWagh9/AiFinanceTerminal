# 2026-04-29 — Sprint C (FU-2 + Q-1 + Q-2) Smoke Green

**TL;DR:** Phase-2 follow-up sprint "C" shipped and verified live against `/analyze ITC` on 2026-04-29. All three target outcomes confirmed: conglomerate guard fired (Confidence 0.50, all 5 ITC segments named), Critic issues are now substance-based (no tag-format noise), severity rubric calibrated (3 MEDIUM + 3 LOW + 0 HIGH). Tests went from 77 → 93 (+16 new tests). Ruff clean.

**Predecessor (same day):** [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]
**Spec:** `docs/superpowers/specs/2026-04-29-prompt-rewrite-fu2-q1-q2.md`

---

## Commits

| SHA | Type | Summary |
|---|---|---|
| `cc16a01` | test | Add tag-discipline regression tests (FU-2, red) — `tests/agents/test_tag_discipline.py`, 5 tests pinning the contract that dossier and context-block must emit the same `[src: ...]` tag vocabulary |
| `e17bfa6` | fix(dossier) | Align `_dossier.py` tags with context-block convention (dotted-path) — root cause of FU-2; now a faithful subset of `build_context_block`'s tag vocabulary; surfaces volume + market_cap |
| `3244943` | prompt(analyst) | Explicit src-tag whitelist + conglomerate guard — 12-tag HARD CONSTRAINT section; principle #8 conglomerate guard (caps Confidence ≤ 0.55, forces segmental P&L disclosure, requires by-name assumption list) |
| `7889024` | prompt(critic) | Defined severity rubric + collegial tone (Q-1) — criteria-based HIGH/MEDIUM/LOW; "≤2 high, ≤4 medium" calibration nudge; verdict thresholds ACCEPT/REVISE/REJECT; `[HIGH]`/`[MEDIUM]`/`[LOW]` bracketed prefix output |

---

## Root-cause summary (FU-2)

| Layer | Before | After |
|---|---|---|
| `_dossier.py` tags | `[QUOTE]`, `[FUND-PE]`, `[NEWS-1]` short-codes | `[src: quote.last_price]`, `[src: fundamentals.pe_ttm]`, `[src: news[0]]` dotted-path |
| `prompts/analyst.md` | Free-form `[src: ...]` reference | Explicit 12-tag whitelist; fallback: "data unavailable in SOURCES" |
| `prompts/critic.md` | Bare `severity: high\|medium\|low` | Criteria-defined rubric; bracketed prefix; calibrated distribution |
| Critic behaviour | Flagged tag-format mismatch as issues | Issues are now purely substance-based |

---

## Files affected

| File | Change |
|---|---|
| `src/finterminal/agents/_dossier.py` | Rewrote tag emission to dotted-path; added volume + market_cap fields |
| `src/finterminal/prompts/analyst.md` | New "Source tags (HARD CONSTRAINT)" section; principle #8 conglomerate guard |
| `src/finterminal/prompts/critic.md` | Severity rubric with criteria; verdict thresholds; tone reframe to senior peer-reviewer |
| `tests/agents/test_tag_discipline.py` | New — 5 tests (contract: dossier ∩ context-block tag vocabulary) |
| `tests/agents/test_analyst_prompt_rules.py` | New — 5 tests pinning every load-bearing phrase in analyst.md |
| `tests/agents/test_critic_prompt_rules.py` | New — 6 tests pinning critic.md structure |
| `tests/agents/test_dossier.py` | Updated 6 tests to assert dotted-path tags |
| `tests/agents/test_data_agent.py:91-93` | Updated to assert dotted-path |

---

## Smoke verification — `/analyze ITC` (live)

| Target signal | Expected | Observed |
|---|---|---|
| Conglomerate guard fires | Confidence ≤ 0.55; assumptions name all segments | Confidence = 0.50; assumptions: "my confidence is capped per the Conglomerate guard"; lists FMCG, Hotels, Paperboards, Agri, Cigarettes |
| Critic tag-format noise absent | No "tags don't match SOURCES" issues | Issues are substance-based: peer data missing, forward estimates absent, falsifiable thresholds lacking |
| Severity rubric calibrated | ≤2 HIGH; mix of MEDIUM + LOW | 0 HIGH, 3 MEDIUM, 3 LOW — within calibration envelope |

---

## Test count

| State | Count |
|---|---|
| Before sprint C | 77 |
| After sprint C | 93 |
| New tests | +16 |

---

## New follow-ups surfaced

- **Q-5 (data-layer hardening):** yfinance returns "possibly delisted" / `EmptyDataError` for valid Indian symbols (e.g., `RELIANCE.NS`) when throttled; quote-provider chain bails entirely instead of falling through to alternate providers. Fix: graceful provider fallthrough on yfinance throttle. Tracked in [[03 - Phases/Phase 2 - Multi-Agent Foundation]] backlog.
- **Q-6 (UI rendering bug, pre-existing):** Rich panel renderer silently strips `[src: quote.last_price]`-style tags from the displayed `analysis_panel` output — Rich interprets dotted bracketed text as failed style markup. Tags ARE emitted (Critic verifies in raw text). Fix: escape brackets before passing to Rich's `Panel`/`Text` constructors, or use `Text(..., markup=False)`. Sized: 30–60 min. Cosmetic only, not blocking. Tracked in [[03 - Phases/Phase 2 - Multi-Agent Foundation]] backlog.

---

## What is NOT changing

- Critic parser unchanged — reads sections, not severity tokens; `[HIGH]`/`[MEDIUM]`/`[LOW]` prefix is for panel rendering only.
- Phase 2 / 4b News & Trend and Phase 3 LangGraph migration scope unchanged.
- `agents/analyze_flow.py` orchestration untouched — prompt-layer-only sprint.

---

## Cross-links

- Predecessor (same day): [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]
- ADR: [[02 - Decisions/ADR-014 Single Tag Convention dotted-path]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- Code map: [[04 - Code Map/agents — _dossier]] · [[04 - Code Map/prompts]]
- Spec: `docs/superpowers/specs/2026-04-29-prompt-rewrite-fu2-q1-q2.md`
