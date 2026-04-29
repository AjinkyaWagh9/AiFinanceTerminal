# Code Map — prompts/

> Back to [[Index]] | See also [[agents — supervisor]] · [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] · [[ADR-005 Sentiment is Optional Feature-Flagged Module]]

**Directory:** `src/finterminal/prompts/`

These are the system prompts loaded by agents. Markdown source-of-truth. Edit in place — agents read on every call (no compile step).

---

## File inventory

| File | Loaded by | Phase | Lines | Last major change |
|---|---|---|---:|---|
| `analyst.md` | Supervisor agent (`agents/supervisor.py:_load_system_prompt`) | 1 (live) | ~90 | 2026-04-29 commit `3244943` — tag whitelist + conglomerate guard |
| `critic.md` | Critic agent (Phase 2) | 2 | ~45 | 2026-04-29 commit `7889024` — severity rubric + tone reframe |
| `supervisor.md` | Multi-agent supervisor (Phase 2 dispatcher prompt) | 2 | ~25 | — |

---

## `analyst.md` — current production prompt

**Loaded by:** `analyze_ticker()` at `src/finterminal/agents/supervisor.py:_load_system_prompt`.

**Output schema (parsed by `parse_analysis()`):**
```
## Variant Perception   ← magenta panel; suppressed if "no consensus in context"
## Bull Case            ← green panel
## Bear Case            ← red panel
## Conviction           ← Conviction Long ▲▲ / Watch Long ▲ / Avoid — / Conviction Short ▼▼ / Pair-Short ▼
## Confidence           ← float in [0, 1]; gauge color: green ≥ 0.7, yellow ≥ 0.4, red < 0.4
## Assumptions          ← cyan panel
## What Would Change My Mind  ← cyan panel
```

**v2 upgrade (commit `47b210d`)** — driven by [[input.md feedback (2026-04-28)]]:
- 6-factor weighting hierarchy now baked in: (1) global liquidity / US yields, (2) earnings momentum + revisions, (3) valuation vs history, (4) domestic macro, (5) positioning / flows, (6) news noise. Bull/bear must lead with the highest-tier factor.
- `## Variant Perception` opens every output. Forces alpha to be explicit.
- `## Conviction` replaces flat-confidence-only output with a structural rating actionable for sizing.
- `## Confidence` stays — calibrator on top of Conviction. Will be Brier-scored in Phase 3 ([[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] §6.6.4).

**Operating principles (in the prompt):**
1. **Source discipline** — every numeric tagged `[src: <field>]` or "data unavailable"; never invent
2. **Factor weighting hierarchy** — see above
3. **Variant Perception** — open with disagreement vs consensus
4. **Conviction tiering** — map factor alignment to one of 4 tiers
5. **Rich Dad lens** — assets vs liabilities; flag multiple-expansion vs earnings-growth dependencies
6. **Stoic uncertainty** — explicit assumptions; calibrate (0.9 should be rare; default 0.4–0.7)
7. **Munger inversion** — articulate how the thesis fails
8. **Conglomerate guard (added 2026-04-29, commit `3244943`)** — for multi-segment Indian conglomerates (Reliance, ITC, L&T, Adani Enterprises, Bajaj Finserv, Tata, Mahindra, Aditya Birla), forces explicit assumption-disclosure listing all segments by name, caps Confidence at 0.55, and adds segmental P&L trigger to "What Would Change My Mind"

**Source tag whitelist (HARD CONSTRAINT, added 2026-04-29):** 12 valid tags enumerated in the prompt. Analyst must use only these or cite "data unavailable in SOURCES". Fabricating tags outside the whitelist is a prompt-level violation.

Valid tags:
- `[src: quote.last_price]`, `[src: quote.volume]`, `[src: quote.market_cap]`
- `[src: fundamentals.pe_ttm]`, `[src: fundamentals.pb]`, `[src: fundamentals.roe]`, `[src: fundamentals.revenue_ttm]`, `[src: fundamentals.net_income_ttm]`, `[src: fundamentals.debt_equity]`
- `[src: news[0]]` … `[src: news[N]]`
- `[src: macro.*]` (any macro sub-field)

Tag convention decision: [[02 - Decisions/ADR-014 Single Tag Convention dotted-path]]

---

## `critic.md` — Phase 2

Senior peer-reviewer prompt (reframed from adversarial, 2026-04-29 commit `7889024`). Runs on every `/analyze` output. Flags:
- Unsourced numeric claims
- Missing context that would have changed the conclusion (no pledge check, no macro headwind, etc.)
- Whether the bear case is crisp + falsifiable, or boilerplate
- Confidence calibration (>0.7 had better be earned; <0.4 means "did the analysis even reach a conclusion")

**Severity rubric (defined 2026-04-29):**

| Severity | Criteria |
|---|---|
| `HIGH` | Fabricated tag (not in analyst whitelist) OR claim directly contradicts SOURCES |
| `MEDIUM` | Unsourced AND material to bull/bear conclusion |
| `LOW` | Unsourced + stylistic OR vague + non-load-bearing |

Calibration nudge: ≤2 HIGH, ≤4 MEDIUM expected per run.

**Output format (updated 2026-04-29):**
```
## Issues
- [HIGH]/[MEDIUM]/[LOW] <issue description>
## Missing Data
- <what was not consulted>
## Confidence Adjustment
<recommended confidence + one-line rationale>
## Verdict
ACCEPT | REVISE | REJECT
```

**Verdict thresholds:**
- `ACCEPT` — no HIGH issues
- `REVISE` — ≥1 MEDIUM or HIGH issue
- `REJECT` — multiple HIGH issues OR >30% citation failures

Note: Critic parser reads sections, not severity tokens — `[HIGH]`/`[MEDIUM]`/`[LOW]` prefix is for panel rendering only (bracketed prefix does not affect parser logic).

If Verdict = REVISE / REJECT, Phase 3 LangGraph migration ([[ADR-002 CrewAI then LangGraph]]) will route back to Data Agent for re-fetch before returning to user.

**Smoke result (2026-04-29, `/analyze ITC`):** 0 HIGH + 3 MEDIUM + 3 LOW. No tag-format complaints — issues are substance-based only.

---

## `supervisor.md` — Phase 2

Multi-agent dispatcher prompt. Phase 2+ only. Phase 1's "supervisor" is actually the analyst prompt — there's no delegation yet, just a single LLM call. This file becomes load-bearing once CrewAI is wired and Supervisor decomposes queries across Data / News / Critic agents.

Operating principles:
1. Decompose explicitly — state the sub-questions before delegating
2. Cite specialists — when output came from Data Agent, News Agent, etc.
3. Synthesize, don't regurgitate — surface cross-cutting insight
4. Defer to Critic on REVISE / REJECT

---

## Editing discipline

- **No prompt prose without a citation point.** Every operating principle should have a known failure mode it prevents (e.g. source-discipline prevents number hallucinations).
- **Test prompt changes live.** A prompt-only edit can't break tests but CAN break output structure — re-run `/analyze RELIANCE` after every change.
- **Document v2/v3 in the same file.** Don't fork. Keep the history in commit messages + the build log ([[2026-04-28 - Strategy Review and Synthesis Layer]] for v2).

---

## Phase 2.5 / Phase 3 additions (planned)

| Future prompt | Purpose | ADR |
|---|---|---|
| `transcript_extract.md` | Topic + guidance extraction from concall transcripts | [[ADR-008 Phase 2.5 Analyst-Grade Layer]] |
| `transcript_synthesize.md` | Synthesis of YoY/QoQ language drift | [[ADR-008 Phase 2.5 Analyst-Grade Layer]] |
| `regime_detector.md` | Layer 1+2 z-scores → regime label + rationale | [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] §6.6.1 |
| `scenario_engine.md` | P(bull)/P(base)/P(bear) per ticker, structured JSON output | [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] §6.6.2 |
| `bias_auditor.md` | Weekly meta-analysis of own output drift | [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] §6.6.5 |

---

## Cross-links

- ADR: [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] (factor hierarchy + Conviction + Variant Perception came from here)
- Code map: [[agents — supervisor]] (consumes `analyst.md`)
- Build log: [[2026-04-28 - Strategy Review and Synthesis Layer]] (analyst.md v2 commit)
