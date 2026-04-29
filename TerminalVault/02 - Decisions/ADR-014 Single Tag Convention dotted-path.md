# ADR-014 — Single tag convention across context block + dossier (dotted-path wins)

> Adopt `[src: dotted.path]` as the one and only source-tag vocabulary used by both the dossier builder and the context block renderer. Short-codes (`[QUOTE]`, `[FUND-PE]`, `[NEWS-1]`) are retired.

**Status:** Accepted
**Date:** 2026-04-29
**Source:** Spec `docs/superpowers/specs/2026-04-29-prompt-rewrite-fu2-q1-q2.md` §3 decision · Follow-up FU-2 from [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]
**Drivers:** FU-2 — Critic's `VERIFY` directive could not cross-reference Analyst-cited tags against dossier tags because the two builders were using different tag vocabularies. This made every Analyst citation unverifiable by the Critic, producing tag-format noise instead of substance-based critique.

---

## Context

At the time the 4a scaffold shipped (2026-04-28), two independent builders emitted source tags:

| Builder | Tag style | Example |
|---|---|---|
| `agents/_dossier.py` | Short-codes | `[QUOTE]`, `[FUND-PE]`, `[NEWS-1]` |
| `ui/panels.py:298+` `build_context_block()` | Dotted-path | `[src: quote.last_price]`, `[src: fundamentals.pe_ttm]`, `[src: news[0]]` |

The Analyst prompt told the Analyst to use `[src: ...]` dotted-path citations. The Analyst correctly cited dotted-path tags. But the dossier it received had short-codes. The Critic's `VERIFY` directive matched Analyst-cited dotted-paths against dossier short-codes — they never matched. Result: every Analyst citation appeared unverifiable, and the Critic produced tag-vocabulary noise (FU-2 surfaced in the 4a smoke run on 2026-04-29).

---

## Decision

- **Dotted-path wins.** `[src: <object>.<field>]` format is the single canonical tag vocabulary for all builders.
- `agents/_dossier.py` is rewritten to emit dotted-path tags as a faithful subset of `build_context_block()`'s full vocabulary (commit `e17bfa6`).
- `prompts/analyst.md` enumerates a 12-tag explicit whitelist using the same dotted-path names (commit `3244943`). Analyst is forbidden from inventing tags outside the whitelist.
- Short-codes (`[QUOTE]`, `[FUND-PE]`, `[NEWS-1]`) are fully retired — removed from dossier, removed from prompt examples.

---

## Why dotted-path over short-codes

| Criterion | Dotted-path `[src: fundamentals.pe_ttm]` | Short-codes `[FUND-PE]` |
|---|---|---|
| Self-documenting | Yes — object and field name are readable in the tag | No — requires a separate lookup table |
| Matches data shape | Yes — mirrors the dict key path used in the actual data payload | No — arbitrary abbreviation |
| Non-regression baseline | Preserves the 4a smoke baseline: Analyst already emitting dotted-path correctly | Would require retraining Analyst prompt and existing test expectations |
| Extensibility | New fields added as `[src: object.new_field]` — no registry update | New short-codes require maintaining an abbreviation registry |
| Critic verifiability | Tags are structurally comparable to context-block output | Mapping required; fragile to abbreviation drift |

---

## Consequences

### Positive
- Critic `VERIFY` can now reliably cross-reference Analyst citations against the dossier.
- Analyst can cite "data unavailable" for null fields (volume, market_cap) that are now surfaced in the dossier.
- One canonical tag vocabulary — no divergence possible between dossier and context block as long as dossier remains a subset of `build_context_block()`.
- All 16 new regression tests (5 tag-discipline + 5 analyst-prompt-rules + 6 critic-prompt-rules) pin the contract and will catch future vocabulary drift.

### Negative
- Anyone reading historical build logs or commit messages will see short-code references pre-`e17bfa6` — context note in this ADR serves as the bridge.
- The dossier is now a defined subset of the context block, not independent. If `build_context_block` adds a new field, the dossier must be manually updated to include it (or the test will catch the drift).

### What this does NOT change
- The context block renderer (`ui/panels.py:298+`) is unchanged — it was already using dotted-path.
- The Critic parser reads sections, not tag tokens — tag changes do not affect the parser.
- Phase boundaries, LangGraph migration plan, and Phase 2 scope are unaffected.

---

## Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Align dossier to short-codes; rewrite analyst prompt to use short-codes | Would break the 4a smoke non-regression baseline (Analyst already emitting dotted-path correctly in the wild); `build_context_block` would still differ |
| Maintain both vocabularies with a mapping table | Mapping tables drift; the Critic would need the mapping at inference time; adds latency + complexity for no user value |
| Let each builder own its own vocabulary and fix the Critic to do fuzzy matching | Transfers complexity to the Critic; fuzzy matching is error-prone and untestable |

---

## Cross-links

- Triggered by: FU-2 from [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]
- Implementation: commits `cc16a01` (regression tests), `e17bfa6` (dossier fix), `3244943` (analyst prompt)
- Build log: [[05 - Build Log/2026-04-29 — C Sprint (FU-2 Q-1 Q-2 Smoke Green)]]
- Code map: [[04 - Code Map/agents — _dossier]] · [[04 - Code Map/prompts]]
- Spec: `docs/superpowers/specs/2026-04-29-prompt-rewrite-fu2-q1-q2.md` §3
