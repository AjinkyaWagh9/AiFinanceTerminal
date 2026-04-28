# Phase 3 — Bull/Bear Depth, US Expansion, and LangGraph

> Back to [[Index]] | See also [[ADR-002 CrewAI then LangGraph]] · [[ADR-001 Indian Markets First]] · [[03 - Phases/Phase 2.5 - Analyst-Grade Layer]]

**Status:** Planned
**Target weeks:** 6–9 (after Phase 2.5 exit criteria pass)
**Source:** [PLAN.md §6 Phase 3](../docs/PLAN.md)

---

## Scope

- **LangGraph migration** for `/analyze` flow (cyclical critique, conditional re-fetch, human-in-loop checkpoints).
- **Multi-LLM router upgrades:** cheap classification → Phi-4 Mini; code/multilingual → Qwen3; synthesis → Claude; large-context → NIM.
- **US expansion:** Finnhub for US quotes/fundamentals; broader CEO list (Dimon, Fink, Pichai, Nadella).
- **Probabilistic bull/bear:** weight factors, surface probability ranges not point estimates.
- **Light backtesting hooks** via vectorbt.
- **Hot reload** of `agents.yaml` + `models.yaml` without terminal restart.
- **A/B testing** two models on the same agent.
- Optional: exo evaluation if a second Apple device is added (BACKLOG.md §1.10).

---

## New / updated commands

| Command | Notes |
|---|---|
| `/bullbear-prob TICKER` | Probabilistic scenarios with explicit weights |
| `/backtest <strategy>` | Light vectorbt hooks on DuckDB OHLCV |
| `/llm-reload` | Hot-reload agent/model config |
| `/llm-test <model>` | Side-by-side model smoke test (Phase 2 helper, formalized) |

---

## LangGraph migration trigger

BACKLOG.md §1.2: migrate when ≥30% of `/analyze` runs need a re-fetch round, or when human-in-loop checkpoints are required. Not before.

---

## US data sources added

| Source | What |
|---|---|
| Finnhub free tier | US equity quotes, fundamentals, news |
| SEC EDGAR | 13F filings, 10-K, 10-Q, 8-K |
| FRED (already in 2.5) | US macro series |

---

## Exit criteria

Phase 2.5 exit criteria fully passed on Indian watchlist before starting Phase 3.

---

## Key risks

| Risk | Mitigation |
|---|---|
| LangGraph migration scope creep | Migrate only `/analyze` hot path; leave other commands on CrewAI |
| Probabilistic weights uncalibrated | Requires 6 months of `/analyze` outputs in DuckDB (BACKLOG.md §1.3) |
| exo cluster complexity | Defer until second device acquired and NIM/Claude no longer covers the gap |
