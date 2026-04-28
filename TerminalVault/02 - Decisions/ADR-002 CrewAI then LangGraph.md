# ADR-002 — CrewAI for MVP, Then LangGraph

> Back to [[Index]] | See also [[01 - Architecture/Agent System]] · [[03 - Phases/Phase 3 - US + Routing]]

**Status:** Accepted
**Date:** 2026-04-27
**Source:** [PLAN.md §4.1 Decision Matrix](../docs/PLAN.md)

---

## Context

Phases 2+ require orchestrating multiple agents (Supervisor, Data, News, Critic, Bull-Bear). The orchestration framework must support multi-LLM routing, self-critique cycles, and eventual human-in-loop checkpoints. Two mature options: **CrewAI** and **LangGraph**.

---

## Decision

**CrewAI for Phases 1–2.5** (speed-to-MVP, role mapping) → **migrate hot paths to LangGraph in Phase 3** (cyclical critique, conditional re-fetch, probabilistic scenarios).

---

## Decision matrix (from PLAN.md §4.1)

| Aspect | Weight | LangGraph | CrewAI | AutoGen | Custom |
|---|---:|---:|---:|---:|---:|
| Control / state machines | 5 | 5 | 3 | 3 | 4 |
| Speed to MVP | 4 | 2 | **5** | 4 | 3 |
| Multi-LLM routing | 4 | 5 | 4 | 4 | 5 |
| Self-critique cycles | 4 | 5 | 3 | 4 | 4 |
| Observability | 3 | 5 | 3 | 3 | 1 |
| Ecosystem / docs | 3 | 5 | 4 | 3 | 1 |
| **Weighted score** | | **107** | **86** | **87** | **78** |

CrewAI wins on speed-to-MVP in the short term; LangGraph wins overall for a mature system.

---

## Rationale

- CrewAI's role-mapping (Agent, Task, Crew) maps 1:1 to the project's agent vocabulary.
- Migration is incremental: both compose with LangChain; `/analyze` hot path can move to LangGraph without rewriting other commands.
- LangGraph's graph state model becomes important specifically when the Critic needs to re-route back to Data Agent on a gap (conditional re-fetch). That complexity doesn't exist in Phase 2.

---

## Migration trigger (PLAN.md §1.2 in BACKLOG.md)

When ≥30% of `/analyze` runs need a re-fetch round, or when human-in-loop checkpoints are required.

---

## Consequences

- Phase 2 introduces CrewAI; registers agents 1–5.
- Phase 3 rewrites `/analyze` in LangGraph; other commands stay on CrewAI until individually migrated.
- Agent interface (via `router.for_agent`) is unchanged by the migration — agents don't know which framework they're running in.
