# FINTERMINAL — Bloomberg-Style Equity Research Terminal

**Owner:** Ajinkya Wagh
**Hardware:** MacBook M4 Air, 16 GB unified memory
**Date:** 2026-04-27
**Source of truth (initial):** `context.md`

---

## 1. Executive Summary

A local-first, AI-augmented equity research terminal that delivers four capabilities a retail Bloomberg surrogate cannot easily get bundled today:

1. **Live market data + fundamentals** for NSE/BSE (Phase 1) and US (Phase 3) via OpenBB.
2. **Trending news + topic clustering** across financial press, regulatory filings, and macro feeds.
3. **X (Twitter) sentiment analysis** via xAI Grok's Live Search — **optional, feature-flagged module** that the terminal works perfectly without.
4. **CEO/leader signal tracking** for Jensen Huang, Jamie Dimon, Larry Fink, Satya Nadella, Sundar Pichai, plus Indian leaders (Mukesh Ambani, N. Chandrasekaran, Uday Kotak) — earnings calls, conference appearances, podcasts, shareholder letters.
5. **Analyst-grade research layer (Phase 2.5):** earnings-call transcript intelligence, consensus estimates with revision tracking, ownership flows (FII/DII/promoter/pledges/block deals), forensic quality scores (Piotroski / Beneish / Altman / Montier), and peer-comp tables — what a junior buy-side analyst at a Mumbai fund actually opens at 8 AM.

A multi-agent layer (CrewAI → LangGraph migration path) orchestrates Claude (synthesis, bull/bear, self-critique) alongside a local Qwen3-class model (cheap summarization, classification) with NVIDIA NIM as a managed-cloud burst lane.

**Differentiators vs. just-using-OpenBB:**
- Sentiment + CEO signals fused into the same analytical surface as price/fundamentals.
- Self-critique loop on every recommendation (confidence score, dissenting view).
- Investment-philosophy framing baked into prompts (Rich Dad asset/liability lens, Stoic uncertainty, Munger inversion).

---

## 2. Goals, Non-Goals, and Success Metrics

### Goals (in priority order)
1. **G1 — Daily-driver utility:** the terminal is faster than opening 6 browser tabs to answer "what's moving RELIANCE today and why?"
2. **G2 — Signal extraction:** detect non-obvious cross-asset narratives (e.g., "Jensen mentioned 'sovereign AI' on 3 calls in 2 weeks → tailwind for HCLTech, Infy GPU partnerships").
3. **G3 — Bull/bear discipline:** every analysis ends with a confidence score, dissenting view, and explicit assumptions.
4. **G4 — Local-first privacy:** watchlist, queries, notes never leave the machine unless explicitly routed to Claude/NIM.

### Non-Goals (Phase 1–3)
- Order execution / brokerage integration (regulatory burden, no edge).
- Full backtesting platform (deprioritized; light hooks only in Phase 3).
- Mobile/web clients (terminal-only until Phase 4+).
- Options analytics, derivatives chains (post-Phase 4).

### Success Metrics
| Metric | Target by end of Phase 2 |
|---|---|
| Time to answer "should I look at $TICKER today?" | < 15 seconds |
| Tickers tracked simultaneously | ≥ 25 |
| News articles processed daily (cached, deduped) | ≥ 500 |
| X posts analyzed daily (curated list) | ≥ 1,000 |
| CEO transcript ingestions per week | ≥ 5 |
| Self-critique invoked on every recommendation | 100% |
| Local-model fallback when Claude unavailable | Works offline |

---

## 3. Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          Rich/Textual TUI                                 │
│  Surfaces: /heatmap (3-layer)  /analyze  /screen  /pair  /alerts         │
└──────────────────────────────┬────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────────────────┐
│  Synthesis Layer (Phase 3 — the actual edge)                              │
│  Regime Detector │ Scenario Engine │ Signal Weighter │ Bias Auditor       │
└──────────────────────────────┬────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────────────────┐
│              Orchestrator (CrewAI → LangGraph)                            │
│  Supervisor │ Critic │ Variant-Perception Checker │ Router                │
└──┬────────┬────────┬─────────┬─────────┬─────────┬────────┬─────────┬────┘
   │        │        │         │         │         │        │         │
┌──▼─────┐┌─▼─────┐┌─▼──────┐┌─▼──────┐┌─▼──────┐┌─▼──────┐┌▼───────┐┌▼─────┐
│ Data   ││ News  ││Sentmnt*││Trnscrpt││ Owner- ││Quality ││Comps + ││Macro │
│ Agent  ││+Trend ││(Grok)  ││+CEO    ││ ship   ││Forensc.││Pair    ││3-Lyr │
└──┬─────┘└─┬─────┘└─┬──────┘└─┬──────┘└─┬──────┘└─┬──────┘└┬───────┘└┬─────┘
   │        │        │         │         │         │        │         │
┌──▼────────▼────────▼─────────▼─────────▼─────────▼────────▼─────────▼────┐
│              Tool / Provider Layer                                         │
│  OpenBB │ NSE/BSE │ Trendlyne │ Screener │ SEBI SAST │ AMFI │ NSDL/CDSL  │
│  RSS (Mint/MC/ET) │ Grok Live Search │ YouTube+Whisper │ RBI DBIE │ FRED │
│  MOSPI │ S&P PMI │ gst.gov.in │ FBIL  │ NSE bhavcopy/sectoral indices    │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────────────┐
│  Storage: DuckDB (analytics) + SQLite (state) + ChromaDB (embeddings)     │
│  Calibration store: predictions table → Brier scoring after outcome       │
└────────────────────────────────────────────────────────────────────────────┘

LLM Routing (see §3.1 for the abstraction layer):

  Agents ──► Router ──► Registry ──► Provider ──► Model
                ▲          ▲           ▲           ▲
        agents.yaml  models.yaml  anthropic    claude-sonnet-4-6
                                  ollama       qwen3:8b
                                  xai          grok-3-mini
                                  openai-compat NIM / LM Studio
```

---

## 3.1 Model Abstraction Layer (so models are dynamic)

**Design goal:** swapping `qwen3:8b → qwen3:32b` for one agent, or `claude-sonnet-4-6 → claude-opus-4-7` globally, is a **YAML edit, not a code change.** Adding a new provider (Together.ai, Groq, OpenRouter) is a single file. The agent code never names a model.

### Components

```
src/finterminal/llm/
├── base.py              # LLMProvider protocol; Message, Completion, ToolSpec dataclasses
├── registry.py          # ModelRegistry: loads models.yaml, returns provider handles
├── router.py            # Router: agents.yaml → for_agent("supervisor") → handle
├── budget.py            # CostTracker, BudgetGuard, per-agent caps
├── cache.py             # response cache keyed by (model, prompt-hash)
└── providers/
    ├── anthropic.py     # implements LLMProvider for Claude
    ├── ollama.py        # implements for local
    ├── xai.py           # implements for Grok + Live Search
    ├── openai_compat.py # implements for any OpenAI-compatible (NIM, LM Studio, OpenRouter, Together)
    └── null.py          # no-op for agents like Calendar that don't need an LLM
```

### Interface (the only thing agents see)

```python
class LLMProvider(Protocol):
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
    ) -> Completion: ...

    @property
    def metadata(self) -> ModelMetadata: ...
```

```python
@dataclass
class ModelMetadata:
    name: str                       # "qwen3:8b"
    provider: str                   # "ollama"
    api_id: str                     # provider-specific identifier
    context_window: int
    cost_per_mtok_in: float
    cost_per_mtok_out: float
    capabilities: set[str]          # {"reasoning","tool_use","vision","json_mode","live_search"}
    tags: set[str]                  # {"fast","cheap","synthesis","multilingual","local"}
```

### Configuration files (the only thing you edit to swap)

`config/models.yaml` — declares what's available:

```yaml
models:
  - name: qwen3:8b
    provider: ollama
    api_id: qwen3:8b
    context_window: 32768
    cost_per_mtok_in: 0.0
    cost_per_mtok_out: 0.0
    capabilities: [reasoning, tool_use, multilingual, json_mode]
    tags: [local, cheap, fast]

  - name: qwen3:32b           # added for upgrade — see MODEL-SWAP-GUIDE.md
    provider: ollama
    api_id: qwen3:32b
    context_window: 32768
    cost_per_mtok_in: 0.0
    cost_per_mtok_out: 0.0
    capabilities: [reasoning, tool_use, multilingual, json_mode]
    tags: [local, premium, slow]

  - name: phi4-mini
    provider: ollama
    api_id: phi4-mini
    context_window: 16384
    cost_per_mtok_in: 0.0
    cost_per_mtok_out: 0.0
    capabilities: [classification, json_mode]
    tags: [local, very-fast, classifier]

  - name: claude-sonnet-4-6
    provider: anthropic
    api_id: claude-sonnet-4-6
    context_window: 200000
    cost_per_mtok_in: 3.0
    cost_per_mtok_out: 15.0
    capabilities: [reasoning, tool_use, vision, json_mode, synthesis]
    tags: [cloud, premium, synthesis]

  - name: claude-opus-4-7
    provider: anthropic
    api_id: claude-opus-4-7
    context_window: 1000000
    cost_per_mtok_in: 15.0
    cost_per_mtok_out: 75.0
    capabilities: [reasoning, tool_use, vision, json_mode, synthesis, deep_reasoning]
    tags: [cloud, premium, deep-thinking]

  - name: grok-3-mini
    provider: xai
    api_id: grok-3-mini
    context_window: 131072
    cost_per_mtok_in: 0.30
    cost_per_mtok_out: 0.50
    capabilities: [classification, live_search, x_data]
    tags: [cloud, cheap, sentiment]
```

`config/agents.yaml` — assigns models to agents:

```yaml
agents:
  supervisor:    { primary: claude-sonnet-4-6, fallbacks: [claude-opus-4-7] }
  data:          { primary: qwen3:8b,         fallbacks: [claude-sonnet-4-6] }
  news:          { primary: qwen3:8b,         fallbacks: [claude-sonnet-4-6] }
  critic:        { primary: claude-sonnet-4-6, fallbacks: [claude-opus-4-7] }
  bull_bear:     { primary: claude-sonnet-4-6, fallbacks: [claude-opus-4-7] }

  # Phase 2.5
  sentiment:     { primary: grok-3-mini,      fallbacks: [],                 enabled: false }
  transcript:
    extract:     { primary: qwen3:8b,         fallbacks: [claude-sonnet-4-6] }
    synthesize:  { primary: claude-sonnet-4-6, fallbacks: [claude-opus-4-7] }
  ceo_tracker:   { primary: qwen3:8b,         fallbacks: [claude-sonnet-4-6] }
  ownership:     { primary: phi4-mini,        fallbacks: [qwen3:8b] }
  quality:       { primary: phi4-mini,        fallbacks: [qwen3:8b] }
  comps:         { primary: qwen3:8b,         fallbacks: [claude-sonnet-4-6] }
  macro:         { primary: phi4-mini,        fallbacks: [qwen3:8b] }
  calendar:      { primary: null }   # no LLM
```

### How agents consume it

```python
# inside src/finterminal/agents/critic.py (illustrative)
class CriticAgent:
    def __init__(self, router: Router):
        self._llm = router.for_agent("critic")     # never names a model

    async def review(self, analysis: str) -> Critique:
        return await self._llm.complete(
            system=load_prompt("critic.md"),
            messages=[Message(role="user", content=analysis)],
        )
```

The agent doesn't know it's talking to Claude vs. Qwen vs. Grok. Swap is invisible.

### What "dynamic" means at each phase

| Capability | Phase | Mechanism |
|---|---|---|
| Per-agent model assignment | 1 | `agents.yaml` |
| New provider plug-in | 1 | drop a file in `providers/` |
| Cost logging per call | 1 | `budget.py` writes to DuckDB `llm_calls` table |
| Fallback on provider error | 2 | Router retries down `fallbacks` list |
| Per-agent cost cap | 2.5 | `BudgetGuard` raises before calling if monthly cap hit |
| Capability-based routing (`router.for_capability("synthesis")`) | 2.5 | Registry indexes by capability/tag |
| Hot reload of `agents.yaml` without restart | 3 | filesystem watcher |
| A/B testing two models on same agent | 3 | `mode: ab_test` in agents.yaml, log both responses |
| Auto-tier-up (use Opus when Sonnet's confidence < threshold) | 4 | Critic-driven escalation |

### Why this is the right shape

- **Provider is a class, model is data.** Adding qwen3:32b is `models.yaml` + `ollama pull`. Adding Together.ai is one new provider class implementing 1 protocol method.
- **Agents are written once.** They name a *role*, not a model. The Critic doesn't change when Claude releases version 5.
- **Cost stays observable.** Every call writes `(agent, model, tokens_in, tokens_out, cost_usd)` to DuckDB. After a month you can ask: "which agent eats my Claude budget?"
- **No premature abstraction.** The Phase-1 implementation is ~200 lines of Python. Capability routing, A/B, hot-reload come later only when needed. The interface accommodates them; the code doesn't pre-build them.

See `MODEL-SWAP-GUIDE.md` for step-by-step playbooks: swapping a single agent's model, swapping globally, adding a new provider, and migrating to bigger local models when you upgrade hardware.

---

## 4. Decision Matrices

Each matrix scores 1–5 (5 = best). **Score** column = weighted total per the Weight column. Recommended choice in **bold**.

### 4.1 Agent Framework
| Aspect | Weight | LangGraph | CrewAI | AutoGen | Custom (asyncio) |
|---|---:|---:|---:|---:|---:|
| Control / state machines | 5 | 5 | 3 | 3 | 4 |
| Speed to MVP | 4 | 2 | 5 | 4 | 3 |
| Multi-LLM routing | 4 | 5 | 4 | 4 | 5 |
| Self-critique cycles | 4 | 5 | 3 | 4 | 4 |
| Observability | 3 | 5 (LangSmith) | 3 | 3 | 1 |
| Ecosystem / docs | 3 | 5 | 4 | 3 | 1 |
| **Weighted score** |  | **107** | **86** | **87** | **78** |

**Choice:** **CrewAI for Phase 1–2** (fast wins, role mapping is intuitive) → **migrate hot paths to LangGraph in Phase 3** for self-critique loops, probabilistic forecasting, and human-in-loop checkpoints. Both compose with LangChain so migration is incremental, not a rewrite.

### 4.2 Local LLM (M4 Air 16 GB)
| Aspect | Weight | Qwen3 8B (Q4) | Gemma 4 12B (Q4) | Phi-4 Mini | Llama 4 8B |
|---|---:|---:|---:|---:|---:|
| Reasoning quality | 5 | 5 | 4 | 3 | 4 |
| Multilingual (Hindi/Marathi headlines) | 4 | 5 | 3 | 2 | 3 |
| Coding/tool-use | 4 | 5 | 4 | 4 | 4 |
| Speed on M4 Air | 5 | 4 | 3 | 5 | 4 |
| RAM headroom (leaves room for OpenBB+Chrome) | 5 | 5 | 3 | 5 | 5 |
| **Weighted score** |  | **111** | **80** | **89** | **94** |

**Choice:** **Qwen3 8B Q4_K_M via Ollama+MLX** as default local. Keep **Phi-4 Mini** as the "fast classifier" model for sentiment scoring and routing decisions where 100ms matters more than depth.

### 4.3 X (Twitter) Sentiment Acquisition
| Aspect | Weight | **xAI Grok + Live Search** | X API v2 (Basic) | X API (Free) | StockTwits API | Skip sentiment |
|---|---:|---:|---:|---:|---:|---:|
| Legality / ToS safety | 5 | 5 | 5 | 5 | 5 | 5 |
| Cost (Phase 2 steady state) | 4 | 5 (~$5–95/mo) | 2 ($200/mo flat) | 5 | 4 | 5 |
| Reliability | 5 | 4 | 5 | 3 | 4 | 5 |
| Setup / maintenance burden | 5 | 5 (one API) | 2 (rate limits, polling, FinBERT) | 2 | 4 | 5 |
| Real-time freshness | 4 | 5 | 5 | 3 | 4 | 1 |
| Raw-post archive for backtest | 3 | 2 (must log responses) | 5 | 4 | 4 | 1 |
| Account-level determinism | 3 | 3 (Grok picks) | 5 | 5 | 4 | 1 |
| **Weighted score** |  | **108** | **101** | **80** | **94** | **84** |

**Choice:** **xAI Grok with Live Search** as the sole sentiment provider. Pattern: prompt grok-3-mini with `"Summarize sentiment on $TICKER from X over the last N hours, cite the top 5 posts"`, store both the structured response and Grok's citations in DuckDB. Claude still owns synthesis and critique — Grok is a retrieval+classification tool, not an analyst.

**Verified pricing (xAI docs, 2026-04-27):** Live Search $5 / 1k calls. Per-token rates checked at `console.x.ai`. Estimated Phase-2 monthly cost: **$5–95** depending on cadence (hourly market sweep → ticker-level hourly).

**Optionality is mandatory.** The sentiment module is gated by `SENTIMENT_ENABLED=true` and `GROK_API_KEY` in `.env`. If either is missing:
- `/sentiment` command prints a one-line "sentiment disabled" notice with setup instructions.
- Sentiment panels in the TUI degrade gracefully (hidden or shown as "—").
- `/analyze` runs the full bull/bear flow on fundamentals + news only; the critic flags "sentiment input unavailable" in the assumptions block.
- The Sentiment Agent is not registered with the CrewAI orchestrator at startup.
- Zero code paths require Grok; the terminal is a complete product without it.

**Why this design:** sentiment is the highest-cost, highest-volatility input. Making it optional keeps the terminal usable on a plane, lets you A/B "with vs. without sentiment" calls to measure if it actually helps, and means a Grok outage doesn't break the daily workflow.

### 4.4 News Data Sources
| Aspect | Weight | NewsAPI.org | OpenBB news connectors | RSS aggregator (custom) | Finnhub | GDELT |
|---|---:|---:|---:|---:|---:|---:|
| Indian coverage (ET, Mint, MoneyControl, BS) | 5 | 3 | 4 | 5 | 2 | 3 |
| Free tier viability | 4 | 4 | 5 | 5 | 4 | 5 |
| Structured metadata (ticker, sector tags) | 4 | 2 | 4 | 2 | 5 | 3 |
| Latency | 3 | 3 | 4 | 5 | 4 | 2 |
| **Weighted score** |  | **51** | **76** | **76** | **67** | **62** |

**Choice:** **OpenBB connectors + custom RSS layer** (Mint, MoneyControl, BloombergQuint/Quintype, Reuters India, Livemint, ET Markets). Add **Finnhub free tier** for US coverage starting Phase 3. **NewsAPI is a fallback only** — its India coverage is thin.

### 4.5 CEO / Leader Signal Acquisition
| Aspect | Weight | YouTube API + Whisper | Earnings call transcripts (paid) | SEC EDGAR / NSE filings | Podcast RSS + Whisper | Manual curated alerts |
|---|---:|---:|---:|---:|---:|---:|
| Coverage (Jensen, Dimon, Fink, Indian leaders) | 5 | 5 | 4 (US only) | 3 | 4 | 3 |
| Cost | 4 | 5 (free) | 1 | 5 | 5 | 5 |
| Freshness (within 24h of event) | 4 | 4 | 3 | 5 | 3 | 5 |
| Setup complexity | 3 | 3 | 5 | 4 | 3 | 5 |
| **Weighted score** |  | **76** | **53** | **76** | **70** | **72** |

**Choice:** **YouTube Data API + faster-whisper for transcription + SEC EDGAR / NSE corporate-announcements feeds**, with an LLM-driven topic-extractor that builds a per-leader knowledge base (key themes, position changes, recurring concerns). Skip paid transcript services until clear ROI.

### 4.6 Sentiment Analysis Approach
| Aspect | Weight | LLM-only (Claude/Qwen) | FinBERT | Hybrid (FinBERT screen + LLM nuance) | VADER + lexicon |
|---|---:|---:|---:|---:|---:|
| Accuracy on financial text | 5 | 4 | 5 | 5 | 2 |
| Cost per 1000 posts | 5 | 2 | 5 | 4 | 5 |
| Handles sarcasm / "diamond hands" | 4 | 5 | 2 | 4 | 1 |
| Multilingual (Hinglish tweets) | 4 | 5 | 1 | 3 | 1 |
| Latency | 3 | 3 | 5 | 4 | 5 |
| **Weighted score** |  | **76** | **66** | **88** | **49** |

**Choice:** **Hybrid** — FinBERT (or local Phi-4 Mini fine-tuned classifier) for fast first-pass scoring on every post; promote borderline / high-engagement / multi-lingual posts to Claude or Qwen3 for nuanced interpretation. Keeps cost bounded; preserves quality on the posts that actually matter.

### 4.7 Terminal UI
| Aspect | Weight | Rich (panels) | Textual (TUI app) | Custom curses | Web (FastAPI + HTMX) |
|---|---:|---:|---:|---:|---:|
| Bloomberg-feel density | 5 | 4 | 5 | 4 | 4 |
| Build speed | 4 | 5 | 3 | 1 | 3 |
| Interactive widgets (live gauges) | 4 | 3 | 5 | 3 | 5 |
| Reflows on terminal resize | 3 | 4 | 5 | 2 | 5 |
| **Weighted score** |  | **70** | **76** | **42** | **70** |

**Choice:** **Rich for Phase 1 → Textual for Phase 2+.** Both are from the same author (Will McGugan), so migration is staged: Rich's `Layout` and `Panel` primitives translate cleanly into Textual `Widget`s.

### 4.8 Storage Layer
| Aspect | Weight | DuckDB | SQLite | Postgres (local) | Parquet files |
|---|---:|---:|---:|---:|---:|
| Analytical queries (OHLCV, time series) | 5 | 5 | 2 | 4 | 4 |
| Embedded / zero-ops | 5 | 5 | 5 | 1 | 5 |
| Concurrent writes (agents writing simultaneously) | 4 | 3 | 4 | 5 | 2 |
| Vector search | 3 | 3 (extension) | 2 | 4 (pgvector) | 1 |
| **Weighted score** |  | **78** | **63** | **66** | **57** |

**Choice:** **DuckDB for analytics** (quotes, fundamentals, OHLCV history) + **SQLite for app state** (watchlist, agent memory, run logs) + **ChromaDB for embeddings** (semantic news search, CEO statement clustering). Three-tier is fine — each is embedded, no servers.

### 4.9 LLM Inference Orchestration
| Aspect | Weight | Ollama | LM Studio | MLX direct | NVIDIA NIM (cloud) |
|---|---:|---:|---:|---:|---:|
| OpenAI-compatible API | 5 | 5 | 5 | 2 | 5 |
| M4 throughput | 5 | 4 (now ships MLX backend) | 4 | 5 | n/a |
| Model breadth | 4 | 5 | 5 | 3 | 5 |
| Setup friction | 4 | 5 | 4 | 2 | 3 |
| **Weighted score** |  | **89** | **84** | **57** | **70** |

**Choice:** **Ollama as primary** local runtime. **NVIDIA NIM** as managed-cloud fallback when local is too slow or you need a 70B-class model. Skip MLX-direct unless you hit a ceiling.

### 4.10 Distributed Inference (exo)
**Decision:** **Defer to Phase 3+.** Single-machine works until you genuinely need a 70B+ model. Adding exo before that is premature optimization.

---

## 5. System Components

### 5.1 Agents (CrewAI roles, by phase)
| # | Agent | Phase | Model | Tools | Responsibility |
|---|---|---|---|---|---|
| 1 | Supervisor | 1 | Claude (Sonnet 4.6) | all | Decompose user query, route, synthesize, run self-critique |
| 2 | Data | 1 | Qwen3 8B | OpenBB, NSE/BSE | Quotes, fundamentals, screening |
| 3 | News & Trend | 2 | Qwen3 8B + embeddings | RSS, NewsAPI, ChromaDB | Pull, dedupe, cluster, summarize, surface trends |
| 4 | Critic | 2 | Claude | (read-only) | Adversarial review: missing data, logical gaps, confidence |
| 5 | Quant / Bull-Bear | 2 | Claude | DuckDB, OpenBB | Build bull and bear case with weighted factors |
| 6 | X Sentiment *(optional)* | 2.5 | Grok-3-mini + Live Search | xAI API, DuckDB | Retrieve + score posts, archive citations. Loaded only if `SENTIMENT_ENABLED=true`. |
| 7 | Transcript | 2.5 | Qwen3 8B + Claude | NSE/BSE, faster-whisper, ChromaDB | Pull concall recordings/PDFs, transcribe if needed, extract topics, YoY language drift |
| 8 | CEO Tracker | 2.5 | Qwen3 8B | YouTube, EDGAR, NSE filings, Whisper | Transcribe, extract themes, alert on shifts (moved from Phase 2 — it's analyst-grade signal, not a starter feature) |
| 9 | Ownership | 2.5 | Phi-4 Mini | NSE/BSE shareholding, SEBI SAST, AMFI | FII/DII/promoter delta, pledge changes, block/bulk deals, MF holding shifts |
| 10 | Quality / Forensic | 2.5 | Phi-4 Mini (formula-based) | DuckDB | Piotroski F, Beneish M, Altman Z, Montier C scores; DSO/inventory-days trends |
| 11 | Comps | 2.5 | Qwen3 8B | DuckDB, OpenBB | Peer-set construction, multiples vs. peer median + own 5Y history (z-scores) |
| 12 | Macro | 2.5 | Phi-4 Mini | OpenBB, FRED, RBI | DXY, US 10Y, USD/INR, Brent, India VIX; sectoral beta overlays |
| 13 | Calendar | 2.5 | (no LLM) | NSE/BSE corp actions, RBI/Fed schedules | Earnings, ex-div, AGM, board meetings, policy events |

### 5.2 Command Surface (cumulative through phases)
```
# Phase 1
/ticker RELIANCE              # snapshot panel
/news NSE                     # trending news
/fundamentals HDFC            # PE, EPS, ROE, debt/equity
/screen growth banking        # screener
/analyze RELIANCE             # full bull/bear with critic
/watch add INFY               # watchlist mgmt
/critique <last>              # re-run critic

# Phase 2
/trends sector                # cross-source narrative clusters
/critic-deep RELIANCE         # heavy critique cycle

# Phase 2.5 (analyst-grade layer)
/transcript RELIANCE Q3       # latest concall, topic-tagged
/transcript-diff RELIANCE     # YoY/QoQ language drift, mention counts
/consensus RELIANCE           # estimates table + revision trend
/revisions RELIANCE 30d       # upgrades/downgrades over window
/ownership RELIANCE           # FII/DII/promoter/pledge snapshot + deltas
/flows NIFTY                  # sectoral FII flow heatmap
/quality RELIANCE             # Piotroski/Beneish/Altman/Montier scores
/quality-cohort banking       # rank a sector by forensic flags
/comps RELIANCE               # peer multiples table, color-coded
/sector-screen IT value       # cheap names in a sector
/ceo jensen                   # latest signals from a leader
/sentiment NIFTY50            # Grok X-sentiment (if enabled)
/macro                        # DXY/US10Y/INR/Brent dashboard
/macro-impact RELIANCE        # ticker beta to macro factors
/events week                  # upcoming earnings/policy/corp actions
/events RELIANCE              # ticker-specific calendar

# Phase 3
/bullbear-prob RELIANCE       # probabilistic scenarios with weights
/backtest <strategy>          # light vectorbt hooks
```

### 5.3 Prompt Frames (Claude system prompts)
- **Rich Dad lens:** "Distinguish assets (cash-flow producing, appreciating) from liabilities. Flag if a thesis depends on multiple expansion vs. earnings growth."
- **Stoic uncertainty:** "Name what you cannot know. State assumptions explicitly before conclusions."
- **Munger inversion:** "Before recommending action, list how this thesis fails. If you cannot articulate the bear case crisply, you don't understand the bull case."
- **Source discipline:** "Every numeric claim cites its source row in DuckDB or its URL. No source → don't say it."

---

## 6. Phased Roadmap (Refined)

### Phase 1 — Core Terminal + Indian Equities MVP (Weeks 1–2)
**Deliverable:** working terminal, 6 commands, single AI command.
- Repo scaffolding, `pyproject.toml`, ruff/black, pre-commit.
- `terminal.py` command parser + Rich layout.
- OpenBB integration: quotes, fundamentals, news for NSE/BSE.
- DuckDB schema: `quotes`, `fundamentals`, `news`.
- Ollama + Qwen3 8B installed; `/analyze TICKER` runs summary + simple bull/bear via Claude.
- Disclaimer + source-citation guardrails.
- **Exit criteria:** can use the terminal in lieu of MoneyControl for a daily check-in on 5 watchlist tickers.

### Phase 2 — Multi-Agent Foundation + News Trends (Weeks 3–4)
**Deliverable:** the terminal stops being a single-shot REPL and becomes a coordinated agent system around news + critique.
- CrewAI integration; register agents 1–5 from §5.1 (Supervisor, Data, News & Trend, Critic, Quant/Bull-Bear).
- News & Trend agent: RSS aggregation across Indian + global sources, dedupe (MinHash), embeddings → ChromaDB, daily clustering, narrative-arc detection across sources.
- Critic agent runs on every `/analyze` output; confidence score + dissenting view appear in panel.
- Watchlist persistence in SQLite.
- TUI upgrade to Textual: tabs (Dashboard, Ticker, News, Watchlist).
- **Exit criteria:** opening the terminal at 8 AM surfaces ≥3 actionable signals you wouldn't have found by browsing — using fundamentals + news + critique only.

### Phase 2.5 — Analyst-Grade Layer (Weeks 5–7) ⭐ *new*
See §6.5 for the full spec. This is the layer that turns the terminal from "smart watchlist" into "analyst desk." Adds 8 new agents (Sentiment optional, Transcript, CEO Tracker, Ownership, Quality, Comps, Macro, Calendar) and ~15 new commands.

### Phase 3 — Bull/Bear Depth + US + Routing (Weeks 6–9)
- LangGraph migration for `/analyze` flow (cyclical critique, conditional re-fetch).
- Multi-LLM router: cheap classification → Phi-4 Mini, code/multilingual → Qwen3, synthesis → Claude, large-context summarization → NIM.
- US expansion: Finnhub for quotes/fundamentals, broader CEO list (Dimon, Fink, Pichai, Nadella).
- Probabilistic bull/bear: weight factors, surface ranges not point estimates.
- Light backtesting hooks via vectorbt.
- Optional: exo evaluation if a second device is added.

### Phase 4 — Polish, Reports, Optimization (Ongoing)
- Confidence calibration (track recommendations vs. outcomes).
- Export to Markdown report; matplotlib charts via Textual's `pyplot` widget.
- Caching layer (Redis or DiskCache) for OpenBB calls.
- Alert scheduler (Phase 4 polish, not background daemon).
- Documentation, public README if open-sourcing.

---

## 6.5 Phase 2.5 — Analyst-Grade Layer (Detailed Spec)

### 6.5.1 Why this phase exists
After Phase 2, the terminal handles the daily check-in flow. But a JP Morgan / Marcellus / Motilal Oswal analyst's first two hours of the day involve five capabilities that no amount of news + sentiment can substitute for: **transcripts, consensus revisions, ownership flows, quality scores, peer comps**. These drive ratings, target prices, and position changes. Most are free for Indian markets if you know where to look — the moat is in stitching them into a coherent surface, not in the data itself.

This phase also relocates **CEO Tracker** out of Phase 2. It's analyst-grade signal, not a starter feature.

### 6.5.2 Decision Matrix — Which Capabilities to Include

Scored 1–5 on four axes. **Include?** is the gating column.

| # | Capability | Signal value (5) | Indian data quality (5) | Build effort (1=fast, 5=slow) | Maintenance burden (1=low) | Score | Include? |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | Earnings call transcript intelligence | 5 | 4 | 4 | 3 | 17 | ✅ Phase 2.5 core |
| 2 | Consensus estimates + revisions tracking | 5 | 4 | 3 | 2 | 19 | ✅ Phase 2.5 core |
| 3 | Ownership flows (FII/DII/promoter/pledges/blocks) | 5 | 5 | 3 | 2 | 21 | ✅ Phase 2.5 core |
| 4 | Forensic / quality scores | 4 | 5 | 2 | 1 | 21 | ✅ Phase 2.5 core |
| 5 | Comps & relative valuation | 4 | 4 | 2 | 1 | 19 | ✅ Phase 2.5 core |
| 6 | CEO / leader tracker | 4 | 4 | 3 | 3 | 15 | ✅ moved here |
| 7 | Event calendar | 3 | 5 | 1 | 1 | 17 | ✅ trivial, do it |
| 8 | Macro overlay (DXY/INR/yields/Brent) | 4 | 4 | 2 | 1 | 18 | ✅ Phase 2.5 core |
| 9 | Sell-side research aggregation | 3 | 3 | 4 | 4 | 9 | ⚠️ Phase 3 |
| 10 | Multi-timeframe charts (Plotext) | 3 | 5 | 2 | 1 | 16 | ✅ as Tier-2 polish |
| 11 | DCF / SOTP modeling | 4 | 3 | 5 | 4 | 7 | ❌ Phase 4 light only |
| 12 | Alt data (LinkedIn jobs, web traffic) | 3 | 2 | 4 | 5 | 4 | ❌ skip — not free, fragile |
| 13 | Backtesting platform | 2 | n/a | 5 | 4 | -2 | ❌ non-goal |
| 14 | Quant screen library (Magic Formula, GARP, etc.) | 3 | 4 | 2 | 1 | 17 | ✅ Phase 2.5 polish |

**Cut for 2.5:** capabilities 1–8, 10, 14. **Sell-side aggregation** waits for Phase 3 (depends on having scraping infra you don't need yet). **DCF, alt-data, backtesting** stay deferred per §2 non-goals.

### 6.5.3 Component Specs

For each, the spec is: **data source(s) → ingestion approach → DuckDB schema → analysis logic → command(s) → TUI surface.**

#### A. Earnings Call Transcript Intelligence
- **Sources (priority order):** company IR pages (PDF transcripts) → Trendlyne → screener.in concall section → BSE concall recordings → NSE corporate-announcement filings → YouTube earnings call uploads (audio only → faster-whisper).
- **Ingestion:** `transcript_fetcher.py` tries each source until it finds a transcript. If only audio, run `faster-whisper` (`large-v3` quantized, ~2 GB, runs on M4 in ~1.5× real-time).
- **Schema:**
  ```sql
  transcripts (ticker, fiscal_period, source_url, full_text, fetched_at)
  transcript_sections (transcript_id, section_type {prepared|qa}, speaker, text, embedding)
  transcript_topics (transcript_id, topic, mention_count, prior_count, delta_pct)
  transcript_guidance (transcript_id, metric, lower, upper, vs_prior_status {raised|maintained|cut})
  ```
- **Analysis (Transcript Agent):**
  - Split into prepared remarks vs. Q&A.
  - Topic extraction with Qwen3 8B → normalized topic taxonomy (per-sector dictionary, e.g., for IT services: deal_pipeline, attrition, BFSI_demand, AI_revenue, hedging).
  - Mention-count deltas vs. prior 4 quarters → flag drifts ≥30%.
  - Guidance extraction (Claude, structured JSON) → compare to prior call's guidance, classify as raised/maintained/cut.
  - Q&A sentiment heuristic: count of analyst push-back markers ("can you walk us through", "we're struggling to", "to be clear", repeated re-asks).
- **Commands:**
  - `/transcript RELIANCE Q3` — display topics, guidance, Q&A friction score, key quotes
  - `/transcript-diff RELIANCE` — YoY/QoQ language drift table (top 10 gainers + 10 losers in mention count)
- **TUI:** new "Transcripts" tab. Per ticker: section navigator, topic cloud, guidance scoreboard.

#### B. Consensus Estimates + Revisions
- **Sources:** Trendlyne consensus pages (scrapeable, stable HTML), Screener.in (consensus shown on each company page), Tijori. For US: Finnhub free tier.
- **Ingestion:** daily snapshot job. Critical: **store every snapshot** — revisions are the alpha, not the level.
- **Schema:**
  ```sql
  consensus_snapshots (
    ticker, snapshot_date, fiscal_period,
    revenue_mean, revenue_high, revenue_low, n_analysts_revenue,
    ebitda_mean, eps_mean, eps_high, eps_low, n_analysts_eps,
    target_price_mean, target_price_high, target_price_low,
    rating_buy_count, rating_hold_count, rating_sell_count
  )
  earnings_actuals (ticker, fiscal_period, reported_at, revenue, ebitda, eps)
  ```
- **Analysis (Data Agent extended):**
  - Revision velocity: change in consensus EPS over rolling 30/60/90 days.
  - Revision breadth: ratio of analysts raising vs. cutting.
  - Beat/miss history: actual vs. consensus for last 8 quarters; surprise % distribution.
  - Variant perception: your `/analyze` thesis vs. consensus → flag if you're meaningfully off.
- **Commands:** `/consensus RELIANCE`, `/revisions RELIANCE 30d`, `/beats RELIANCE`
- **Why this matters:** estimate-revision momentum is one of the strongest documented short-horizon alpha signals (post-earnings drift, analyst herding).

#### C. Ownership Flows
- **Sources (all free, all Indian-edge):**
  - **NSE/BSE shareholding pattern** (quarterly XBRL filings): promoter %, FII %, DII %, public %.
  - **SEBI SAST disclosures** (real-time): substantial acquisitions, promoter buying/selling.
  - **NSE/BSE bulk & block deals** (daily): trades > 0.5% of equity (bulk) or > ₹10cr (block).
  - **AMFI monthly portfolio disclosure** (monthly, 10th of next month): mutual fund holdings per scheme.
  - **NSDL/CDSL FII flows** (daily): aggregate net FII purchases per market segment.
  - **Pledge disclosures** (NSE/BSE): promoter share pledges — major red flag when rising.
- **Schema:**
  ```sql
  ownership_snapshots (ticker, snapshot_date, promoter_pct, promoter_pledged_pct, fii_pct, dii_pct, public_pct, mf_pct)
  sast_filings (ticker, filer, filer_type, transaction_type, shares, value, filed_at)
  bulk_block_deals (ticker, trade_date, client_name, side {buy|sell}, qty, price, deal_type)
  mf_holdings (amc, scheme, ticker, snapshot_month, shares, market_value)
  fii_flows_daily (date, segment {cash|fno|debt}, gross_buy, gross_sell, net)
  ```
- **Analysis (Ownership Agent):**
  - Promoter pledge delta — alert if pledge % rises >2pp QoQ.
  - FII delta vs. own 8-quarter average.
  - "Smart money" tracker: aggregate top 10 high-conviction MFs (Mirae, Parag Parikh, Nippon, Quant, etc.) and flag when they enter/exit.
  - Bulk-deal pattern: same client name appearing across multiple tickers in a sector.
- **Commands:** `/ownership RELIANCE`, `/flows NIFTY`, `/pledge-watch` (cohort scan), `/smart-money RELIANCE`
- **TUI:** Ownership tab with stacked-bar of holding mix over time, pledge gauge (red zone at >25%).

#### D. Forensic / Quality Scores
All formula-based. No LLM needed for computation, only for explanation.

- **Piotroski F-Score (0–9):** 9 binary tests across profitability (4), leverage/liquidity (3), operating efficiency (2). Score ≥7 = high quality.
- **Beneish M-Score (8 variables):** earnings manipulation likelihood. M > -1.78 = elevated risk.
- **Altman Z-Score:** bankruptcy risk (Z < 1.81 distress, Z > 2.99 safe). Use Z'' for emerging market non-manufacturing.
- **Montier C-Score (0–6):** 6 binary "cooking the books" indicators (DSO trending up, DSI up, growth in net income vs. cash flow gap, etc.). Score ≥4 = avoid.
- **Trend metrics:** DSO (days sales outstanding) 8-quarter trend, inventory days, cash conversion cycle.
- **Schema:**
  ```sql
  quality_scores (ticker, asof_date, piotroski, beneish_m, altman_z, montier_c, dso_trend_slope, inventory_days_trend_slope)
  ```
- **Analysis (Quality Agent):**
  - Compute on every fundamentals refresh.
  - When `/quality TICKER` runs: Phi-4 Mini explains *which* Piotroski tests failed, *which* Beneish components are elevated, in plain English.
  - Cohort view (`/quality-cohort banking`): rank a sector worst-to-best to find names to avoid.
- **Why critical for India:** Yes Bank, IL&FS, DHFL, Satyam, Manpasand, Vakrangee — accounting failures missed by retail because nobody runs the numbers. The whole point of this command is "did anything in this company's accounts change in a way that should worry me?"

#### E. Comps & Relative Valuation
- **Peer set construction:** seeded curated peer-groups table per ticker (banking/IT/pharma/auto have well-known peer sets); auto-suggest peers via sector + market-cap band + ROE band as a fallback.
- **Multiples:** PE (TTM, FY1, FY2), EV/EBITDA, EV/Sales, P/B, P/Sales, dividend yield, ROE, ROCE, debt/equity.
- **Comparisons:** vs. peer median (ratio), vs. own 5-year history (z-score), vs. sector index multiple.
- **Schema:**
  ```sql
  peer_groups (ticker, peer_ticker, weight, source {curated|auto})
  valuation_snapshots (ticker, asof_date, multiple_name, value)
  ```
- **Analysis (Comps Agent):** color-code green (cheap on ≥4 of 6 multiples vs. both peer and history), red (expensive on ≥4), amber otherwise.
- **Commands:** `/comps RELIANCE`, `/sector-screen IT value`, `/historical-multiple RELIANCE pe 5y`

#### F. 3-Layer Macro Heatmap (replaces flat "Macro Overlay")

The Bloomberg-tier mistake is showing 30 macro tickers in a flat grid. The right framing — per the input.md feedback — is **three layers, each answering one question**:

- **Layer 1 — Global Risk** ("is the world risk-on or risk-off?")
- **Layer 2 — India Macro** ("is the domestic engine accelerating?")
- **Layer 3 — Market Internals** ("is the market itself confirming or fighting price?")

The heatmap renders all three side-by-side with **z-scores vs trailing 1Y** and a regime label per layer. The Regime Detector (Phase 3, see §6.6) consumes these as inputs.

##### Layer 1 — Global Risk
- **Tracks:** S&P 500 + futures, Nasdaq 100 + futures, US 2Y, US 10Y, DXY, Brent crude, WTI, gold (spot + MCX), copper, VIX, India VIX
- **Why:** for India equities, US liquidity + DXY frequently explain more of any given day's move than domestic data
- **Sources:** yfinance (`^GSPC`, `^IXIC`, `^TNX`, `^FVX`, `DX-Y.NYB`, `BZ=F`, `GC=F`, `^VIX`, `^INDIAVIX`); FRED for US rates history

##### Layer 2 — India Macro
- **Tracks:** CPI (headline + core), WPI, PMI (manufacturing + services), IIP, GST monthly collections, repo rate + repo expectations (OIS implied), India 10Y G-Sec, USD/INR, FX reserves, fiscal deficit run-rate
- **Sources:**
  - **RBI DBIE** (Database on Indian Economy) for repo, India 10Y, FX reserves — `dbie.rbi.org.in`
  - **MOSPI** for IIP + CPI — `mospi.gov.in` (XML/CSV releases)
  - **S&P Global PMI** for PMI press releases (manufacturing + services)
  - **gst.gov.in** for monthly GST collections
  - **FBIL** for benchmark bond yields
  - **CCIL** OIS curves for repo expectations

##### Layer 3 — Market Internals
- **Tracks:**
  - **Flows:** FII/DII daily net (cash + F&O), bulk/block deals
  - **Breadth:** A/D ratio, % NIFTY-500 above 50/200 DMA, new highs/lows
  - **Sector rotation:** rolling 1M/3M relative strength of each NSE sector index vs NIFTY
  - **Valuation:** NIFTY trailing PE percentile vs 10Y history, NIFTY earnings yield vs India 10Y spread, sector PE z-scores
  - **Index earnings:** NIFTY trailing EPS, blended forward EPS, revision velocity (analyst revisions index)
- **Sources:** NSE bhavcopy (constituents → A/D + breadth computed in DuckDB), NSE published Nifty PE/PB/divyld history, NSDL/CDSL FII flows, NSE sector indices

##### Schema additions
```sql
macro_series (date, layer, series_id, value, source)
macro_zscores (date, series_id, value, mean_1y, std_1y, zscore)
sector_relative_strength (date, sector_index, rs_1m, rs_3m, percentile_1y)
nifty_internals (date, ad_ratio, pct_above_50dma, pct_above_200dma,
                 nifty_pe_ttm, nifty_pe_percentile_10y, ey_minus_g10y_bps)
ticker_factor_betas (ticker, factor, beta, r_squared, window_days, last_updated)
```

**Per-ticker** factor betas (replaces the coarse sectoral table) — INFY's USD/INR beta differs from TCS's; ONGC's Brent beta differs from HPCL's. Computed quarterly via 60d rolling regression.

##### Commands
```
/heatmap                    composite — all 3 layers with regime labels
/macro-global               Layer 1 only
/macro-india                Layer 2 only
/internals                  Layer 3 only
/macro-impact RELIANCE      decompose recent ticker move into factor contributions (β-weighted)
/factor RELIANCE usd_inr    history of one ticker's exposure to one factor
```

#### F2. Banking Health (depth, since Bank Nifty alone is shallow)
The input.md author's correct push: a price index isn't health. Real banking analysis needs flows, asset quality, deposit franchise, margin trajectory.

- **Tracks (system + per-bank):**
  - **Credit growth:** YoY total bank credit (RBI weekly), sectoral splits (industry/services/retail/agri)
  - **Asset quality:** GNPA / NNPA / restructured book / SMA-2 stress
  - **Liability mix:** CASA ratio, deposit growth YoY, term-deposit costs
  - **Margin / spreads:** NIM, yield on advances, cost of funds
  - **Capital:** CET1, leverage ratio
- **Sources:** RBI weekly data on banking + monthly bulletin; bank quarterly results (already ingested via Phase 2.5.A transcripts pipeline) — extract these structured fields with the Quality agent
- **Schema:**
  ```sql
  bank_metrics (bank, period, credit_growth, gnpa, nnpa, restructured_pct,
                casa_ratio, deposit_growth, nim, cet1, yield_on_advances,
                cost_of_funds)
  banking_system (period, total_credit_growth, sectoral_credit_json,
                  system_gnpa, system_casa)
  ```
- **Commands:** `/banking-health` (system overview), `/banking-health HDFCBANK` (per-bank), `/banking-cohort` (rank universe on quality + growth + margin)
- **Why this is mandatory:** every Indian portfolio is banking-heavy. Bank Nifty as a beacon has hidden every prior banking accident (Yes Bank, IL&FS funding contagion, DHFL exposure). Surface health metrics above and the next one is harder to miss.

#### G. CEO / Leader Tracker (relocated from Phase 2)
- Per §4.5, this stays unchanged in design. Just moves into 2.5 to align with its true value tier.
- **Cut for 2.5:** 10-leader watchlist (per Q4 in §9). Add to 25 in Phase 3.

#### H. Event Calendar
- **Sources:** NSE/BSE corporate-actions feed (earnings dates, ex-div, AGM, board meetings, dividend), RBI policy schedule, Fed FOMC calendar, India Union Budget, US CPI/jobs schedule.
- **Schema:** `events (event_date, event_type, ticker_or_market, description, importance)`
- **Commands:** `/events week`, `/events RELIANCE`
- **TUI:** persistent "Next 7 Days" panel on dashboard.

#### I. Quant Screen Library (polish)
A handful of canonical screens runnable as one-liners:
- Magic Formula (Greenblatt): high ROIC + high earnings yield
- GARP: PEG < 1, EPS growth > 15%, ROE > 15%
- Dividend sustainability: yield > 3%, payout < 60%, 5Y dividend growth > 5%
- Quality at reasonable price: Piotroski ≥ 7 + PE < sector median
- Distress avoidance: Altman Z > 3 + Beneish M < -2.22

Commands: `/screen magic-formula NIFTY500`, `/screen garp banking`.

#### J. Multi-Timeframe Charts (polish)
- **Tool:** [Plotext](https://github.com/piccolomo/plotext) for in-terminal charts (no GUI), or Textual's chart widget.
- Default views: 1D / 1W / 1M / 1Y / 5Y candles + 50/200 DMA + relative strength vs. NIFTY.
- Command: `/chart RELIANCE 1y`

### 6.5.4 New DuckDB Schema (cumulative additions in 2.5)
14 new tables: `transcripts`, `transcript_sections`, `transcript_topics`, `transcript_guidance`, `consensus_snapshots`, `earnings_actuals`, `ownership_snapshots`, `sast_filings`, `bulk_block_deals`, `mf_holdings`, `fii_flows_daily`, `quality_scores`, `peer_groups`, `valuation_snapshots`, `macro_series`, `sector_macro_betas`, `events`. (Schema migrations live in `src/finterminal/data/migrations/00X_*.sql`.)

### 6.5.5 Updated Agent Count and LLM Routing
| Layer | Agents | Default LLM |
|---|---|---|
| Synthesis (Supervisor, Critic, Bull-Bear, Transcript-synthesis) | 4 | Claude Sonnet 4.6 |
| Mid-tier extraction (Data, News, Transcript-extract, CEO, Comps) | 5 | Qwen3 8B (Ollama) |
| Fast classification (Quality, Macro, Calendar, Ownership) | 4 | Phi-4 Mini |
| External retrieval (Sentiment, optional) | 1 | Grok-3-mini |

Total: **13 agents** (12 if sentiment off). Router policy stays as defined in §3.

### 6.5.6 Exit Criteria (Phase 2.5)
Tested on a 25-name Indian watchlist (banking, IT, pharma, auto, FMCG):
1. `/transcript TICKER Q3` returns within 30s if cached, ≤4 min if it has to transcribe audio.
2. `/consensus TICKER` shows estimate-revision trend over 90 days; backfilled snapshots ≥ 8 weeks deep.
3. `/ownership TICKER` shows current snapshot + ≥4 quarter deltas + last 30 days of SAST/bulk/block.
4. `/quality TICKER` returns Piotroski + Beneish + Altman + Montier with plain-English component breakdown.
5. `/comps TICKER` shows ≥6 peer companies with 6 multiples each, color-coded.
6. Across the 25-name list, at least 3 names per week surface a non-obvious flag (a topic shift, a pledge change, a quality-score deterioration, a consensus revision, an unusual block deal) that you'd not have noticed otherwise.

### 6.5.7 Phase 2.5 Risks (additions to §7)
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Trendlyne/screener HTML changes break consensus scraping | High | Medium | Dual-source (Trendlyne + Screener), schema-versioned parsers, snapshot diff alerts. Treat scraper as a known-fragile boundary; isolate behind `ConsensusSource` interface. |
| Smaller co's don't post concall transcripts | Medium | Medium | Fall back to YouTube → faster-whisper. Mark `transcript_quality = whisper` so user knows source. |
| Whisper accuracy on Indian-accented English + Hindi mixing | Medium | Low | Use `large-v3` (best for accents); accept ~5% WER; topic extraction is robust to it. |
| Forensic score false positives | Medium | Medium | Always show *which components* drive the score, not just the number. User judges, model explains. |
| AMFI portfolio data is monthly + 10-day lag | High | Low | Display `as_of_date` on every ownership panel. Don't pretend it's real-time. |

### 6.5.8 Why this layer is the actual moat
Phase 1–2 give you a smarter Bloomberg shortcut. **Phase 2.5 is what makes the terminal something a working analyst would not want to give up.** Every capability above is the answer to a specific recurring question that a real research process asks:
- *What did management actually say this quarter, and how is that different from last quarter?* → Transcripts
- *What does the street think, and is that view changing?* → Consensus + revisions
- *Is smart money accumulating or distributing? Are promoters worried?* → Ownership
- *Is anything fishy in the accounts?* → Quality
- *Is this cheap or expensive vs. peers and itself?* → Comps
- *What macro tailwind/headwind is this name actually exposed to?* → Macro

If you can answer all six in under 3 minutes per ticker, you have a real research workflow.

---

## 6.6 Phase 3 — Synthesis Layer (the actual edge over JP Morgan)

Phase 2.5 gives you analyst-grade *inputs*. **Phase 3 is what most retail tools — and most sell-side desks — do not have**: a calibrated synthesis layer with a memory of its own past calls. This is the moat. Five components.

### 6.6.1 Regime Detector
- **Input:** Layer 1 + Layer 2 z-scores from `/heatmap`, 60d trend
- **States:** `risk_on` | `risk_off` | `transition_into_risk_on` | `transition_into_risk_off` | `neutral`
- **Method:** rules-based v1 (z-score thresholds + sign of trend) → optionally a small classifier in Phase 4 if rules-based misclassifies obvious cases
- **Output:** current state + confidence + 3-line rationale ("DXY +1.5σ, US 10Y +0.8σ, INR -0.6σ → tightening global liquidity → risk_off")
- **Schema:** `regime_history (date, state, confidence, rationale_json, layer1_inputs_json, layer2_inputs_json)`
- **Command:** `/regime`, `/regime-history 2y`
- **Why mandatory:** every other agent's output should be regime-aware. A bull case in `risk_off` needs to clear a higher bar.

### 6.6.2 Scenario Engine
- **Input:** ticker fundamentals, valuation percentile, earnings revision velocity, regime state, ownership delta
- **Output:** explicit `P(bull) / P(base) / P(bear)` over 1m / 3m / 6m horizons, with per-scenario rationale and observable triggers
- **Method:** structured prompt to Claude/synthesis model with the inputs as context. Probabilities must sum to 1. Each scenario has a price-implied range from current valuation × scenario EPS × scenario multiple
- **Schema:** `scenarios (ticker, generated_at, horizon_days, p_bull, p_base, p_bear, bull_rationale, base_rationale, bear_rationale, bull_target, bear_target)`
- **Command:** `/scenarios RELIANCE 3m`
- **Distinct from `/analyze`:** `/analyze` produces narrative; `/scenarios` produces explicit weighted probabilities + price ranges suitable for sizing decisions

### 6.6.3 Signal Weighter
- **Input:** all the per-ticker signals — quality score, valuation z, revision velocity, ownership delta, transcript topic drift, factor exposure to current regime
- **Output:** composite score in [-1, +1] decomposed by factor; conviction tier (Conviction Long / Watch / Avoid / Conviction Short)
- **Default weights:** input.md author's hierarchy as priors:
  1. Global liquidity / regime fit — 25%
  2. Earnings momentum + revisions — 25%
  3. Valuation vs history — 20%
  4. Domestic macro — 10%
  5. Positioning / flows — 15%
  6. News noise — 5%
- **Schema:** `signal_scores (ticker, generated_at, composite, conviction_tier, factor_breakdown_json, weight_set)`
- **Command:** `/signal RELIANCE`, `/signal-cohort banking` (rank a sector)
- **Customizable:** `config/weights.yaml` — different weight sets for different market regimes (e.g., Buffett-tilt: heavier valuation; Momentum-tilt: heavier revisions)

### 6.6.4 Calibration Loop (the trust-building layer)
**The single capability that separates a tool from a toy.** Without this you don't know if your high-confidence calls actually pay.

- **Method:**
  1. Every `/analyze`, `/scenarios`, `/signal` writes a row to `predictions` with the ticker, prediction, confidence, horizon, and entry_price
  2. A nightly job evaluates outcomes (1m / 3m / 6m later): did the bull/bear case materialize? Did P(bull) match realized frequency?
  3. Compute Brier score, reliability diagram, calibration-by-conviction-tier
- **Schema:**
  ```sql
  predictions (id, ts, ticker, source_command, claim_type {direction|p_bull|tier},
               claim_value, confidence, horizon_days, entry_price)
  outcomes (prediction_id, evaluated_at, realized_value, score, hit)
  calibration_summary (window, brier_score, by_tier_json, by_confidence_bucket_json)
  ```
- **Surfaces:**
  - `/calibration` — Brier score, reliability diagram (ASCII), tier-by-tier hit rate
  - Footer of every `/analyze` includes "your last 50 Conviction Long calls hit 47%" so confidence is anchored in reality
- **Why JP can't do this internally:** career risk. Their analysts do not get scored individually and publicly on calibration. We can — there's no career.

### 6.6.5 Bias Auditor
A meta-agent run weekly. Examines the last 30 days of `/analyze` and `/signal` outputs for:
- **Direction bias:** what % of cases were bull vs bear? In a flat market, ≥75% one direction is suspicious
- **Sector bias:** are you over-confident on sectors you personally favor (IT? defense? PSUs?)
- **Confidence bias:** is your confidence calibrated, or are 0.7s actually 0.5s?
- **Source-discipline drift:** are `[src: ...]` tags getting sloppier?
- **Output:** weekly digest, optionally pushed via the alert daemon
- **Why this matters:** every research process drifts. Sell-side analysts hedge for legal reasons; we drift in different ways. The auditor names the drift before it costs money.

### 6.6.6 Variant-Perception Checker
Every `/analyze` invocation, before returning to the user, the Critic agent checks: "is this materially different from consensus? If not, why are we writing a note?" A non-variant analysis gets flagged in the panel header. **Concurring with consensus is not bad — but it's information you should know.**

### 6.6.7 Pair / Relative Value
A complement to single-name analysis — half of buy-side process is pair trades.
- `/pair HDFCBANK ICICIBANK` — relative valuation, fundamentals delta, factor exposure delta, recent relative-price chart, historical mean-reversion stats on the spread
- `/relative INFY it-services` — INFY's z-score on each multiple vs IT-services peer median, plus per-factor relative beta
- **Schema:** `pair_trade_views (ticker_a, ticker_b, ts, spread_zscore, fundamental_delta_json, beta_delta_json)`

### 6.6.8 Why this is the moat
Layer-by-layer:
| Capability | What it does | Why JP can't / doesn't |
|---|---|---|
| Regime Detector | Tags everything risk-on/off, makes outputs regime-aware | They have macro strategists but not integrated into single-name calls |
| Scenario Engine | Explicit P(bull/base/bear) + price ranges per ticker | Sell-side notes give point targets, not probability distributions |
| Signal Weighter + tiering | Conviction Long / Watch / Avoid + factor breakdown | They do this internally but compliance prevents publishing variant tiers |
| Calibration Loop | Tracks own predictions, surfaces hit-rate over time | Career risk to score analysts publicly on calibration |
| Bias Auditor | Names systematic drift in own output | Same career-risk constraint |
| Variant-Perception Checker | Forces every note to lead with disagreement vs consensus | Sell-side hedges to keep client relationships |

The first three are table stakes for any serious tool. The last three are unique to *not* being a sell-side desk — they're the asymmetry of building this for yourself.

---

## 7. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Grok pricing or Live Search ToS changes | Medium | Low | Sentiment is feature-flagged off — terminal works without it. `SentimentSource` interface lets you swap to StockTwits or skip entirely. |
| Grok returns black-box / non-reproducible results | Medium | Medium | Always log Grok's full response + cited post URLs into DuckDB on every call → builds an audit trail and a backtestable archive. |
| Indian data quality (NSE unofficial APIs flaky) | High | Medium | Cache aggressively; Finnhub India fallback; explicit `data_freshness` field in every panel. |
| LLM hallucinations on numerics | High | High | Hard rule: numbers only from DuckDB rows, never the LLM's memory. Critic agent checks for unsourced numbers. |
| Local model too slow for interactive feel | Medium | Medium | Phi-4 Mini for fast-path; NVIDIA NIM cloud burst; precompute embeddings overnight. |
| Scope creep (geospatial, options, mobile) | High | High | Non-goals locked in §2. Anything not on the roadmap goes to a `BACKLOG.md`. |
| YouTube transcript ToS | Medium | Low | Use official Data API for metadata; only download where TOS permits; faster-whisper on local audio for podcasts via RSS. |
| Claude API cost runaway | Medium | Medium | Token budget per command; route 70%+ traffic to local; cache analyses for 4h per ticker. |

---

## 8. Cost Estimate (Monthly, Phase 2 steady state)

| Item | Cost | Notes |
|---|---:|---|
| Claude API (Sonnet 4.6) | $30–90 | Higher in 2.5: more synthesis (transcripts, comps, ownership narratives) |
| **Grok API (sentiment, optional)** | **$0 / $5–10 / $50–95** | Off / hourly market sweep / hourly per-ticker |
| Finnhub Free | $0 | US fundamentals |
| Trendlyne / Screener / NSE / BSE / SEBI / AMFI | $0 | All scraping public data; respect rate limits |
| NewsAPI Developer | $0 | Fallback only |
| OpenBB | $0 | OSS |
| YouTube Data API | $0 | Within free quota for ~10 leaders |
| NVIDIA NIM | $0 | Free tier sufficient for burst |
| Whisper compute (local) | $0 | Runs on M4 Air; ~1.5× real-time |
| **Phase 2 floor (no 2.5 yet)** | **~$20–60** |  |
| **Phase 2.5 floor (sentiment OFF)** | **~$30–90** | Fully featured analyst terminal sans X |
| **Phase 2.5, sentiment light** | **~$35–100** | Hourly market-wide sweep |
| **Phase 2.5, sentiment heavy** | **~$80–185** | Per-ticker hourly across 25-name watchlist |

---

## 9. Open Questions (resolve before Phase 1 kickoff)

1. ~~**X API budget:**~~ **Resolved 2026-04-27:** swap X API for **Grok Live Search**, treat the entire sentiment module as **optional** behind `SENTIMENT_ENABLED`. Phase 2.0 ships with sentiment OFF; Phase 2.5 turns it on.
2. **Grok cadence (when enabled):** hourly market-wide sweep (~$5/mo) or per-ticker hourly across the watchlist (~$95/mo)? Decide at Phase 2.5 cut, after measuring Phase 2.0 signal quality.
3. **Brokerage view-only API:** integrate Zerodha Kite read-only for portfolio overlay, or stay symbol-list-only?
4. **CEO list:** which 10 leaders for the Phase-2 cut? Suggested: Jensen Huang, Jamie Dimon, Larry Fink, Satya Nadella, Sundar Pichai, Mukesh Ambani, N. Chandrasekaran, Uday Kotak, Nithin Kamath, Sanjiv Bajaj.
5. **Time budget:** is the 1–2 / 2–3 / 3–4 week phasing in context.md realistic given day-job hours? If part-time, double it.
6. **Public artifact:** open-source the project, or private?

---

## 10. Immediate Next Actions (this week)

1. ✅ Plan written → this file.
2. **Decide on Q4 (CEO list).** Q1 already resolved (Grok, optional). 15-min decision; unblocks Phase 2 design.
3. **Bootstrap repo:**
   - `pyproject.toml` (Python 3.12, ruff, pytest)
   - `pip install openbb crewai rich textual duckdb chromadb anthropic ollama`
   - `ollama pull qwen3:8b` and `ollama pull phi4-mini`
4. **Build Phase 1 skeleton** (~2–3 hours):
   - `terminal.py` REPL with `/ticker`, `/news`, `/quit`
   - DuckDB schema + first OpenBB fetch wired into a Rich panel
5. **Wire `/analyze RELIANCE` end-to-end** with Claude as the only LLM (no agents yet) — validate the API loop, prompt frame, citation discipline.
6. **Write `BACKLOG.md`** for everything that gets cut along the way.

---

## Appendix A — Why these matrices and not others?

I deliberately did not score:
- **Cloud vs. on-prem:** the M4 Air constraint pre-decides this.
- **Python vs. Rust/Go:** ecosystem (OpenBB, CrewAI, Whisper) makes Python the only sensible choice at MVP.
- **Vector DB choice (Chroma vs. LanceDB vs. Qdrant):** all three work; defaulting to ChromaDB until volume forces an upgrade.

## Appendix B — Files to create in Phase 1

```
finterminal/
├── pyproject.toml
├── PLAN.md                 ← this file
├── BACKLOG.md
├── README.md
├── .env.example            (ANTHROPIC_API_KEY, X_API_KEY, ...)
├── src/finterminal/
│   ├── __init__.py
│   ├── terminal.py         (entrypoint, command parser)
│   ├── ui/
│   │   ├── panels.py
│   │   └── layout.py
│   ├── data/
│   │   ├── openbb_client.py
│   │   ├── nse.py
│   │   └── duckdb_store.py
│   ├── agents/             (Phase 2)
│   ├── llm/                   (see §3.1 — model abstraction)
│   │   ├── base.py            (LLMProvider protocol, Message, Completion)
│   │   ├── registry.py        (loads models.yaml)
│   │   ├── router.py          (loads agents.yaml, resolves agent→provider)
│   │   ├── budget.py          (cost tracking, BudgetGuard)
│   │   ├── cache.py           (response cache by model+prompt-hash)
│   │   └── providers/
│   │       ├── anthropic.py
│   │       ├── ollama.py
│   │       ├── xai.py         (Phase 2.5, optional)
│   │       ├── openai_compat.py (NIM / LM Studio / OpenRouter / Together)
│   │       └── null.py
│   ├── ../../config/
│   │   ├── models.yaml        (model registry — edit to add models)
│   │   └── agents.yaml        (agent → model mapping — edit to swap)
│   ├── sentiment/             (Phase 2.5, optional — entire dir gated by SENTIMENT_ENABLED)
│   │   ├── source.py          (SentimentSource interface)
│   │   ├── grok_source.py
│   │   └── store.py
│   ├── transcripts/           (Phase 2.5)
│   │   ├── fetcher.py         (multi-source: IR / Trendlyne / screener / NSE / YouTube)
│   │   ├── whisper_runner.py
│   │   ├── topic_extractor.py
│   │   ├── guidance_extractor.py
│   │   └── diff.py            (YoY / QoQ language drift)
│   ├── consensus/             (Phase 2.5)
│   │   ├── trendlyne_source.py
│   │   ├── screener_source.py
│   │   └── revisions.py
│   ├── ownership/             (Phase 2.5)
│   │   ├── shareholding.py    (NSE/BSE quarterly)
│   │   ├── sast.py            (SEBI real-time)
│   │   ├── bulk_block.py
│   │   ├── amfi.py            (mutual fund holdings)
│   │   └── flows.py           (FII/DII aggregate)
│   ├── quality/               (Phase 2.5)
│   │   ├── piotroski.py
│   │   ├── beneish.py
│   │   ├── altman.py
│   │   ├── montier.py
│   │   └── trends.py          (DSO, inventory days)
│   ├── comps/                 (Phase 2.5)
│   │   ├── peer_groups.py
│   │   ├── multiples.py
│   │   └── relative.py        (z-scores vs peer + own history)
│   ├── macro/                 (Phase 2.5)
│   │   ├── series.py
│   │   └── betas.py           (sector beta computation)
│   ├── ceo/                   (Phase 2.5, moved from Phase 2)
│   │   ├── youtube_source.py
│   │   ├── filings_source.py
│   │   └── theme_extractor.py
│   ├── calendar/              (Phase 2.5)
│   │   └── events.py
│   ├── screens/               (Phase 2.5 polish)
│   │   ├── magic_formula.py
│   │   ├── garp.py
│   │   ├── dividend.py
│   │   ├── qarp.py
│   │   └── distress.py
│   ├── charts/                (Phase 2.5 polish)
│   │   └── plotext_charts.py
│   └── prompts/
│       ├── supervisor.md
│       ├── critic.md
│       └── analyst.md
└── tests/
```
