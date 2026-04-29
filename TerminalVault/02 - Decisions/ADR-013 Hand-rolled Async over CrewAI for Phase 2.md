# ADR-013 — Hand-rolled Async Orchestration for Phase 2 (supersedes ADR-002 in part)

> Drop CrewAI from Phase 2's `/analyze` flow. Compose Data + Analyst + Critic with plain `asyncio` and the existing `router.for_agent()` interface. Phase 3 LangGraph migration plan is **unchanged**.

**Status:** Accepted
**Date:** 2026-04-28
**Source:** brainstorm 2026-04-28 + spec `docs/superpowers/specs/2026-04-28-multi-agent-scaffold-4a-design.md`

---

## Context

ADR-002 (2026-04-27) chose CrewAI for Phases 1–2.5 with LangGraph migration in Phase 3. Three of its inputs no longer hold:

| ADR-002 assumption | Current reality (2026-04-28) |
|---|---|
| 5 agents with LLM-driven delegation | 3 agents, deterministic per-command routing |
| Bull-Bear is a separate agent | analyst.md v2 absorbed it |
| Critic re-fetch loop in Phase 2 | Deferred to LangGraph (ADR-002's own migration trigger) |

The actual Phase 2 `/analyze` shape is a 3-step linear DAG: Data → Analyst → Critic. No conditional routing. No delegation. No cycles. CrewAI's value-props don't fire.

## Decision

For Phase 2 (and Phase 2.5 by extension), use:
- **Hand-rolled async orchestration** in `agents/analyze_flow.py` (and per-command flows in 4b+).
- A typed `Agent` Protocol + `AgentRegistry` (`agents/base.py`) so future agents drop in as one file each.
- The existing `router.for_agent()` interface for model selection — no abstraction change there.

**Phase 3 LangGraph migration of `/analyze` is unchanged** from ADR-002's plan. The trigger remains: ≥30% of `/analyze` runs need a re-fetch round, OR human-in-loop checkpoints required.

## Why CrewAI was the wrong tool *for this scope*

- "Agent backstory" abstraction adds noise for deterministic Python work (Data agent has no LLM).
- Adopting CrewAI for `/analyze` means "framework we add, then swap for LangGraph" — extra migration for no Phase 2 user value.
- Token-economy levers (compact source dossier, prompt caching, result cache) are easier to wire directly than through CrewAI's `Crew`/`Task` shape.

## Where CrewAI may still earn its keep

If 4b News & Trend's parallel feed-fetch + dedupe pipeline turns out to want CrewAI's parallel-task orchestration, it can be adopted there in isolation — `news_flow.py` is independent of `analyze_flow.py`. Decide at the start of 4b's spec.

## Consequences

**Positive**
- Smallest change that ships: ~150 LoC of orchestration, no new framework dependency.
- Token-economy levers (lever 1 source dossier, lever 2 prompt caching, lever 3 max_tokens cap, lever 4 result cache) wire directly through `LLMProvider.complete()` — no framework interception.
- Phase 2.5 transcript / ownership / quality / comps / macro agents are linear pipelines too — same scaffold scales without re-architecting.
- Phase 3 LangGraph migration scope is *smaller*, not larger: we replace a thin orchestrator instead of porting a CrewAI Crew.

**Negative**
- We diverge from ADR-002's documented framework choice mid-stream — ADR-013 is its supersession record for clarity.
- If Phase 2.5 grows graph-shaped flows earlier than expected, we either roll our own state machine or pull in LangGraph one phase early.

## Status update — 2026-04-29

- **Shipped 2026-04-29.** Smoke green: `/analyze RELIANCE` and `/analyze RELIANCE --fresh` rendered full 7-section panel + Critic block against live OpenAI (`gpt-5-mini`).
- **77/77 tests passing** (76 before smoke; +1 regression test for `registry=None` default path).
- Three post-smoke fixes committed: import path correction in `analyze_flow.py:138`, ruff unused-import cleanup, Critic model swapped to `gpt-5-mini` (Anthropic eager-init incompatibility).
- Follow-ups tracked: **FU-1** (cache-hit path not smoke-tested), **FU-2** (Analyst↔dossier source-tag convention drift). See [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]].

---

## Cross-links
- Supersedes: parts of [[ADR-002 CrewAI then LangGraph]] (Phase 2 framework only — Phase 3 plan stands)
- Implementation spec: `docs/superpowers/specs/2026-04-28-multi-agent-scaffold-4a-design.md`
- Implementation plan: `docs/superpowers/plans/2026-04-28-multi-agent-scaffold-4a.md`
- Brainstorm: 2026-04-28 (4a path through Phase 2 decomposition)
- Smoke log: [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]
