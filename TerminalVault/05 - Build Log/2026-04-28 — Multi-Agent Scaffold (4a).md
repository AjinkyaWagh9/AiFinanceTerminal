# 2026-04-28 — Multi-Agent Scaffold (Phase 2 / 4a)

**TL;DR:** `/analyze` is no longer a single LLM call. It's now Data → Analyst → Critic over a hand-rolled async orchestrator with prompt caching, a 5-min result cache, and a non-regression test that locks the Analyst output to a captured baseline.

## Commits in this PR

- `1232297` Indian data layer — Screener.in fundamentals + Moneycontrol/Mint/ET RSS news + Finnhub
- `6b45875` test: capture analyst non-regression baseline before 4a refactor
- `de274a4` feat(llm): add cache_system kwarg to LLMProvider.complete (Anthropic wires; others no-op)
- `f751ef4` Task 4: Add source dossier builder for Critic agent
- `63eea0b` feat(agents): add deterministic Data agent with parallel fetches + dossier
- `021db9f` feat(data): critiques table + payload_json column + recent_analysis cache helper
- `56f3b77` feat(agents): add Critic agent with parse_critique and retry-friendly failure mode
- `e65f45d` feat(agents): add Analyst agent (extracted from supervisor.py); preserves baseline parse
- `6249c13` feat(agents): add analyze_flow orchestrator with retry-degrade Critic + result cache
- `cc95857` feat(agents): add Agent protocol + AgentRegistry
- `a03f86b` feat(ui): extend analysis_panel with optional critic block + degraded badge
- `ac8bd74` refactor: rewire /analyze to multi-agent flow; rename supervisor→analyst; drop legacy module

## Surprises

| What | Why it surprised | Resolution |
|---|---|---|
| `analyses.id` is VARCHAR (uuid4), not INTEGER | Spec §8 declared FK as INTEGER; we caught it before writing the migration | Migration uses `VARCHAR` for `critiques.analysis_id` |
| `analyses` table only stored bull/bear/confidence — variant/conviction/etc. lived only in memory | Result-cache rehydration would lose 4 of 7 fields without a schema change | Added nullable `payload_json` column on `analyses`; older rows still read fine (NULL) |
| Existing fetchers are sync `def`, not `async def` | `asyncio.gather` directly on them would block the event loop | Wrap with `asyncio.to_thread` per fetch in `DataAgent.run` |
| Critic verdict from a malformed model response is unparseable | Risk: degrade silently to "no critic shown" with no record | Added explicit `degraded=True` row in `critiques` so failures are forensically auditable |

## Before / After

| Aspect | Before (Phase 1) | After (4a) |
|---|---|---|
| LLM calls per `/analyze` | 1 (analyst.md) | 2 (analyst.md + critic.md), or 0 on cache hit |
| Adversarial check | none | every call, with degraded badge on failure |
| Source verification | self-policed by analyst | Critic checks `[src: ...]` against a compact dossier |
| Cost (cold) | ~4500 tokens | ~5500 tokens (+22%) |
| Cost (within 5min same ticker) | ~4500 tokens | 0 (result cache) |
| Cost (within 5min, different ticker) | ~4500 tokens | ~3500 tokens (system prompts cached) |
| Bull-Bear split | analyst.md v2 (single call) | analyst.md v2 (unchanged — `Bull-Bear` agent stays out) |
| Framework | none | hand-rolled `agents.AgentRegistry` over `router.for_agent` |

## Cross-links
- Spec: `docs/superpowers/specs/2026-04-28-multi-agent-scaffold-4a-design.md`
- Plan: `docs/superpowers/plans/2026-04-28-multi-agent-scaffold-4a.md`
- ADR: [[ADR-013 Hand-rolled Async over CrewAI for Phase 2]]
- Phase: [[Phase 2 - Multi-Agent Foundation]]
- Architecture: [[01 - Architecture/Agent System]]
