# ADR-009 — Phase 1: Synchronous REPL with asyncio.run for LLM Calls

> Back to [[Index]] | See also [[04 - Code Map/commands]] · [[04 - Code Map/agents — supervisor]] · [[02 - Decisions/ADR-006 Model Abstraction in Phase 1]]

**Status:** Accepted
**Date:** 2026-04-28
**Deciders:** Ajinkya Wagh

---

## Context

`terminal.py` runs a `while True` input loop — inherently synchronous. The five REPL commands (`/help`, `/ticker`, `/news`, `/watch`, `/analyze`) are all sync. However, `agents/supervisor.py::analyze_ticker` is `async` because the LLM provider protocol (`llm.complete`) is defined as a coroutine (anticipating Phase 2 parallel agent calls).

This creates a bridge problem: sync caller → async callee.

---

## Decision

Keep `commands.py` entirely **synchronous**. The one async path (`_cmd_analyze` → `analyze_ticker`) is bridged with a single `asyncio.run()` call per invocation.

```python
# commands.py:159
result = asyncio.run(analyze_ticker(ticker, conn))
```

---

## Rationale

| Factor | Reasoning |
|---|---|
| REPL loop simplicity | A sync loop has a trivial error boundary: one `try/except` in `dispatch`. Mixing `asyncio.run` into the top-level loop introduces event-loop lifecycle complexity for no Phase-1 benefit. |
| Single async path | Phase 1 has exactly one LLM-using command (`/analyze`). The overhead of `asyncio.run()` per call (≈ event-loop spin-up) is negligible vs. LLM network latency (1–10 s). |
| Error isolation | `asyncio.run` fully completes (or raises) before `dispatch` returns control to the loop. Unhandled async exceptions surface as normal Python exceptions — the existing `try/except Exception` in `dispatch` catches them. |
| Clear upgrade path | When Phase 2 adds parallel agents (Supervisor + Critic concurrently), `_cmd_analyze` can be expanded inside the same `asyncio.run()` block without touching the outer REPL loop. When Phase 3 migrates to LangGraph, the entire `asyncio.run` wrapper can be replaced by the LangGraph runner. |

---

## Trade-offs

| Pro | Con |
|---|---|
| Simple REPL loop; easy to reason about | `asyncio.run()` creates a new event loop per `/analyze` call — cannot reuse a persistent loop |
| Standard Python; no framework dependency | If a future command needs streaming (token-by-token output), `asyncio.run` would need refactoring |
| One error boundary for all commands | Concurrent `/analyze` calls (not relevant in REPL, but conceptually) would block each other |

---

## Alternatives considered

| Option | Why rejected |
|---|---|
| Make the REPL loop `async` (run under `asyncio.run` at top level) | Adds complexity for no Phase-1 benefit; Textual in Phase 2 has its own async event loop |
| Use `concurrent.futures.ThreadPoolExecutor` to run async in a thread | Needlessly complex; thread-safety of DuckDB connections would need auditing |
| Synchronous LLM provider (blocking HTTP) | Forfeits `async def complete` — would require protocol change that breaks Phase 2 parallelism design |

---

## Revisit trigger

When Phase 2 introduces parallel agent calls (Supervisor + Critic in `asyncio.gather`), or when Phase 3 migrates to LangGraph with its own async runner. At that point, consider running the REPL itself under a persistent event loop.

---

## Affected files

- `src/finterminal/commands.py` — `_cmd_analyze` line :148–163
- `src/finterminal/agents/supervisor.py` — `analyze_ticker` is `async def`
- `src/finterminal/terminal.py` — sync REPL loop
