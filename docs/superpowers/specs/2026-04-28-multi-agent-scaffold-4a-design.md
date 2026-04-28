# Multi-Agent Scaffold (4a) — Design Spec

**Status:** Draft — awaiting user approval before plan writing
**Date:** 2026-04-28
**Source:** Brainstorm session 2026-04-28 (user + Claude)
**Replaces parts of:** [[ADR-002 CrewAI then LangGraph]] (for Phase 2 only — Phase 3 LangGraph migration unchanged)
**New ADR required:** ADR-013 — Hand-rolled async orchestration for Phase 2

---

## 1. Problem & Goals

### Why this work exists
Phase 1 ships `/analyze TICKER` as a single LLM call: deterministic Python fetches OpenBB + RSS + fundamentals, builds a context block, calls one model with `analyst.md`, parses 7 sections, persists to DuckDB. There is no adversarial check on the output — `[src: ...]` discipline is self-policed by the analyst, confidence is unaudited, and weak bear cases ship unchallenged.

Phase 2's first sub-deliverable (4a in the brainstorm decomposition) splits the monolith into a multi-agent flow with a Critic that runs on every analysis.

### Success bar (selected option B from brainstorm Q1)
- `/analyze TICKER` produces the **same Analyst-side output** as today (all 7 sections, same shape, same persistence)
- The panel **gains a Critic block**: verdict (`ACCEPT` / `REVISE` / `REJECT`), top issues, missing-data flags, adjusted confidence
- **No revise loop.** Critic dissent is shown but does not trigger an Analyst rerun. (That belongs in the Phase 3 LangGraph migration per ADR-002's documented trigger.)
- **No regression** in any other command (`/help`, `/ticker`, `/news`, `/watch`)

### Non-goals (explicitly out of scope for 4a)
| Out of scope | Why | Lives in |
|---|---|---|
| Bull-Bear as a separate agent | analyst.md v2 already produces both | Already done |
| LLM-driven Supervisor delegation | No freeform queries — every command has a fixed flow | Possibly never; revisit Phase 3 |
| News & Trend agent + `/trends` | Different command, different flow | 4b (separate spec) |
| Critic re-fetch / Analyst rerun on REVISE | Cyclical critique = LangGraph value-prop | Phase 3 |
| Watchlist persistence | Already shipped in Phase 1 | n/a |
| Textual TUI migration | Orthogonal, large, deferrable | 4d (deferred) |

---

## 2. Architectural Decisions

### 2.1 ADR-013 (new) — Hand-rolled async, not CrewAI

ADR-002 picked CrewAI for Phase 2. Three of its inputs no longer hold:

| ADR-002 assumption | Current reality |
|---|---|
| 5 agents with LLM-driven delegation | 3 agents, deterministic per-command routing |
| Bull-Bear is a separate agent | analyst.md v2 absorbed it |
| Critic re-fetch loop in Phase 2 | Deferred to LangGraph (ADR-002's own migration trigger) |

The remaining `/analyze` flow is a 3-step linear DAG with no conditional routing, no delegation, no cycles. CrewAI's value-props (Agent/Task abstraction, native delegation, multi-process parallelism) don't fire. ADR-002's Phase 3 LangGraph migration plan is **unchanged** — we just skip the CrewAI middle layer.

ADR-013 will be authored alongside the implementation PR.

### 2.2 Three agents (selected option A from brainstorm Q2)
- **Data** — deterministic Python; *no LLM*. Owns OpenBB + RSS + fundamentals fetch, DuckDB upserts, context-block + source-dossier construction.
- **Analyst** — LLM. Loads `prompts/analyst.md`. Produces 7 structured sections (today's behavior).
- **Critic** — LLM. Loads `prompts/critic.md`. Produces `Issues / Missing Data / Confidence Adjustment / Verdict`.
- **Orchestrator** — Python coroutine in `agents/analyze_flow.py`. Not an LLM. Composes the three agents and assembles the panel.

### 2.3 Agent protocol baked in now (selected option B from brainstorm Q4)
A typed `Agent` Protocol + `AgentRegistry` ship with 4a so Phase 2.5 agents (transcript-extract, ownership, quality, comps, macro) drop in as one file each. Detailed in §4.

### 2.4 LLM tier policy (cloud vs local)
| Workload class | Default model class | Rationale |
|---|---|---|
| **Judgment** — form a thesis, find flaws, make variant claims | Cloud (Anthropic / OpenAI premium tier) | 8B-class local models miss this bar |
| **Transformation** — extract, summarize, classify, format | Local (Ollama: `qwen3:8b`, `phi4-mini`) | Free, fast, accuracy is sufficient |

**Inside 4a, both LLM agents (Analyst, Critic) are judgment-class → cloud.** Ollama earns its keep starting in 4b (News summarization) and Phase 2.5 (Transcript stage-1 extract, Ownership/Quality/Comps narration, CEO Tracker extracts).

The `LLMProvider.complete()` interface gains an optional `cache_system: bool = False` kwarg as a *hint*. Anthropic provider sets `cache_control: {type: ephemeral}`; OpenAI provider relies on its automatic prefix caching; Ollama provider silently no-ops the kwarg. **Switching any agent's model remains a one-line `agents.yaml` edit.**

---

## 3. File Layout

```
finterminal/src/finterminal/
├── agents/
│   ├── __init__.py
│   ├── base.py             ← NEW. Agent protocol + AgentContext + AgentResult + AgentRegistry. ~80 LoC.
│   ├── data.py             ← NEW. Deterministic Data agent. Extracted from supervisor.py.
│   ├── analyst.py          ← RENAME of current supervisor.py (LLM call + parse_analysis only).
│   │                          analyze_ticker() leaves; moves into analyze_flow.
│   ├── critic.py           ← NEW. LLM agent. Loads critic.md + parse_critique().
│   └── analyze_flow.py     ← NEW. Orchestrator coroutine for /analyze. ~100 LoC.
│
├── prompts/                  unchanged on disk (analyst.md, critic.md, supervisor.md exist).
├── data/                     unchanged. duckdb_store.py gains critique persistence + recent_analysis().
├── llm/                      unchanged interface. complete() gains optional cache_system kwarg.
├── ui/
│   ├── panels.py           ← extend analysis_panel() with optional critic_block parameter.
│   └── ...
└── commands.py             ← _cmd_analyze imports from agents.analyze_flow, not agents.supervisor.
                              Gains a single optional flag: --fresh.

config/
├── agents.yaml             ← rename `supervisor:` → `analyst:`. No other changes.
└── models.yaml               unchanged.
```

The current `agents/supervisor.py` does **not** survive 4a — its responsibilities split cleanly:
- Fetch logic (~lines 99–125) → `agents/data.py`
- LLM call + `parse_analysis()` (~lines 28–96 + 134–145) → `agents/analyst.py`
- Persistence + assembly (~lines 146–165) → `agents/analyze_flow.py`

`prompts/supervisor.md` becomes obsolete with the rename and is removed (the orchestrator has no prompt).

---

## 4. Agent Protocol

Defined in `agents/base.py`:

```python
from typing import Any, Protocol, runtime_checkable
from dataclasses import dataclass, field
import duckdb

@dataclass
class AgentContext:
    """Per-call payload threaded through agents."""
    ticker: str
    conn: duckdb.DuckDBPyConnection
    prior: dict[str, Any] = field(default_factory=dict)  # {"data": ..., "analyst": ...}

@dataclass
class AgentResult:
    """Uniform return shape across agents. ok=False means the agent's job failed cleanly."""
    ok: bool
    payload: Any = None              # agent-specific; documented per agent
    error: str | None = None         # one-line reason when ok=False
    model: str | None = None         # which model was used (None for deterministic agents)
    tokens_in: int = 0
    tokens_out: int = 0

@runtime_checkable
class Agent(Protocol):
    name: str            # "data" | "analyst" | "critic" | future: "news" | "ownership" | ...
    is_llm: bool         # informs orchestrator about cost/retry behaviour
    async def run(self, ctx: AgentContext) -> AgentResult: ...

class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.name in self._agents:
            raise ValueError(f"agent already registered: {agent.name}")
        self._agents[agent.name] = agent

    def get(self, name: str) -> Agent:
        if name not in self._agents:
            raise KeyError(f"agent not registered: {name}")
        return self._agents[name]
```

**Registry construction.** The registry is built lazily inside `analyze_flow.run_analyze()` for now (one helper `_build_default_registry()`). Cheap to construct; we don't pay for unused agents in non-`/analyze` commands. When 4b adds `news_flow`, it builds its own registry the same way. Refactor to a global once we have ≥3 flows sharing identical registry contents.

**Adding a future agent (illustrative — not part of 4a):**

```python
# agents/ownership.py — Phase 2.5, NOT shipped in 4a
class OwnershipAgent:
    name = "ownership"
    is_llm = True
    async def run(self, ctx: AgentContext) -> AgentResult:
        # 1. fetch shareholding deltas (deterministic)
        # 2. format prompt + call self via router.for_agent("ownership")
        # 3. parse + return AgentResult(ok=True, payload={...})
```

That is the entire surface area for a new agent. No framework gymnastics.

---

## 5. Data Flow

```
/analyze RELIANCE [--fresh]

┌──────────────────────────────────────────────────────────────────┐
│ analyze_flow.run_analyze(ticker, conn, *, fresh=False)           │
└────────────┬─────────────────────────────────────────────────────┘
             │
             │ (lever 4) Result-cache check
             │   if not fresh:
             │     row = duckdb_store.recent_analysis(conn, ticker, ttl_s=300)
             │     if row: return row   # STOP — 0 LLM tokens
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ Data agent (no LLM)                                              │
│   asyncio.gather(                                                │
│     fetch_quote(ticker),         ← parallelized; today is serial │
│     fetch_fundamentals(ticker),                                  │
│     fetch_news(ticker, limit=10))                                │
│   upsert all to DuckDB                                           │
│   build context_block      (full, for Analyst — same as today)   │
│   build source_dossier     (slim, for Critic — see §6 lever 1)   │
│   return AgentResult(ok=True, payload={                          │
│     quote, fundamentals, news,                                   │
│     context_block, source_dossier})                              │
└────────────┬─────────────────────────────────────────────────────┘
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ Analyst agent (LLM, via router.for_agent("analyst"))             │
│   system: analyst.md   [cache_system=True — lever 2]             │
│   user:   context_block + "Produce the analysis per …"           │
│   max_tokens: 2000  (today's value, unchanged)                   │
│   parse_analysis() → 7 sections                                  │
│   return AgentResult(ok=True, payload=parsed)                    │
│                                                                  │
│   On primary failure: router.fallback_chain("analyst") iterates. │
│   On all-fallback failure: AgentResult(ok=False, error=...)      │
│     → orchestrator raises AnalysisError (cannot degrade further) │
└────────────┬─────────────────────────────────────────────────────┘
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ Critic agent (LLM, with retry-then-degrade — see §7)             │
│   system: critic.md    [cache_system=True — lever 2]             │
│   user:   analyst.payload + source_dossier                       │
│           NOT the full context_block (lever 1)                   │
│   max_tokens: 500   (lever 3 — cap critic verbosity)             │
│   parse_critique() → {issues, missing, conf_adj, verdict}        │
│                                                                  │
│   On primary failure: try fallback_chain("critic") once.         │
│   On retry-fail or parse-fail: return AgentResult(ok=False).     │
│     Orchestrator records degraded=True, renders without panel.   │
└────────────┬─────────────────────────────────────────────────────┘
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ Orchestrator: assemble + persist                                 │
│   INSERT analyses row     (same shape as today + critic ref)     │
│   INSERT critiques row    (FK to analyses.id; degraded flag)     │
│   build AnalysisResult for ui.panels.analysis_panel              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Token Economy (4 levers)

### Lever 1 — Compact source dossier for Critic
The Analyst gets the full context block (today's behavior, unchanged). The Critic gets a structured one-line-per-source compact form derived from the same data. Saves ~40% of Critic input tokens. Format:

```
SOURCES AVAILABLE TO THE ANALYST:
[QUOTE]      RELIANCE  ₹2945.50  +1.2%   2026-04-28 15:30 IST  (provider: openbb/yfinance)
[FUND-PE]    23.4   (TTM)
[FUND-ROE]   9.1%
[FUND-DEBT]  ₹2.8L cr
[NEWS-1]     "Reliance Q4 net profit up 8%; refining margins improve"  Moneycontrol  2026-04-26
[NEWS-2]     "Jio user adds slow to 3.4M in Q4"                        Livemint      2026-04-25
[NEWS-3]     "RIL board approves ₹1.6L cr capex for new energy"        ET            2026-04-24
...

VERIFY: every numeric or qualitative claim in the analyst's output should map
to one of the [...] tags above. Flag any that does not.
```

Building this is `data/_dossier.py::build_source_dossier(quote, fundamentals, news) -> str` — a pure function over the structures already produced by today's fetchers.

### Lever 2 — Anthropic prompt caching on system prompts
Both `analyst.md` (~1500 tok) and `critic.md` (~400 tok) are stable. `LLMProvider.complete()` gains an optional `cache_system: bool = False` kwarg. The Anthropic provider passes `cache_control: {"type": "ephemeral"}` on the system block. OpenAI's automatic prefix caching kicks in for prompts ≥1024 tokens with stable prefixes — no flag needed. Ollama provider ignores the kwarg.

5-minute TTL on Anthropic's side. First call of the day pays full system-prompt cost; calls within 5 min pay ~10%.

### Lever 3 — Cap Critic `max_tokens` at 500
`critic.md` output is structured + short by spec (Issues / Missing / Confidence / Verdict). Hard cap prevents over-explaining.

### Lever 4 — 5-minute result cache on `/analyze TICKER`
A new method on `duckdb_store`:

```python
def recent_analysis(conn, ticker: str, ttl_s: int) -> AnalysisResult | None:
    """Return the most recent analyses row for this ticker if still within TTL.
    Joins critiques table to rehydrate the Critic block."""
```

Default TTL: 300 seconds. The `--fresh` flag bypasses. Hardcoded constant in `analyze_flow.py` for v1; promote to `config/system.yaml` if a second flow needs the same knob.

### Projected cost per `/analyze` call
| Scenario | Today (Phase 1) | 4a (this spec) | Δ |
|---|---|---|---|
| First call (cold) | ~4500 tok | ~5500 tok | **+22%** |
| Same ticker within 5 min | ~4500 tok | **0 tok** (cache hit) | **−100%** |
| Different ticker within 5 min | ~4500 tok | ~3500 tok (system prompts cached) | **−22%** |

The +22% on a cold call buys: visible Critic dissent, adjusted confidence, source-discipline enforcement, and persisted critic rows for future Calibration Loop (Phase 3). **No call ever exceeds today's cost without the user gaining the Critic.**

---

## 7. Failure Semantics

| Failure point | What happens | User-visible |
|---|---|---|
| Quote fetch fails | `/analyze` raises (today's behavior — quote is required) | Error panel |
| Fundamentals fetch fails | Proceed without; warning logged | Panel without fundamentals (today's behavior) |
| News fetch fails | Proceed without; warning logged | Panel without news (today's behavior) |
| Analyst LLM fails on primary | `router.fallback_chain("analyst")` retries on each fallback | Transparent on success |
| Analyst LLM fails on every fallback | `/analyze` raises `AnalysisError` | Error panel — same as today |
| Critic LLM fails on primary | One retry on `claude-opus-4-7` (per agents.yaml fallback) | Transparent on success |
| Critic fails on retry too | Persist `critiques` row with `degraded=True`, `error=<reason>`. Render panel **identical to today** + small "Critic unavailable: <reason>" badge | Today's panel + badge |
| Critic returns malformed text (no parseable verdict) | Same as Critic-fails-on-retry: degrade, badge, persist with `error="parse failed"` and full `raw_text` | Today's panel + badge |

**Guarantee:** if the Critic completely vanishes — flake, malformed output, network outage — the user sees exactly today's `/analyze` panel plus a one-line badge. **No functionality is removable by Critic failure.**

---

## 8. Persistence Schema

Additive only. No changes to existing tables.

```sql
-- Existing `analyses` table is unchanged.
-- (For reference, today: id, ticker, bull_case, bear_case, confidence, sources_json, created_at)

CREATE TABLE IF NOT EXISTS critiques (
    id              INTEGER PRIMARY KEY,
    analysis_id     INTEGER NOT NULL REFERENCES analyses(id),
    verdict         TEXT,           -- 'ACCEPT' | 'REVISE' | 'REJECT' | NULL when degraded
    issues_md       TEXT,           -- raw markdown of Issues section
    missing_md      TEXT,           -- raw markdown of Missing Data section
    confidence_adj  REAL,           -- recommended adjusted confidence
    raw_text        TEXT,           -- full critic LLM output for forensics
    model           TEXT,           -- which model produced it
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    degraded        BOOLEAN DEFAULT FALSE,
    error           TEXT,           -- failure reason when degraded=true
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_critiques_analysis ON critiques(analysis_id);
```

Migration: ships as a new file under `data/migrations/` following the existing convention. Ran once at startup by `duckdb_store.get_conn()` (today's pattern).

---

## 9. UI

`ui/panels.py::analysis_panel(parsed, critic=None)` — `critic` parameter is optional and defaults to None, in which case the panel renders exactly today's layout. When provided:

```
┌─ /analyze RELIANCE ───────────────────────────────────────┐
│ Variant Perception:  …                                    │
│ Bull Case:           …                                    │
│ Bear Case:           …                                    │
│ Conviction:          Conviction Long                      │
│ Confidence:          0.72  →  0.65 (critic-adjusted)      │
│ Assumptions:         …                                    │
│ What Would Change:   …                                    │
├─ Critic ──────────────────────────────────────────────────┤
│ Verdict: REVISE                                           │
│ Issues:                                                   │
│   - [HIGH] PE claim 23.4 unsourced ([FUND-PE] missing)    │
│   - [MED]  Bear case ignores GST collection slowdown      │
│ Missing data: pledge status, FII flow last 30d            │
└───────────────────────────────────────────────────────────┘
```

Degraded variant (Critic failed):

```
├─ Critic ──────────────────────────────────────────────────┤
│ Critic unavailable: timeout after 30s                     │
└───────────────────────────────────────────────────────────┘
```

Today's confidence display shows a single number; the new display shows `raw → adjusted`.

---

## 10. Testing Strategy

| Test type | Files | Purpose |
|---|---|---|
| **Unit** — `parse_analysis()` | `tests/agents/test_analyst.py` | Preserve today's parser tests verbatim |
| **Unit** — `parse_critique()` | `tests/agents/test_critic.py` | Mirror analyst-parser test pattern: well-formed → all 4 fields, malformed → ok=False |
| **Unit** — Data agent | `tests/agents/test_data.py` | With mocked `openbb_client` + RSS, verify dossier shape and DuckDB upserts |
| **Unit** — `AgentRegistry` | `tests/agents/test_base.py` | register/get/duplicate-name |
| **Integration** — full flow | `tests/agents/test_analyze_flow.py` | All LLM calls mocked. Asserts: (a) parsed analysis matches the snapshot, (b) critiques row inserted, (c) panel renders with critic block |
| **Non-regression** | `tests/agents/test_analyze_flow.py::test_analyst_fields_preserved` | **Snapshot test:** for a fixed ticker with mocked fetchers + mocked Analyst LLM, the new flow's analyst-side AnalysisResult fields are byte-identical to a stored snapshot. **This is the "don't remove functionality" guarantee, executable.** The baseline snapshot is captured **before any refactor begins** by running the current `analyze_ticker()` against the same mocks and saving the parsed dict to `tests/agents/fixtures/analyst_baseline_RELIANCE.json`. This baseline-capture step is the very first commit in the rollout (a step 0 prepended to the table in §11). |
| **Failure modes** | `tests/agents/test_analyze_flow_failures.py` | Critic timeout → degraded panel + critiques row with degraded=true. Critic malformed → same. Analyst total failure → AnalysisError. Quote fetch failure → AnalysisError. Fundamentals/news failure → proceed without. |

CI runs all tests on every commit. Non-regression test is the gate before the rename PR merges.

---

## 11. Rollout

Single PR, ordered commits. Tests stay green between each.

| # | Commit | What |
|---|---|---|
| 0 | `tests/agents/fixtures/analyst_baseline_RELIANCE.json` | Capture non-regression snapshot of today's `analyze_ticker()` parsed output for `RELIANCE` (and one or two other tickers covering edge cases — IT-services + a small-cap with no fundamentals). Mocked-LLM run; deterministic. **Must precede any code reorganisation.** |
| 1 | `agents/base.py` + tests | Introduce Agent protocol + Registry. No callers. |
| 2 | `agents/data.py` + tests | Extract fetch logic from supervisor.py into Data agent. supervisor.py still imports it back temporarily for compatibility. |
| 3 | `agents/critic.py` + `parse_critique()` + tests | New agent + parser. No caller yet. |
| 4 | `data/migrations/NNNN_critiques.sql` + `recent_analysis()` | Schema + cache-lookup helper. |
| 5 | `agents/analyst.py` + `agents/analyze_flow.py` | Create `analyst.py` with the LLM call + `parse_analysis()` extracted from `supervisor.py`. Create `analyze_flow.py` orchestrator. `supervisor.py` is left in place but no longer imported by `commands.py` after step 6 — deletion happens in step 6 once it is fully orphaned. |
| 6 | `commands.py` + `agents.yaml` + `ui/panels.py` + cleanup | Rewire `_cmd_analyze` to use `analyze_flow`. Rename `supervisor:` → `analyst:` in agents.yaml. Extend `analysis_panel()` for critic block. Add `--fresh` flag parsing. **Delete the now-orphaned** `agents/supervisor.py` and `prompts/supervisor.md`. |
| 7 | Vault docs | Write [[ADR-013 Hand-rolled Async over CrewAI for Phase 2]]. Update [[Phase 2 - Multi-Agent Foundation]] (4a status: shipped). Update [[01 - Architecture/Agent System]]. New build-log entry. Refresh `agents.yaml` comments. |

**No external API changes.** Only internal renames. Users see one new badge in `/analyze` panels and a `--fresh` flag in `/help`.

**Rollback path:** revert the PR. Schema is purely additive (the `critiques` table is left in place but unused — no harm).

---

## 12. Open Questions Deferred to Implementation

These are resolved during plan/implementation, not blockers for the spec:

- **Q-4a-1:** `--fresh` flag CLI parsing. Today's `_require_one()` errors on extra args. Smallest change: in `_cmd_analyze`, scan args for `--fresh`, remove it from the list, then call `_require_one` on the rest. Keep it that simple unless we discover another flag is also needed.
- **Q-4a-2:** Result-cache TTL — hardcode 300s in v1 vs. config knob in `system.yaml`. Default to hardcode; promote when 4b needs the same constant.
- **Q-4a-3:** Future `/critique-redo TICKER` (re-run Critic on a stored analysis without refetching data). Out of scope for 4a; logged for the Phase 2 backlog.

## 13. Cross-links

- New ADR: ADR-013 — Hand-rolled async over CrewAI for Phase 2
- Supersedes: parts of [[02 - Decisions/ADR-002 CrewAI then LangGraph]] (Phase 2 framework choice only — Phase 3 LangGraph migration is unchanged)
- Implements: first sub-deliverable of [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- Affects: [[01 - Architecture/Agent System]], [[04 - Code Map/prompts]] (supervisor.md removal note)
- Sister specs (future): 4b News & Trend agent, 4c Watchlist (already shipped), 4d Textual TUI migration
- Brainstorm session: 2026-04-28
