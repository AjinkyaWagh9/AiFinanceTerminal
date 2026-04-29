# Code Map — ui/panels.py

> Back to [[Index]] | See also [[04 - Code Map/commands]] · [[04 - Code Map/agents — supervisor]] · [[03 - Phases/Phase 2 - Multi-Agent Foundation]]

**File:** `src/finterminal/ui/panels.py`
**Role:** All Rich panel and table renderers for the REPL, plus context-block formatters that emit `[src: ...]` tags for the LLM.

---

## `_escape_markup` helper (Q-6, commit `0b5e723`)

| Detail | Value |
|---|---|
| Function | `_escape_markup(s: str \| None) -> str` |
| File:line | `panels.py:13` |
| What it does | Escapes `[` → `\[` in LLM-generated strings so Rich renders bracketed text literally instead of interpreting it as style markup |
| Why needed | Rich's `Panel(string)` silently strips unknown `[style]` tokens. The Analyst emits `[src: quote.last_price]` citations; without escaping these vanished from the rendered panel (Q-6 root cause) |
| Applied to | `variant_perception` (:221), `bull_case` (:229), `bear_case` (:236), `assumptions` (:265), `what_would_change` (:266) |
| NOT applied to | Critic block — `Text.append()` already treats input as plain text |
| Live-verified | 2026-04-29 `/analyze ITC` — every `[src: ...]` tag renders literally in the panel |

---

## Panel / table renderers

| Function | Line | Output type | Used by |
|---|---|---|---|
| `banner()` | :13 | `Panel` | `terminal.py` on startup |
| `help_panel()` | :21 | `Panel` | `_cmd_help` |
| `error_panel(message, title)` | :37 | `Panel` | `dispatch` error boundary |
| `info_panel(message, title)` | :41 | `Panel` | `/watch add`, `/watch remove` |
| `ticker_panel(quote, fundamentals)` | :79 | `Panel` | `_cmd_ticker` |
| `news_table(items, ticker)` | :120 | `Table` | `_cmd_news` (empty case: single "—" row) |
| `watchlist_table(rows)` | :143 | `Table` | `_cmd_watch list` |
| `analysis_panel(analysis)` | :177 | `Panel` | `_cmd_analyze` |

---

## Context-block helpers (for LLM)

| Function | Line | Emits |
|---|---|---|
| `build_context_block(ticker, quote, fundamentals, news)` | :276 | Full markdown context with all `[src:]` tags |
| `format_quote_for_context(quote)` | :232 | `## Quote` section; tags: `[src: quote.last_price]`, etc. |
| `format_fundamentals_for_context(f)` | :243 | `## Fundamentals` section; tags: `[src: fundamentals.pe_ttm]`, etc. |
| `format_news_for_context(items)` | :258 | `## Recent News` section; tags: `[src: news[i]]` per headline |

All numeric fields in the context block carry a `[src: ...]` tag — enforced by `test_context_block_tags_every_numeric`.

---

## `analysis_panel` layout

```
┌── /analyze TICKER ──────────────────────────────────────┐
│ ┌── bull (green) ────┐  ┌── bear (red) ───────────────┐ │
│ │  LLM bull_case text │  │  LLM bear_case text         │ │
│ └────────────────────┘  └────────────────────────────── ┘ │
│ confidence  ████████████░░░░░░░░  0.55                    │
│ ┌── assumptions ─────┐  ┌── what would change my mind ─┐  │
│ │  ...                │  │  ...                         │  │
│ └────────────────────┘  └─────────────────────────────── ┘ │
└─────────────────────────────────────────────────────────── ┘
```

Confidence gauge (`_confidence_gauge`, line :161): 20-cell bar.
- ≥ 0.7 → green
- 0.4–0.69 → yellow
- < 0.4 → red

---

## `ticker_panel` formatting helpers

| Helper | Purpose |
|---|---|
| `_fmt_money(v, suffix)` | Formats large numbers as `cr` / `L` (Indian convention) |
| `_fmt_num(v, decimals)` | Comma-formatted float; `—` for None |
| `_fmt_pct(v)` | `+1.23%` with sign |
| `_color_change(change_pct)` | Returns Rich color name based on magnitude / direction |

---

## Phase notes

- **Phase 1:** Rich `Panel` / `Table` / `Columns` for REPL output.
- **Phase 2+:** Textual full TUI with tabs (Dashboard, Ticker, News, Watchlist). The panel functions will map to Textual widgets.
