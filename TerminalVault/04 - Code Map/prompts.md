# Code Map — prompts/

> Back to [[Index]] | See also [[agents — supervisor]] · [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] · [[ADR-005 Sentiment is Optional Feature-Flagged Module]]

**Directory:** `src/finterminal/prompts/`

These are the system prompts loaded by agents. Markdown source-of-truth. Edit in place — agents read on every call (no compile step).

---

## File inventory

| File | Loaded by | Phase | Lines |
|---|---|---|---:|
| `analyst.md` | Supervisor agent (`agents/supervisor.py:_load_system_prompt`) | 1 (live) | ~70 |
| `critic.md` | Critic agent (Phase 2) | 2 | ~30 |
| `supervisor.md` | Multi-agent supervisor (Phase 2 dispatcher prompt) | 2 | ~25 |

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

---

## `critic.md` — Phase 2

Adversarial review prompt. Runs on every `/analyze` output once the Critic agent is wired (Phase 2). Flags:
- Unsourced numeric claims
- Missing context that would have changed the conclusion (no pledge check, no macro headwind, etc.)
- Whether the bear case is crisp + falsifiable, or boilerplate
- Confidence calibration (>0.7 had better be earned; <0.4 means "did the analysis even reach a conclusion")

**Output:**
```
## Issues
- <severity: high|medium|low>
## Missing Data
- <what was not consulted>
## Confidence Adjustment
<recommended confidence + one-line rationale>
## Verdict
ACCEPT | REVISE | REJECT
```

If Verdict = REVISE / REJECT, Phase 3 LangGraph migration ([[ADR-002 CrewAI then LangGraph]]) will route back to Data Agent for re-fetch before returning to user.

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
