# Phase 1 — Core Terminal + Indian Equities MVP

> Back to [[Index]] | See also [[05 - Build Log/2026-04-28 - Phase 1 REPL Wiring Complete]] · [[05 - Build Log/2026-04-28 - Days 3-5 Pushed to GitHub]] · [[05 - Build Log/2026-04-28 - Indian News Gap]]

**Status:** Functionally complete (news gap pending Phase 2)
**Target weeks:** 1–2
**Source:** [PLAN.md §6 Phase 1](../docs/PLAN.md) | [Phase-1-Kickoff.md](../docs/Phase-1-Kickoff.md)

---

## Scope

- Repo scaffolding: `pyproject.toml`, ruff/black, pre-commit.
- `terminal.py` command parser + Rich layout.
- OpenBB integration: quotes, fundamentals, news for NSE/BSE.
- DuckDB schema: `quotes`, `fundamentals`, `news`, `watchlist`, `analyses`, `llm_calls`.
- LLM abstraction layer (PLAN.md §3.1) — built in Phase 1 to avoid 13-agent refactor later.
- `/analyze TICKER` end-to-end: context block → Claude Sonnet 4.6 → structured bull/bear → Rich panel.
- Source-discipline guardrails: `[src: ...]` tags on every numeric field.

---

## Commands shipped

| Command | Description |
|---|---|
| `/help` | List available commands |
| `/ticker <SYMBOL>` | Quote + fundamentals Rich panel |
| `/news <SYMBOL>` | Fetch + render news table |
| `/watch add/list/remove` | Watchlist management |
| `/analyze <SYMBOL>` | Full bull/bear with source-cited confidence |
| `/quit`, `/exit` | Exit REPL |

---

## Exit criteria

Tested on a 5-name watchlist (RELIANCE, HDFCBANK, INFY, TCS, ITC):

1. `/ticker TICKER` returns panel within 2s (warm) / 5s (cold).
2. `/news TICKER` returns ≥10 headlines from ≥2 distinct sources.
3. `/analyze TICKER` returns structured bull/bear with sourced numbers, confidence, assumptions in < 30s.
4. Used in lieu of MoneyControl for morning check-in for **2 consecutive trading days**.

---

## Key technical facts

- yfinance Indian quote endpoint is flaky → `fetch_quote` falls back to historical bars. Validated: RELIANCE.NS returned `last_price=1385.10`.
- `gpt-5-mini` 403'd on the test OpenAI project (model-tier issue, not a code bug). Supervisor stays on Claude Sonnet 4.6 until ANTHROPIC_API_KEY is set.
- DuckDB column gotcha: `asof` → renamed `as_of` (reserved keyword). See [[ADR-003 DuckDB + SQLite + ChromaDB local-only]].
- 12 smoke tests pass (was 6 before Days 3–5 push).

---

## Open gap (pre-Phase 2)

**Indian news gap:** yfinance/OpenBB news for NSE tickers is thin. `/news` may return < 10 results for smaller-cap Indian names. RSS aggregation (Mint, MoneyControl, ET Markets) is the Phase 2 fix. See [[05 - Build Log/2026-04-28 - Indian News Gap]].

---

## Key commit

`cf79139` — Phase 1 Days 3-5: live OpenBB data, REPL commands, `/analyze` pipeline.
