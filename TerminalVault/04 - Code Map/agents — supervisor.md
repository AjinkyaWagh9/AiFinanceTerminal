# Code Map — agents/supervisor.py

> Back to [[Index]] | See also [[04 - Code Map/commands]] · [[04 - Code Map/ui — Rich-Textual]] · [[01 - Architecture/Agent System]]

**File:** `src/finterminal/agents/supervisor.py`
**Role:** Phase 1 LLM orchestration for `/analyze`. Fetches context, calls the supervisor LLM, parses the structured response, persists to DuckDB.

---

## Key functions

| Function | Line | Purpose |
|---|---|---|
| `parse_analysis(text)` | :41 | Splits 5-section analyst.md response into dict. Lenient (missing sections → empty string). |
| `analyze_ticker(ticker, conn)` | :78 | Async. Full flow: fetch → context block → LLM → parse → persist → return dict. |
| `_load_system_prompt()` | :37 | Reads `prompts/analyst.md` from disk on each call (no cache — acceptable in Phase 1). |

---

## `parse_analysis` detail

- **Regex:** matches `## <Section Name>` headers for all 5 sections (line :47–53)
- **Sections parsed:** Bull Case, Bear Case, Confidence, Assumptions, What Would Change My Mind
- **Confidence extraction:** first float in the Confidence section; clamped `max(0.0, min(1.0, v))` (line :63–65)
- **Missing sections:** become `""` (bull_case, bear_case, assumptions, what_would_change) or `None` (confidence)
- **Tests:** `test_analysis_parser_extracts_all_sections`, `test_analysis_parser_handles_missing_sections`, `test_analysis_parser_clamps_confidence` in `tests/test_smoke.py`

---

## `analyze_ticker` flow

```
1. fetch_quote(ticker)           → quote dict, upsert to DuckDB
2. fetch_fundamentals(ticker)    → fundamentals dict, upsert (best-effort; warns on fail)
3. fetch_news(ticker, limit=10)  → news list, upsert if non-empty (best-effort; warns on fail)
4. build_context_block(...)      → markdown with [src: ...] tags on every numeric
5. router.for_agent("supervisor") → LLM provider (Claude Sonnet 4.6 per agents.yaml)
6. llm.complete(system, messages, max_tokens=2000, temperature=0.3)
7. budget.record("supervisor", completion)   → logs cost to DuckDB llm_calls
8. parse_analysis(completion.text)
9. duckdb_store.record_analysis(conn, ...)  → returns analysis_id
10. return parsed dict + ticker + analysis_id
```

---

## Source discipline enforcement

- `build_context_block` (in `panels.py`) emits `[src: quote.*]`, `[src: fundamentals.*]`, `[src: news[i]]` tags for every numeric field.
- User message appended: `"Every numeric claim must trace to a [src: ...] tag from the context above."` (supervisor.py:108–110)
- Prompt file: `src/finterminal/prompts/analyst.md`

---

## Design notes

- **Phase 1 = single agent, no Critic.** Phase 2 adds Critic agent as a second pass.
- **No response caching in Phase 1.** Each `/analyze` call hits the LLM fresh.
- **LLM model indirection:** never calls Claude directly; always goes through `router.for_agent("supervisor")`. See [[01 - Architecture/LLM Abstraction Layer]].
- **asyncio bridge:** `analyze_ticker` is `async`; called from sync `commands._cmd_analyze` via `asyncio.run()`. See [[02 - Decisions/ADR-009 Synchronous REPL with asyncio.run]].

---

## Dependencies

- `finterminal.data.duckdb_store` — upserts + `record_analysis`
- `finterminal.data.openbb_client` — quote / fundamentals / news
- `finterminal.llm.build_router` — LLM abstraction layer
- `finterminal.llm.budget.record` — cost tracking
- `finterminal.ui.panels.build_context_block` — context formatting
