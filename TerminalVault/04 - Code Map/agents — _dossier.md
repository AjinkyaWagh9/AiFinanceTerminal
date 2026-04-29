# Code Map — agents/_dossier.py

> Back to [[Index]] | See also [[agents — analyze_flow]] · [[04 - Code Map/prompts]] · [[02 - Decisions/ADR-014 Single Tag Convention dotted-path]]

**File:** `src/finterminal/agents/_dossier.py`
**Shipped:** 2026-04-29, commit `e17bfa6` (rewrite of tag emission; file predates this commit as part of 4a scaffold)
**Driver:** FU-2 — Analyst↔dossier source-tag convention drift. See [[05 - Build Log/2026-04-29 — C Sprint (FU-2 Q-1 Q-2 Smoke Green)]].

---

## Purpose

Builds the compact source dossier injected into the Analyst's user message. The dossier is the deterministic source-of-truth for everything the Analyst can cite. Every field it surfaces has a corresponding `[src: ...]` tag — the Analyst is only allowed to cite tags that appear in the dossier.

The Critic's `VERIFY` directive cross-references Analyst-cited tags against the dossier tags. If the tag vocabularies diverge, Critic can't verify — the root cause of FU-2.

---

## Tag convention (post-FU-2 fix)

All tags use **dotted-path format** matching `build_context_block()` in `ui/panels.py:298+`. Short-codes (`[QUOTE]`, `[FUND-PE]`, `[NEWS-1]`) were replaced entirely in commit `e17bfa6`.

| Tag emitted by `_dossier.py` | Data field | Notes |
|---|---|---|
| `[src: quote.last_price]` | Spot price | Required |
| `[src: quote.volume]` | Trading volume | May be null |
| `[src: quote.market_cap]` | Market capitalisation | Often null for Indian tickers via yfinance |
| `[src: fundamentals.pe_ttm]` | Trailing P/E | |
| `[src: fundamentals.pb]` | Price-to-book | |
| `[src: fundamentals.roe]` | Return on equity | |
| `[src: fundamentals.revenue_ttm]` | TTM revenue | |
| `[src: fundamentals.net_income_ttm]` | TTM net income | |
| `[src: fundamentals.debt_equity]` | Debt-to-equity | |
| `[src: news[0]]` … `[src: news[N]]` | RSS headline N | N = 0-indexed; count depends on feed |
| `[src: macro.*]` | Macro sub-fields | Passed through from Data agent |

The dossier emits a **faithful subset** of `build_context_block`'s full tag vocabulary — it does not extend it. Analyst prompt whitelist matches exactly these 12 categories.

---

## Key implementation notes

- `volume` and `market_cap` are surfaced even when null — Analyst can then cite "data unavailable" rather than fabricating or skipping the field. This was a deliberate design choice in the FU-2 fix.
- Tags are rendered inline in the dossier text alongside each field value, not as a separate tag table. Example: `Last price: ₹450.20 [src: quote.last_price]`.
- The dossier is injected as the user message to the Analyst; system message is `prompts/analyst.md`. Critic receives the raw analyst output plus the original dossier for cross-reference.

---

## Tests

| Test file | Count | What is pinned |
|---|---|---|
| `tests/agents/test_dossier.py` | 6 | Field presence, dotted-path tag format, null-field handling |
| `tests/agents/test_tag_discipline.py` | 5 | Contract: dossier tag vocabulary ∩ context-block tag vocabulary (no drift) |
| `tests/agents/test_data_agent.py:91-93` | 3 lines | Dotted-path assertion updated |

---

## Before vs after (FU-2 root cause)

| Aspect | Before (commit prior to `e17bfa6`) | After (`e17bfa6`) |
|---|---|---|
| Tag format | `[QUOTE]`, `[FUND-PE]`, `[NEWS-1]` short-codes | `[src: quote.last_price]` etc. dotted-path |
| Tag vocabulary | Diverged from `build_context_block` | Faithful subset of `build_context_block` |
| Critic verification | Tag-format mismatch — Critic flagged vocabulary noise | Tag vocabulary aligned — Critic issues substance-only |
| volume / market_cap | Absent | Surfaced (may be null) |

---

## Cross-links

- ADR: [[02 - Decisions/ADR-014 Single Tag Convention dotted-path]]
- Build log: [[05 - Build Log/2026-04-29 — C Sprint (FU-2 Q-1 Q-2 Smoke Green)]]
- Related: [[04 - Code Map/prompts]] (analyst.md whitelist mirrors this tag set)
- Related: [[04 - Code Map/ui — Rich-Textual]] (`build_context_block` in `ui/panels.py:298+` is the canonical tag vocabulary source)
- Related: [[04 - Code Map/agents — analyze_flow]] (orchestrator that wires dossier into Analyst call)
