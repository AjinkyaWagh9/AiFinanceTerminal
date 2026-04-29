# Spec — Prompt rewrite: FU-2 (tag drift) + Q-1 (critic severity) + Q-2 (conglomerate)

**Date:** 2026-04-29
**Author:** Claude (Opus 4.7)
**Phase:** 4b — Phase 2 follow-up after 4a smoke
**Predecessor:** `2026-04-28-multi-agent-scaffold-4a-design.md`
**Time budget:** 3-5 hrs (Day 1 of the May-1 sprint)

---

## 1. Problem statement

The 4a smoke surfaced three real issues. Each has a precise root cause:

### FU-2 — Source-tag convention drift between Analyst context and Critic dossier

The Analyst's input (built by `ui/panels.py:298-340` via `build_context_block`) emits dotted-path tags:

```
- last_price: 1413.20 [src: quote.last_price]
- pe_ttm: 43.60 [src: fundamentals.pe_ttm]
- ... [src: news[0]]
```

The Critic's input (built by `agents/_dossier.py:24-78` via `build_source_dossier`) emits short-code tags:

```
[QUOTE]      RELIANCE.NS  1413.20  +2.31%  ...
[FUND-PE]    43.60   (TTM)
[NEWS-1]     "..."
```

Two side-effects:
1. **Critic cannot verify** any analyst tag — they're in different schemas. Every analyst citation looks "unsourced" to the Critic, which (correctly) flags this as high severity. This drowns out the legitimate critiques.
2. **Analyst hallucinates tags** like `[src: quote.market_cap]` when `market_cap` was `None` in the context (the field name appears in `format_quote_for_context` even when the value is `None`, so the analyst sees a valid-looking tag with a `—` value and cites it). The dossier then has no `[FUND-MC]` or equivalent — confirmed unverifiable.

### Q-1 — Critic severity rubric is undefined

`prompts/critic.md` line 17 says `<each issue, severity: high|medium|low>` but never defines what each level means. Result: the LLM defaults to "high" for everything, including stylistic critiques. User feedback called this "overly harsh" and "high severity used dramatically."

### Q-2 — Analyst lacks conglomerate-awareness

The 4a smoke on RELIANCE produced consolidated-PE / consolidated-ROE judgments without flagging that Reliance is multi-segment (Jio / Retail / O2C / Oil&Gas) and consolidated metrics obscure segment-level reality. User feedback flagged this as a missed nuance. No prompt rule exists today to force the analyst to handle this case.

---

## 2. Goals

1. **Single tag convention.** The Analyst's context block, the Critic's dossier, and the Analyst's own output all use the same `[src: ...]` tag scheme. The Critic's verification logic ("does every claim map to a tag?") becomes mechanically checkable.
2. **Defined severity rubric.** Critic's `high/medium/low` becomes a function of objective criteria, not vibes.
3. **Conglomerate rule.** Analyst declines to draw consolidated valuation conclusions when segment-level data is missing for multi-segment targets.
4. **Regression tests.** All three changes have automated tests so they don't silently regress.

## Non-goals

- Data agent enrichment (cash flow, segmentals, peer multiples) — that's Q-4, separate ADR, separate sprint.
- Re-tuning Analyst's factor hierarchy or conviction tiers — those are working as designed.
- Touching the Analyst's non-regression baseline test path (`test_run_analyze_non_regression_analyst_fields_match_baseline`). That test pins *parsed fields*, not raw text — so tag-format changes won't break it. We verify this assumption before making prompt changes.

---

## 3. Decision: which tag convention wins

Two candidate conventions:
- **A (current Analyst):** dotted-path — `[src: quote.last_price]`, `[src: fundamentals.pe_ttm]`, `[src: news[0]]`
- **B (current Critic dossier):** short-code — `[src: QUOTE]`, `[src: FUND-PE]`, `[src: NEWS-1]`

**Choice: A (dotted-path) wins.**

Rationale:
- Self-documenting (`fundamentals.pe_ttm` says exactly which field).
- Already consumed correctly by the Analyst — the bug is in the *dossier* having lied about its own format, not in the analyst.
- Matches the actual data shape (the dicts have keys like `pe_ttm`, `last_price`).
- The non-regression baseline (`tests/agents/fixtures/analyst_baseline_RELIANCE.json`) was captured under convention A. Switching to B would force a baseline rebuild and lose our 4a safety net.

Migration: rewrite `_dossier.py` to emit dotted-path tags instead of short-codes. The Analyst doesn't change the citation style it produces; only the Critic's reference card changes to match.

---

## 4. Concrete changes

### 4.1 `src/finterminal/agents/_dossier.py` — switch to dotted-path tags

Current `_render_quote` returns a one-line `[QUOTE] ...` summary. New version:

```
SOURCES AVAILABLE TO THE ANALYST (RELIANCE.NS):

# Quote (from quote.* tags)
- last_price: 1413.20 [src: quote.last_price]
- change_pct: +2.31% [src: quote.change_pct]
- volume: 80,90,000 [src: quote.volume]
- market_cap: — [src: quote.market_cap]   # value unavailable but tag valid
- as_of: 2026-04-29T10:19:54+00:00 [src: quote.as_of]

# Fundamentals (from fundamentals.* tags; missing fields explicit)
- pe_ttm: 43.60 [src: fundamentals.pe_ttm]
- eps_ttm: 32.40 [src: fundamentals.eps_ttm]
- roe: 0.079 [src: fundamentals.roe]
- roce: 0.079 [src: fundamentals.roce]
- debt_to_equity: 0.41 [src: fundamentals.debt_to_equity]
- revenue_ttm: 5,05,649.00 [src: fundamentals.revenue_ttm]
- net_income_ttm: 43,851.00 [src: fundamentals.net_income_ttm]

# News (from news[i] tags, 0-indexed)
- "Government proposes higher ethanol blending..." (Mint, 2026-04-28) [src: news[0]]
- "Reliance Jio adds 4.2M subscribers..." (Moneycontrol, 2026-04-27) [src: news[1]]

VERIFY: every numeric or qualitative claim in the analyst's output must
map to one of the [src: ...] tags above. Flag any that do not. A tag whose
value is "—" is still a valid tag — the analyst may cite it to acknowledge
"data unavailable", but must not fabricate the value.
```

Token cost: roughly the same as today (~25-40 lines for typical RELIANCE input).

Implementation notes:
- The dossier becomes a **direct subset of `build_context_block`'s tag schema** — same names, same conventions, just compacted (drop full news bodies, keep headlines).
- Keep `[src: news[i]]` 0-indexed to match `format_news_for_context` at `panels.py:337`.
- Surface `volume` and `market_cap` (today the dossier hides them even when the analyst's context has them as null — that's part of why the analyst hallucinates values).

### 4.2 `src/finterminal/prompts/analyst.md` — make tag rules explicit

Add a new `# Source tags (HARD CONSTRAINT)` section after the existing `# Operating principles`. Body:

```
You will be given a SOURCES block in your input. Every numeric or
qualitative claim in your output that derives from data MUST be tagged
with [src: <exact tag from the SOURCES block>]. The valid tags are
exactly these — never invent new ones:

  Quote:        quote.last_price | quote.change_pct | quote.volume
                quote.market_cap | quote.as_of
  Fundamentals: fundamentals.pe_ttm | fundamentals.eps_ttm
                fundamentals.roe | fundamentals.roce
                fundamentals.debt_to_equity | fundamentals.revenue_ttm
                fundamentals.net_income_ttm
  News:         news[0], news[1], ... news[N-1]   (0-indexed)

If a claim cannot be tied to one of these tags, do not make the claim —
write "data unavailable" instead. NEVER invent a tag like
[src: quote.something_not_listed] or [src: fundamentals.cash_flow]; the
critic checks every tag against the SOURCES block and unverifiable tags
are treated as fabrication.
```

Update existing principle #1 (line 5) to point at this section.

### 4.3 `src/finterminal/prompts/analyst.md` — add conglomerate rule (Q-2)

Add a new operating principle (becomes principle #8):

```
8. **Conglomerate guard.** If the company operates ≥3 distinct revenue
   segments (typical: diversified banks, oil/gas integrated majors,
   tech conglomerates like Reliance with Jio + Retail + O2C, holding
   companies, large industrial groups) AND segment-level P&L is NOT
   present in the SOURCES block, you MUST:

   (a) State explicitly in `Assumptions` that consolidated PE/ROE/ROCE
       obscure segment-level economics
   (b) Cap your `Confidence` at 0.55 regardless of factor alignment
   (c) Add to `What Would Change My Mind`: "segmental P&L disclosure
       showing [the segments] would let me size this properly"

   The Phase-2 SOURCES block does not include segmentals. So for any
   target you recognize as a multi-segment conglomerate (Reliance, ITC,
   L&T, Adani Enterprises, Bajaj Finserv holding co, etc.), this rule
   applies by default.
```

### 4.4 `src/finterminal/prompts/critic.md` — explicit severity rubric (Q-1)

Replace the bare `severity: high|medium|low` line with a rubric. New section:

```
# Severity rubric (use these exact criteria, no others)

`high` — Either of:
  - The claim cites a [src: ...] tag that is NOT in the SOURCES block
    (fabricated tag), OR
  - The claim contradicts a value in the SOURCES block.

`medium` — Both of:
  - The claim is unsourced (no [src: ...] tag), AND
  - The claim is material to the bull/bear conclusion (would flip a
    factor's sign, change conviction tier, or move confidence by ≥0.1
    if removed).

`low` — Either of:
  - Unsourced but stylistic / throwaway (e.g., "moderate leverage",
    "manageable risk" — qualitative framing without a numeric anchor).
  - Vague but not load-bearing.

If you find yourself wanting to flag everything as `high`, you are
mis-calibrated — re-read the criteria. A typical /analyze output should
have ≤2 `high`-severity issues, ≤4 `medium`, with the rest `low`.
```

Update output format to require: `- [SEVERITY] <issue> [src: ...|no source]` so each issue line is parseable.

### 4.5 Critic prompt — soften tone

Replace the opening line:

> You are an adversarial reviewer of equity research.

with:

> You are a senior peer-reviewer of equity research. Your job is constructive
> rigor: identify what's wrong, missing, or weak, but in the same tone a
> respected colleague would use in a Monday morning meeting — direct,
> specific, actionable, never theatrical.

This nudges away from the "boilerplate", "not falsifiable" word-choice the user flagged.

---

## 5. Tests

### 5.1 New: `tests/agents/test_tag_discipline.py`

Property-style test, no LLM calls:

```python
def test_dossier_tags_are_subset_of_context_block_tags():
    """Every [src: ...] tag emitted by the dossier must also exist in
    build_context_block, so the Critic can verify analyst citations."""
    quote = {...sample with all fields...}
    fund = {...sample...}
    news = [{...}, {...}]

    context_tags = extract_src_tags(build_context_block(...))
    dossier_tags = extract_src_tags(build_source_dossier(...))

    assert dossier_tags <= context_tags  # subset

def test_dossier_emits_dotted_path_tags():
    """Convention check: tags are quote.X, fundamentals.X, news[i] — never
    short-codes like QUOTE / FUND-PE / NEWS-1."""
    output = build_source_dossier(...)
    assert "[src: quote.last_price]" in output
    assert "[src: fundamentals.pe_ttm]" in output
    assert "[src: news[0]]" in output
    # Negative: short-codes must NOT appear
    assert "[QUOTE]" not in output
    assert "[FUND-PE]" not in output
    assert "[NEWS-1]" not in output

def test_dossier_surfaces_unavailable_fields_with_dash():
    """volume and market_cap are often missing from quotes; dossier must
    still list the tag so the analyst can cite 'data unavailable'."""
    quote = {"ticker": "X", "last_price": 100, "as_of": ..., "provider": "p"}
    # volume + market_cap absent
    out = build_source_dossier("X", quote, None, [])
    assert "[src: quote.volume]" in out
    assert "[src: quote.market_cap]" in out
    # ... values shown as "—"
```

**Helper to extract:** a small `_extract_src_tags(text: str) -> set[str]` regex on `\[src:\s*([^\]]+)\]`.

### 5.2 New: `tests/agents/test_critic_severity_rubric.py`

LLM-mocked test using a fixture analyst output with known issues:

```python
def test_critic_uses_high_only_for_fabricated_or_contradictory():
    """Given a fixture analyst output that has (a) one fabricated tag,
    (b) one unsourced material claim, (c) one stylistic flourish, the
    critic should produce roughly: 1 high, 1 medium, 1 low — not 3 highs."""
    # Use a recorded provider response where the critic followed the rubric.
    # The point of this test is to lock the prompt's rubric in the system
    # message, not to test the model's compliance — that's smoke territory.
    crit = CriticAgent(get_provider=lambda: _MockProvider(_RUBRIC_FIXTURE))
    result = asyncio.run(crit.run(ctx))
    parsed = result.payload
    severities = [i["severity"] for i in parsed["issues"]]
    assert severities.count("high") <= 1
    assert "medium" in severities
    assert "low" in severities
```

### 5.3 New: `tests/agents/test_analyst_conglomerate_guard.py`

Fixture-based test that verifies the prompt change is wired (system message contains the guard text):

```python
def test_analyst_system_prompt_contains_conglomerate_guard():
    """Sanity check: the prompt file actually has the new principle.
    Catches accidental deletion / refactor regressions."""
    from finterminal.agents.analyst import _ANALYST_SYSTEM_PROMPT
    assert "Conglomerate guard" in _ANALYST_SYSTEM_PROMPT
    assert "≥3 distinct revenue segments" in _ANALYST_SYSTEM_PROMPT
    assert "Cap your `Confidence` at 0.55" in _ANALYST_SYSTEM_PROMPT
```

### 5.4 Update: `tests/agents/test_dossier.py`

Existing tests in `test_dossier.py` assert `"[QUOTE]"` is in the output. Those will fail under the new convention. Update to assert the dotted-path equivalents. Don't delete tests — change the assertion strings only.

Existing tests to update:
- `test_dossier_includes_quote_tag` → assert `[src: quote.last_price]`
- `test_dossier_includes_fundamental_tags` → assert `[src: fundamentals.pe_ttm]`, etc.
- `test_dossier_news_uses_indexed_tags` → assert `[src: news[0]]`, `[src: news[1]]`
- `test_dossier_handles_missing_fundamentals` → still works (assert `fundamentals unavailable`)
- `test_dossier_handles_no_news` → still works (assert `no news returned`)
- `test_dossier_ends_with_verify_directive` → still works (asserts `VERIFY`)

### 5.5 Smoke verification (manual, end-of-day-1)

Run `/analyze RELIANCE` once. Confirm:
- Analyst's `[src: ...]` tags use dotted-path style
- Critic's issue list does NOT have a "tags don't match" complaint
- ≤2 high-severity issues (rubric calibrated)
- `Assumptions` section mentions segmental P&L gap (conglomerate guard)
- `Confidence` ≤ 0.55

If any of those fail, halt — don't ship until calibrated.

---

## 6. Rollout (commit plan)

One commit per logical change, TDD order (failing test → green test):

1. `test: add tag-discipline regression tests (failing pre-fix)` — adds `test_tag_discipline.py`. Runs red.
2. `fix(dossier): align tags with context block convention (dotted-path)` — rewrites `_dossier.py`. Updates existing `test_dossier.py` assertions. Tag-discipline tests pass.
3. `prompt(analyst): explicit src-tag whitelist + conglomerate guard` — rewrites `analyst.md`. Adds `test_analyst_conglomerate_guard.py`.
4. `prompt(critic): defined severity rubric + softer collegial tone` — rewrites `critic.md`. Adds `test_critic_severity_rubric.py`.
5. `chore: smoke-verify FU-2/Q-1/Q-2 on RELIANCE` — vault-only; no code. Captures the manual smoke result in the build log.

---

## 7. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Non-regression baseline test breaks because Analyst output text changed | Medium | The baseline pins *parsed fields* (`bull_case`, `bear_case` etc.), not raw text. Verify before §4.2. If it breaks, it's a real regression worth investigating, not a baseline-update issue. |
| `test_dossier.py` updates miss an assertion → silently green test for wrong reason | Low | Run targeted `pytest tests/agents/test_dossier.py -v` after change; visually confirm 6 tests still pass. |
| New severity rubric is too strict and the smoke critic finds nothing → Critic value = 0 | Medium | The rubric explicitly says "≤2 high, ≤4 medium" — that's a ceiling, not a floor. The critic should still surface real issues; we only constrain over-flagging. |
| Conglomerate rule fires on non-conglomerate names → over-cautious analyst | Low | Rule is gated on "≥3 distinct revenue segments" + "segmental P&L NOT present." Single-segment names (TCS, Asian Paints) won't trip it. |
| Token bloat in `_dossier.py` (volume + market_cap rows added) | Low | +2 lines per quote, ~+10 tokens. Negligible. |

---

## 8. Open questions

- **Should the Critic also be told the severity-rubric numbers ("≤2 high, ≤4 medium")?** Risk of the LLM hard-rationing to hit a quota even when more issues exist. *Decision: yes, frame as "should be" not "must be." Calibration nudge, not a hard limit.*
- **Conglomerate detection — by name or by data?** The plan uses by-name (Reliance/ITC/L&T...). Detecting from data alone needs segmental P&L which we don't have. *Decision: name-based for Phase-2 scope; revisit when Phase 2.5.A transcripts pipeline brings in segmental disclosures.*
- **Critic system prompt cache impact?** The rewrite roughly doubles the critic prompt length. With `cache_system=True` (Anthropic) or no-op (others), cost impact is one-time per session. *Acceptable.*

---

## 9. Done criteria

- [ ] All five commits land green
- [ ] `uv run pytest -q` shows all tests passing (target: 81+ tests, was 77)
- [ ] `uv run ruff check src tests` clean
- [ ] Manual smoke `/analyze RELIANCE` produces tags in dotted-path style, severity-calibrated critic, conglomerate-aware Analyst output
- [ ] Vault build log entry committed for the day
