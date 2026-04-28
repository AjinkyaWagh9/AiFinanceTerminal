# System Diagram

> Back to [[Index]] | See also [[LLM Abstraction Layer]], [[Agent System]], [[Storage]]

---

## High-level diagram

```
┌───────────────────────────────────────────────────────────────┐
│                       Rich / Textual TUI                      │
│  (command parser, panels, gauges, tables, watchlist views)    │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│              Orchestrator (CrewAI → LangGraph Phase 3)        │
│  Supervisor: Claude  │  Critic: Claude  │  Router: agents.yaml│
└──┬─────────────┬──────────────┬─────────────┬─────────────────┘
   │             │              │             │
 Data         News+         Sentiment     Analyst-grade agents
 Agent        Trend         Agent*        (Phase 2.5):
              Agent                       Transcript, Ownership,
                                          Quality, Comps, Macro,
                                          CEO Tracker, Calendar
   │             │              │             │
┌──▼─────────────▼──────────────▼─────────────▼─────────────────┐
│                  Tool / Provider Layer                         │
│  OpenBB │ NSE/BSE │ RSS feeds │ xAI Grok* │ YouTube │ EDGAR   │
│  Trendlyne │ screener.in │ SEBI SAST │ AMFI │ FRED │ RBI      │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│  Storage                                                       │
│  DuckDB (analytics: OHLCV, fundamentals, news, llm_calls)     │
│  SQLite  (app state: watchlist, agent memory, run logs)        │
│  ChromaDB (embeddings: semantic news search, CEO clustering)   │
└───────────────────────────────────────────────────────────────┘

LLM Routing:
  Agents → Router → Registry → Provider → Model
             ▲          ▲          ▲
         agents.yaml  models.yaml  anthropic / ollama / xai / openai_compat

* = optional, gated by SENTIMENT_ENABLED=true
```

---

## Component descriptions

### TUI (Rich → Textual)
- **Phase 1:** Rich `Layout` + `Panel` for REPL-style output.
- **Phase 2+:** Textual full TUI with tabs (Dashboard, Ticker, News, Watchlist, Transcripts).
- Entry point: `src/finterminal/terminal.py`
- See [[ui — Rich-Textual]] for code map.

### Orchestrator
- **Phase 1:** no agent framework; Claude called directly via the router.
- **Phase 2:** CrewAI registers agents 1–5 (Supervisor, Data, News, Critic, Bull-Bear).
- **Phase 3:** LangGraph replaces CrewAI for `/analyze` hot path (cyclical critique, conditional re-fetch, human-in-loop).
- See [[ADR-002 CrewAI then LangGraph]] for the decision.

### LLM Router
- Agents call `router.for_agent("critic")` — they never name a model.
- Config lives in `config/agents.yaml` + `config/models.yaml`.
- See [[LLM Abstraction Layer]] for full design.

### Tool / Provider Layer
- OpenBB is the primary data foundation (equity quotes, fundamentals, news).
- NSE/BSE direct feeds for India-specific data (shareholding, SAST, bulk deals).
- See [[Data Sources]] for the full source inventory.

### Storage (three-tier, all embedded)
- **DuckDB** — analytical queries (time series, OHLCV, fundamentals, LLM cost tracking).
- **SQLite** — app state (watchlist, agent memory, run logs).
- **ChromaDB** — vector embeddings (semantic news search, CEO statement clustering).
- See [[Storage]] for schema design and rationale.

---

## Data flow for `/analyze RELIANCE.NS`

1. TUI parses command → dispatches to Supervisor agent.
2. Supervisor calls Data Agent → fetches quote + fundamentals + news from DuckDB (or live via OpenBB if stale).
3. Supervisor formats context block → calls `router.for_agent("supervisor")` → Claude Sonnet 4.6.
4. Claude returns structured bull/bear + confidence + assumptions.
5. Critic agent reviews output → appends confidence adjustment + dissenting view.
6. Result persisted to `analyses` table in DuckDB.
7. TUI renders side-by-side bull/bear panel with confidence gauge.
