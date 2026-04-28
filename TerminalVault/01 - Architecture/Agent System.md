# Agent System

> Back to [[Index]] | See also [[ADR-002 CrewAI then LangGraph]] · [[ADR-008 Phase 2.5 Analyst-Grade Layer]] · [[LLM Abstraction Layer]]

---

## All 13 agents by phase

| # | Agent | Phase | Default LLM | Key tools | Responsibility |
|---|---|---|---|---|---|
| 1 | **Supervisor** | 1 | Claude Sonnet 4.6 | all | Decompose user query, route, synthesize, run self-critique |
| 2 | **Data** | 1 | Qwen3 8B | OpenBB, NSE/BSE | Quotes, fundamentals, screening |
| 3 | **News & Trend** | 2 | Qwen3 8B + embeddings | RSS, NewsAPI, ChromaDB | Pull, dedupe, cluster, summarize, surface trends |
| 4 | **Critic** | 2 | Claude Sonnet 4.6 | (read-only) | Adversarial review: missing data, logical gaps, confidence |
| 5 | **Quant / Bull-Bear** | 2 | Claude Sonnet 4.6 | DuckDB, OpenBB | Build weighted bull and bear case |
| 6 | **X Sentiment** *(optional)* | 2.5 | grok-3-mini | xAI API, DuckDB | Retrieve + score X posts, archive citations. Loaded only if `SENTIMENT_ENABLED=true`. |
| 7 | **Transcript** | 2.5 | Qwen3 8B + Claude | NSE/BSE, Trendlyne, screener.in, faster-whisper, ChromaDB | Fetch concall transcripts (PDF or audio), topic extraction, YoY language drift |
| 8 | **CEO Tracker** | 2.5 | Qwen3 8B | YouTube Data API, EDGAR, NSE filings, Whisper | Transcribe, extract themes, alert on shifts |
| 9 | **Ownership** | 2.5 | Phi-4 Mini | NSE/BSE shareholding, SEBI SAST, AMFI | FII/DII/promoter delta, pledge changes, block/bulk deals |
| 10 | **Quality / Forensic** | 2.5 | Phi-4 Mini (formula-based) | DuckDB | Piotroski F, Beneish M, Altman Z, Montier C scores |
| 11 | **Comps** | 2.5 | Qwen3 8B | DuckDB, OpenBB | Peer multiples table, color-coded vs. peer median + own 5Y history |
| 12 | **Macro** | 2.5 | Phi-4 Mini | OpenBB, FRED, RBI | DXY, US 10Y, USD/INR, Brent, India VIX; sector beta overlays |
| 13 | **Calendar** | 2.5 | (no LLM) | NSE/BSE corp actions, RBI/Fed schedules | Earnings, ex-div, AGM, board meetings, policy events |

**Total: 13 agents** (12 without Sentiment if `SENTIMENT_ENABLED=false`).

---

## LLM tier assignments (Phase 2.5)

| Tier | Agents | LLM |
|---|---|---|
| Synthesis | Supervisor, Critic, Bull-Bear, Transcript-synthesize | Claude Sonnet 4.6 |
| Mid-tier extraction | Data, News, Transcript-extract, CEO Tracker, Comps | Qwen3 8B (Ollama) |
| Fast classification | Quality, Macro, Ownership, Calendar | Phi-4 Mini |
| External retrieval | Sentiment (optional) | grok-3-mini |

---

## Orchestration framework by phase

| Phase | Framework | Notes |
|---|---|---|
| 1 | None (direct router call) | Single agent, sync call via `asyncio.run` |
| 2–2.5 | CrewAI | Role mapping; registers agents 1–5 (Phase 2), then 1–13 (Phase 2.5) |
| 3+ | LangGraph (hot paths) | `/analyze` migrated for cyclical critique, conditional re-fetch |

See [[ADR-002 CrewAI then LangGraph]] for the migration rationale.

---

## Sentiment agent gating

The Sentiment Agent is not registered with the CrewAI orchestrator at startup unless:

```bash
SENTIMENT_ENABLED=true
GROK_API_KEY=<key>
```

See [[ADR-005 Sentiment is Optional Feature-Flagged Module]].

---

## Phase 1 status

Phase 1 has one active agent: **Supervisor** (`src/finterminal/agents/supervisor.py`). The Data Agent's responsibilities (OpenBB fetch, DuckDB store) are handled inline within `analyze_ticker()` for simplicity. Full agent separation happens in Phase 2. See [[agents — supervisor]] for the code map.

**Current Supervisor model:** `gpt-5-mini` (was `claude-sonnet-4-6`; swapped via `config/agents.yaml` after user added OpenAI access). The model abstraction ([[ADR-006 Model Abstraction in Phase 1]]) makes this a YAML-only change. See [[2026-04-28 - Days 3-5 analyze on gpt-5-mini]] for the gpt-5 quirks fixed (max_completion_tokens, 8000-token reasoning floor).

**Current `analyst.md` prompt:** v2 (commit `47b210d`) — see [[prompts]]. Adds Variant Perception + Conviction tiering + 6-factor weighting hierarchy per [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]].

---

## Phase 3 — Synthesis Layer agents (per [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]])

Five additional agents on top of Phase 2.5's 13. These are the moat — capabilities JP Morgan structurally cannot have for career / compliance reasons:

| # | Agent | Purpose | Default LLM |
|---|---|---|---|
| 14 | **Regime Detector** | Layer 1+2 z-scores → `risk_on / risk_off / transition_*` + rationale | Phi-4 Mini (rules-based v1) |
| 15 | **Scenario Engine** | P(bull)/P(base)/P(bear) per ticker + price ranges | Claude Sonnet 4.6 |
| 16 | **Signal Weighter** | Composite [-1, +1] score + Conviction tier (factor decomposition) | Phi-4 Mini |
| 17 | **Calibration Loop** | Brier-scores own predictions; surfaces tier-by-tier hit-rate in `/analyze` footer | (no LLM — pure compute) |
| 18 | **Bias Auditor** | Weekly meta-analysis of own output drift (direction / sector / confidence) | Claude Sonnet 4.6 |

Plus the **Variant-Perception Checker** added to the Critic agent — flags non-variant analyses in panel headers.

**Phase 3 total: 18 agents** (17 if Sentiment off).
