# Multi-Agent Scaffold (4a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic `/analyze` LLM call into Data + Analyst + Critic agents coordinated by a hand-rolled async orchestrator, with token-economy levers, an Agent protocol that scales to Phase 2.5 agents, and a non-regression guarantee that today's analyst-side output is preserved byte-identical.

**Architecture:** A `agents/base.py` typed Protocol + Registry; a deterministic Data agent that parallelizes fetches and emits both a full context block (for Analyst) and a compact source dossier (for Critic); LLM-backed Analyst (renamed from `supervisor.py`) and Critic agents; an `analyze_flow.py` coroutine that composes them with retry-then-degrade Critic semantics, a 5-min result cache, and Anthropic prompt caching. Schema gains a `critiques` table + a nullable `payload_json` column on `analyses`.

**Tech Stack:** Python 3.13, `uv`, pytest 9.x, DuckDB 1.5+, Anthropic SDK ≥0.97, OpenAI SDK ≥1.60, Rich 15.x.

**Spec source:** `docs/superpowers/specs/2026-04-28-multi-agent-scaffold-4a-design.md`

---

## Project conventions (read before starting)

- **Project root:** `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/` — all `uv` and `pytest` commands run from here unless noted.
- **Repo root:** `/Users/ajinkyawagh/Desktop/FINTERMINAL/` — git repo lives here; vault docs live here.
- **Test runner:** `uv run pytest <path>` (uv resolves the project automatically).
- **Existing tests:** flat at `finterminal/tests/test_smoke.py`. New tests live under `finterminal/tests/agents/` (new directory + `__init__.py`).
- **Migrations:** SQL files in `finterminal/src/finterminal/data/migrations/`, named `NNN_<name>.sql`, applied once via the `_migrations` ledger table.
- **Commits:** TDD-flavored — failing test, then green, then commit. One logical change per commit.
- **Type hints:** project uses `from __future__ import annotations` everywhere — keep that header in every new module.
- **Lint:** `uv run ruff check finterminal/src finterminal/tests` should be clean before each commit.

---

## Task 0: Repo prep

**Files:**
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/.gitignore` (create if absent)

- [ ] **Step 1: Verify git is initialized**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git rev-parse --is-inside-work-tree
```

Expected: `true`. If the command errors with `not a git repository`, initialize:

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git init && git add -A && git commit -m "baseline"
```

- [ ] **Step 2: Verify the dev environment runs**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/test_smoke.py -v
```

Expected: tests pass (or some skip on missing API keys with the documented `API_KEY` message). If imports fail, run `uv sync` first.

- [ ] **Step 3: Create the new test package**

Create the file `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/__init__.py` (empty file).

- [ ] **Step 4: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add -A && git commit -m "chore: add tests/agents package for multi-agent scaffold (4a)"
```

---

## Task 1: Capture the non-regression baseline

**Why first:** the non-regression test compares post-refactor analyst output to a snapshot. The snapshot must be captured **before** any agent code moves — otherwise the test is trivially green against itself.

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/fixtures/__init__.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/fixtures/baseline_capture.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/fixtures/analyst_baseline_RELIANCE.json`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_baseline_present.py`

- [ ] **Step 1: Write the script that captures the baseline**

Write `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/fixtures/baseline_capture.py`:

```python
"""Captures a non-regression baseline of today's parse_analysis() output.

Run via:  uv run python tests/agents/fixtures/baseline_capture.py

This script is intentionally separate from pytest. It produces a deterministic
JSON snapshot — generated *once*, before the 4a refactor begins — that future
multi-agent flow tests assert against.

If the captured shape ever needs to change (e.g., analyst.md gains an 8th
section), regenerate by re-running this script and committing the new JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

from finterminal.agents.supervisor import parse_analysis

# A representative LLM-style response. Mirrors analyst.md v2's seven-section format.
SAMPLE_RESPONSE = """## Variant Perception
Consensus is broadly bullish on capex pipeline; we are skeptical because new-energy capex has not yet shown unit-economics that justify the multiple. [src: news[2]]

## Bull Case
- Refining margins improving on lighter crude slate [src: news[0]]
- Jio + retail subscriber base provides predictable cashflow [src: fundamentals.revenue_ttm]
- Net debt has come down vs FY23 peak [src: fundamentals.debt_to_equity]

## Bear Case
- New-energy capex is binary and 5+ years to monetization [src: news[2]]
- Telecom ARPU growth slowing; Jio user adds decelerated [src: news[1]]
- Conglomerate discount likely persists with no demerger catalyst

## Conviction
Watch Long

## Confidence
0.55

## Assumptions
- Crude stays in $70-95 range
- No regulatory action on telecom tariff hikes
- Capex schedule holds within ±15% of stated plan

## What Would Change My Mind
- A 20%+ Jio ARPU step-up announcement (bullish)
- Promoter pledge increase >10% of holdings (bearish)
- Material delay (>12mo) on new-energy first-revenue date (bearish)
"""


def main() -> None:
    parsed = parse_analysis(SAMPLE_RESPONSE)
    out = {
        "ticker": "RELIANCE.NS",
        "raw_response": SAMPLE_RESPONSE,
        "parsed": parsed,
    }
    target = Path(__file__).parent / "analyst_baseline_RELIANCE.json"
    target.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it once to generate the baseline JSON**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run python tests/agents/fixtures/baseline_capture.py
```

Expected output: `wrote .../analyst_baseline_RELIANCE.json`

Verify the file exists:

```bash
ls -la /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/fixtures/analyst_baseline_RELIANCE.json
```

- [ ] **Step 3: Write a sanity test that the baseline file is present and well-formed**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_baseline_present.py`:

```python
"""Sanity check: the non-regression baseline JSON exists and contains all 7 analyst fields."""
from __future__ import annotations

import json
from pathlib import Path


_BASELINE = Path(__file__).parent / "fixtures" / "analyst_baseline_RELIANCE.json"

_REQUIRED_PARSED_KEYS = {
    "variant_perception",
    "bull_case",
    "bear_case",
    "conviction",
    "confidence",
    "assumptions",
    "what_would_change",
}


def test_baseline_file_exists():
    assert _BASELINE.exists(), (
        f"Baseline missing: {_BASELINE}. "
        "Run: uv run python tests/agents/fixtures/baseline_capture.py"
    )


def test_baseline_has_all_parsed_fields():
    data = json.loads(_BASELINE.read_text())
    parsed = data["parsed"]
    missing = _REQUIRED_PARSED_KEYS - set(parsed.keys())
    assert not missing, f"baseline missing parsed keys: {missing}"


def test_baseline_confidence_is_in_range():
    data = json.loads(_BASELINE.read_text())
    conf = data["parsed"]["confidence"]
    assert conf is None or 0.0 <= conf <= 1.0
```

- [ ] **Step 4: Run the sanity tests**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_baseline_present.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/tests/agents/ && git commit -m "test: capture analyst non-regression baseline before 4a refactor"
```

---

## Task 2: Agent protocol + Registry (`agents/base.py`)

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/base.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_base.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_base.py`:

```python
"""Unit tests for the Agent protocol + AgentRegistry."""
from __future__ import annotations

import pytest

from finterminal.agents.base import (
    Agent,
    AgentContext,
    AgentRegistry,
    AgentResult,
)


class _FakeAgent:
    """A minimal protocol-compliant agent used only in tests."""

    name = "fake"
    is_llm = False

    async def run(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(ok=True, payload={"got": ctx.ticker})


def test_agent_result_defaults():
    r = AgentResult(ok=True)
    assert r.ok is True
    assert r.payload is None
    assert r.error is None
    assert r.tokens_in == 0
    assert r.tokens_out == 0
    assert r.model is None


def test_agent_context_defaults():
    ctx = AgentContext(ticker="RELIANCE.NS", conn=None)  # type: ignore[arg-type]
    assert ctx.ticker == "RELIANCE.NS"
    assert ctx.prior == {}


def test_registry_register_and_get():
    reg = AgentRegistry()
    a = _FakeAgent()
    reg.register(a)
    assert reg.get("fake") is a


def test_registry_rejects_duplicates():
    reg = AgentRegistry()
    reg.register(_FakeAgent())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_FakeAgent())


def test_registry_unknown_name_raises_keyerror():
    reg = AgentRegistry()
    with pytest.raises(KeyError, match="not registered"):
        reg.get("nope")


def test_protocol_runtime_check_accepts_fake():
    """The Agent protocol is runtime_checkable so we can isinstance-test fakes in other tests."""
    a = _FakeAgent()
    assert isinstance(a, Agent)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_base.py -v
```

Expected: ImportError / ModuleNotFoundError on `finterminal.agents.base`.

- [ ] **Step 3: Implement `agents/base.py`**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/base.py`:

```python
"""Agent protocol + per-call context + uniform result type + a small registry.

Every agent (deterministic or LLM-backed) implements this Protocol. The
orchestrator (`agents/analyze_flow.py`) composes them. Future agents
(Phase 2.5: ownership, transcript, quality, comps, macro, ...) drop in
as one file each + one registry entry.

This module has zero LLM dependencies — providers are reached via
`finterminal.llm.router.Router.for_agent(name)` from inside concrete agents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import duckdb


@dataclass
class AgentContext:
    """Per-call payload threaded through agents.

    `prior` accumulates outputs from earlier-running agents in the flow,
    keyed by agent.name (e.g. {"data": <DataPayload>, "analyst": <AnalystPayload>}).
    """
    ticker: str
    conn: duckdb.DuckDBPyConnection
    prior: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Uniform return shape across agents.

    ok=False means the agent's job failed cleanly — the orchestrator decides
    whether to degrade or raise based on the agent's role.
    """
    ok: bool
    payload: Any = None
    error: str | None = None
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0


@runtime_checkable
class Agent(Protocol):
    """Agents implement this; orchestrator depends only on this surface."""
    name: str
    is_llm: bool

    async def run(self, ctx: AgentContext) -> AgentResult: ...


class AgentRegistry:
    """Tiny in-memory registry keyed by Agent.name.

    Built lazily by each flow (e.g. `analyze_flow._build_default_registry()`).
    Not a global — when 4b News flow lands, it will build its own registry the
    same way, sharing nothing.
    """

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

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_base.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/agents/base.py finterminal/tests/agents/test_base.py && git commit -m "feat(agents): add Agent protocol + AgentRegistry"
```

---

## Task 3: Thread `cache_system` kwarg through `LLMProvider.complete()`

**Why now:** Analyst and Critic both want prompt caching. Adding the kwarg through the Protocol + all 3 providers in one focused commit avoids touching providers in mid-flight tasks later.

**Files:**
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/llm/base.py`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/llm/providers/anthropic.py`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/llm/providers/openai_compat.py`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/llm/providers/ollama.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_provider_cache_kwarg.py`

- [ ] **Step 1: Write failing test for the kwarg surface**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_provider_cache_kwarg.py`:

```python
"""All 3 providers must accept the `cache_system` kwarg (Anthropic uses it; others ignore)."""
from __future__ import annotations

import inspect

from finterminal.llm.base import LLMProvider
from finterminal.llm.providers.anthropic import AnthropicProvider
from finterminal.llm.providers.ollama import OllamaProvider
from finterminal.llm.providers.openai_compat import OpenAICompatProvider


def test_protocol_complete_accepts_cache_system():
    sig = inspect.signature(LLMProvider.complete)
    assert "cache_system" in sig.parameters
    p = sig.parameters["cache_system"]
    assert p.default is False


def test_anthropic_provider_complete_accepts_cache_system():
    sig = inspect.signature(AnthropicProvider.complete)
    assert "cache_system" in sig.parameters
    assert sig.parameters["cache_system"].default is False


def test_openai_compat_provider_complete_accepts_cache_system():
    sig = inspect.signature(OpenAICompatProvider.complete)
    assert "cache_system" in sig.parameters
    assert sig.parameters["cache_system"].default is False


def test_ollama_provider_complete_accepts_cache_system():
    sig = inspect.signature(OllamaProvider.complete)
    assert "cache_system" in sig.parameters
    assert sig.parameters["cache_system"].default is False
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_provider_cache_kwarg.py -v
```

Expected: 4 failed (parameter `cache_system` not in signature).

- [ ] **Step 3: Add the kwarg to the Protocol**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/llm/base.py`, change the `LLMProvider.complete` signature:

Old (lines 61-69):
```python
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
    ) -> Completion: ...
```

New:
```python
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
        cache_system: bool = False,
    ) -> Completion: ...
```

- [ ] **Step 4: Wire `cache_system` in the Anthropic provider**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/llm/providers/anthropic.py`, change `complete`:

Old `complete` signature (lines 28-36):
```python
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
    ) -> Completion:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
```

New `complete` signature + body (replace through line 49 — the `await self._client.messages.create` block):
```python
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
        cache_system: bool = False,
    ) -> Completion:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        # Anthropic prompt caching: mark the system block as ephemeral (5min TTL).
        # https://docs.anthropic.com/claude/docs/prompt-caching
        if cache_system:
            system_param: str | list[dict] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        else:
            system_param = system

        last_err: Exception | None = None
        for attempt in range(3):
            t0 = time.monotonic()
            try:
                resp = await self._client.messages.create(
                    model=self._meta.api_id,
                    system=system_param,
                    messages=api_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
```

The rest of the file (response parsing, retry handling) is unchanged.

- [ ] **Step 5: Add the kwarg to the OpenAI-compat provider (no-op — relies on automatic prefix caching)**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/llm/providers/openai_compat.py`, change `complete` signature only:

Old (lines 68-76):
```python
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
    ) -> Completion:
```

New:
```python
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
        cache_system: bool = False,  # accepted; OpenAI auto-caches stable prefixes ≥1024 tokens
    ) -> Completion:
```

(No body changes — the kwarg is intentionally unused. OpenAI's API caches automatically on stable prefixes.)

- [ ] **Step 6: Add the kwarg to the Ollama provider (no-op — local models, no caching to wire)**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/llm/providers/ollama.py`, change `complete` signature only:

Old (lines 16-24):
```python
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
    ) -> Completion:
```

New:
```python
    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_schema: dict | None = None,
        cache_system: bool = False,  # accepted; Ollama has no remote cache to mark
    ) -> Completion:
```

- [ ] **Step 7: Run tests**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_provider_cache_kwarg.py tests/test_smoke.py -v
```

Expected: 4 new tests + all pre-existing smoke tests pass.

- [ ] **Step 8: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/llm finterminal/tests/agents/test_provider_cache_kwarg.py && git commit -m "feat(llm): add cache_system kwarg to LLMProvider.complete (Anthropic wires; others no-op)"
```

---

## Task 4: Source dossier builder

**What:** A pure function that turns the same `(quote, fundamentals, news)` payload into a slim, line-per-source string for the Critic. Saves ~40% of Critic input tokens (lever 1).

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/_dossier.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_dossier.py`

- [ ] **Step 1: Write the failing tests**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_dossier.py`:

```python
"""Source-dossier shape tests."""
from __future__ import annotations

from finterminal.agents._dossier import build_source_dossier


_QUOTE = {
    "ticker": "RELIANCE.NS",
    "last_price": 2945.50,
    "change_pct": 1.2,
    "as_of": "2026-04-28T15:30:00+05:30",
    "provider": "yfinance",
}
_FUND = {
    "pe_ttm": 23.4,
    "roe": 0.091,
    "debt_to_equity": 0.45,
}
_NEWS = [
    {"source": "Moneycontrol", "headline": "Reliance Q4 net profit up 8%; refining margins improve",
     "published_at": "2026-04-26"},
    {"source": "Livemint", "headline": "Jio user adds slow to 3.4M in Q4",
     "published_at": "2026-04-25"},
]


def test_dossier_includes_quote_tag():
    out = build_source_dossier("RELIANCE.NS", _QUOTE, _FUND, _NEWS)
    assert "[QUOTE]" in out
    assert "RELIANCE.NS" in out
    assert "2945" in out  # price digits present


def test_dossier_includes_fundamental_tags():
    out = build_source_dossier("RELIANCE.NS", _QUOTE, _FUND, _NEWS)
    assert "[FUND-PE]" in out and "23.4" in out
    assert "[FUND-ROE]" in out
    assert "[FUND-DEBT]" in out  # debt_to_equity rendered as [FUND-DEBT]


def test_dossier_news_uses_indexed_tags():
    out = build_source_dossier("RELIANCE.NS", _QUOTE, _FUND, _NEWS)
    assert "[NEWS-1]" in out
    assert "[NEWS-2]" in out
    assert "Moneycontrol" in out
    assert "Livemint" in out


def test_dossier_handles_missing_fundamentals():
    out = build_source_dossier("RELIANCE.NS", _QUOTE, None, _NEWS)
    assert "[QUOTE]" in out
    # Fundamentals section absent or marked unavailable; must not crash:
    assert "[FUND-PE]" not in out
    assert "fundamentals unavailable" in out.lower()


def test_dossier_handles_no_news():
    out = build_source_dossier("RELIANCE.NS", _QUOTE, _FUND, [])
    assert "[NEWS-1]" not in out
    assert "no news" in out.lower()


def test_dossier_ends_with_verify_directive():
    out = build_source_dossier("RELIANCE.NS", _QUOTE, _FUND, _NEWS)
    assert "VERIFY" in out
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_dossier.py -v
```

Expected: ImportError on `finterminal.agents._dossier`.

- [ ] **Step 3: Implement the dossier builder**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/_dossier.py`:

```python
"""Compact source dossier for the Critic.

The Analyst gets a full context block (today's `ui.panels.build_context_block`).
The Critic does NOT need the full news-article bodies — it needs to verify
[src: ...] tags from the Analyst's output. A one-line-per-source compact form
saves ~40% of Critic input tokens with no loss in verification accuracy.

Output is a stable, deterministic string — feed it directly to the Critic LLM
as the user message body.
"""
from __future__ import annotations

from typing import Any


def _fmt_or_dash(v: Any, decimals: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.{decimals}f}"
    return str(v)


def _render_quote(q: dict) -> str:
    price = _fmt_or_dash(q.get("last_price"))
    chg = q.get("change_pct")
    chg_str = "—" if chg is None else f"{chg:+.2f}%"
    as_of = q.get("as_of")
    provider = q.get("provider", "?")
    return f"[QUOTE]      {q.get('ticker', '?')}  {price}  {chg_str}  {as_of}  (provider: {provider})"


def _render_fundamentals(f: dict | None) -> list[str]:
    if not f:
        return ["[FUND]       fundamentals unavailable"]
    lines: list[str] = []
    pe = f.get("pe_ttm")
    if pe is not None:
        lines.append(f"[FUND-PE]    {_fmt_or_dash(pe)}   (TTM)")
    eps = f.get("eps_ttm")
    if eps is not None:
        lines.append(f"[FUND-EPS]   {_fmt_or_dash(eps)}")
    roe = f.get("roe")
    if roe is not None:
        lines.append(f"[FUND-ROE]   {_fmt_or_dash(roe, 3)}")
    roce = f.get("roce")
    if roce is not None:
        lines.append(f"[FUND-ROCE]  {_fmt_or_dash(roce, 3)}")
    de = f.get("debt_to_equity")
    if de is not None:
        lines.append(f"[FUND-DEBT]  {_fmt_or_dash(de)}   (D/E)")
    rev = f.get("revenue_ttm")
    if rev is not None:
        lines.append(f"[FUND-REV]   {_fmt_or_dash(rev)}")
    ni = f.get("net_income_ttm")
    if ni is not None:
        lines.append(f"[FUND-NI]    {_fmt_or_dash(ni)}")
    if not lines:
        return ["[FUND]       fundamentals unavailable"]
    return lines


def _render_news(news: list[dict]) -> list[str]:
    if not news:
        return ["[NEWS]       no news returned"]
    lines: list[str] = []
    for i, n in enumerate(news, start=1):
        published = n.get("published_at")
        date_str = (
            published.strftime("%Y-%m-%d") if hasattr(published, "strftime")
            else (str(published)[:10] if published else "—")
        )
        source = n.get("source") or "?"
        headline = (n.get("headline") or "—").strip()
        # Truncate very long headlines so the dossier remains compact.
        if len(headline) > 140:
            headline = headline[:137] + "…"
        lines.append(f"[NEWS-{i}]     \"{headline}\"  {source}  {date_str}")
    return lines


def build_source_dossier(
    ticker: str,
    quote: dict,
    fundamentals: dict | None,
    news: list[dict],
) -> str:
    """Returns the compact source dossier string for Critic input."""
    parts: list[str] = [f"SOURCES AVAILABLE TO THE ANALYST ({ticker}):", ""]
    parts.append(_render_quote(quote))
    parts.extend(_render_fundamentals(fundamentals))
    parts.extend(_render_news(news))
    parts.append("")
    parts.append(
        "VERIFY: every numeric or qualitative claim in the analyst's output "
        "should map to one of the [...] tags above. Flag any that does not."
    )
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_dossier.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/agents/_dossier.py finterminal/tests/agents/test_dossier.py && git commit -m "feat(agents): add compact source dossier builder for Critic input"
```

---

## Task 5: Data agent (`agents/data.py`)

**What:** Deterministic Data agent. Parallelizes the three fetches via `asyncio.gather`+`asyncio.to_thread` (existing fetchers are sync). Builds both context block (full, for Analyst) and source dossier (slim, for Critic). Owns DuckDB upserts.

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/data.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_data_agent.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_data_agent.py`:

```python
"""Data agent: deterministic, parallelized fetches + DuckDB upserts + dossier construction."""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timezone

import pytest

from finterminal.agents.base import AgentContext
from finterminal.agents.data import DataAgent
from finterminal.data.duckdb_store import get_conn


@pytest.fixture
def conn():
    """Fresh DuckDB per test."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DUCKDB_PATH"] = f"{tmp}/test.duckdb"
        c = get_conn()
        yield c
        c.close()


def _stub_quote_ok(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc),
        "last_price": 2945.50,
        "change_pct": 1.2,
        "volume": 4_200_000,
        "market_cap": 2.0e13,
        "provider": "stub",
    }


def _stub_fund_ok(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).date(),
        "pe_ttm": 23.4,
        "eps_ttm": None,
        "roe": 0.091,
        "roce": None,
        "debt_to_equity": 0.45,
        "revenue_ttm": None,
        "net_income_ttm": None,
        "provider": "stub",
    }


def _stub_news_ok(ticker: str, limit: int = 10) -> list[dict]:
    return [
        {"id": "n1", "ticker": ticker, "source": "Moneycontrol",
         "headline": "Q4 profit up 8%", "url": "u1",
         "published_at": "2026-04-26", "body": "..."},
        {"id": "n2", "ticker": ticker, "source": "Livemint",
         "headline": "Jio user adds slow", "url": "u2",
         "published_at": "2026-04-25", "body": "..."},
    ]


def _stub_quote_raise(ticker: str) -> dict:
    raise RuntimeError(f"quote fetch failed for {ticker}")


def _stub_fund_raise(ticker: str) -> dict:
    raise RuntimeError(f"fundamentals fetch failed for {ticker}")


def _stub_news_raise(ticker: str, limit: int = 10) -> list[dict]:
    raise RuntimeError(f"news fetch failed for {ticker}")


def test_data_agent_happy_path(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_ok,
    )
    ctx = AgentContext(ticker="RELIANCE.NS", conn=conn)
    result = asyncio.run(agent.run(ctx))

    assert result.ok is True
    assert result.payload is not None
    p = result.payload
    assert p["quote"]["last_price"] == 2945.50
    assert p["fundamentals"]["pe_ttm"] == 23.4
    assert len(p["news"]) == 2
    assert "[QUOTE]" in p["source_dossier"]
    assert "## Quote" in p["context_block"]
    assert "[FUND-PE]" in p["source_dossier"]


def test_data_agent_persists_to_duckdb(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_ok,
    )
    ctx = AgentContext(ticker="RELIANCE.NS", conn=conn)
    asyncio.run(agent.run(ctx))

    rows = conn.execute("SELECT count(*) FROM quotes").fetchone()
    assert rows[0] >= 1
    rows = conn.execute("SELECT count(*) FROM fundamentals").fetchone()
    assert rows[0] >= 1
    rows = conn.execute("SELECT count(*) FROM news").fetchone()
    assert rows[0] == 2


def test_data_agent_quote_failure_returns_not_ok(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_raise,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_ok,
    )
    ctx = AgentContext(ticker="X.NS", conn=conn)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "quote" in (result.error or "").lower()


def test_data_agent_fund_failure_proceeds_with_none(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_raise,
        fetch_news=_stub_news_ok,
    )
    ctx = AgentContext(ticker="RELIANCE.NS", conn=conn)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is True
    assert result.payload["fundamentals"] is None


def test_data_agent_news_failure_proceeds_empty(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_raise,
    )
    ctx = AgentContext(ticker="RELIANCE.NS", conn=conn)
    result = asyncio.run(agent.run(ctx))
    assert result.ok is True
    assert result.payload["news"] == []


def test_data_agent_is_not_llm(conn):
    agent = DataAgent(
        fetch_quote=_stub_quote_ok,
        fetch_fundamentals=_stub_fund_ok,
        fetch_news=_stub_news_ok,
    )
    assert agent.is_llm is False
    assert agent.name == "data"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_data_agent.py -v
```

Expected: ImportError on `finterminal.agents.data`.

- [ ] **Step 3: Implement the Data agent**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/data.py`:

```python
"""Data agent — deterministic Python, no LLM.

Parallelizes the three Phase-1 fetches via asyncio.to_thread, persists to
DuckDB, and emits both:
  - context_block (full, for Analyst — same shape as today)
  - source_dossier (slim, for Critic — see agents._dossier)

Fetchers are injected via the constructor so tests can stub them. Production
construction (in analyze_flow._build_default_registry) wires the real
openbb_client functions.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from ..data import duckdb_store
from ..ui.panels import build_context_block
from . import _dossier
from .base import AgentContext, AgentResult

logger = logging.getLogger(__name__)


class DataAgent:
    """name='data', is_llm=False. Returns AgentResult with payload dict containing
    {quote, fundamentals, news, context_block, source_dossier}."""

    name = "data"
    is_llm = False

    def __init__(
        self,
        fetch_quote: Callable[[str], dict],
        fetch_fundamentals: Callable[[str], dict],
        fetch_news: Callable[..., list[dict]],
    ) -> None:
        self._fetch_quote = fetch_quote
        self._fetch_fundamentals = fetch_fundamentals
        self._fetch_news = fetch_news

    async def run(self, ctx: AgentContext) -> AgentResult:
        ticker = ctx.ticker

        # Fan out fetches in parallel. quote is required; fund + news are best-effort.
        quote_t = asyncio.create_task(asyncio.to_thread(self._fetch_quote, ticker))
        fund_t = asyncio.create_task(asyncio.to_thread(self._fetch_fundamentals, ticker))
        news_t = asyncio.create_task(asyncio.to_thread(self._fetch_news, ticker, 10))

        # Wait on all three; we tolerate fund/news exceptions.
        results = await asyncio.gather(quote_t, fund_t, news_t, return_exceptions=True)
        quote_or_exc, fund_or_exc, news_or_exc = results

        # Quote is required.
        if isinstance(quote_or_exc, Exception):
            return AgentResult(ok=False, error=f"quote fetch failed: {quote_or_exc!s}")
        quote: dict = quote_or_exc  # type: ignore[assignment]

        fundamentals: dict | None
        if isinstance(fund_or_exc, Exception):
            logger.warning("fundamentals unavailable for %s: %s", ticker, fund_or_exc)
            fundamentals = None
        else:
            fundamentals = fund_or_exc  # type: ignore[assignment]

        news: list[dict]
        if isinstance(news_or_exc, Exception):
            logger.warning("news unavailable for %s: %s", ticker, news_or_exc)
            news = []
        else:
            news = news_or_exc  # type: ignore[assignment]

        # Persist (sync — duckdb is thread-safe for this connection pattern).
        try:
            duckdb_store.upsert_quote(ctx.conn, quote)
            if fundamentals:
                duckdb_store.upsert_fundamentals(ctx.conn, fundamentals)
            if news:
                duckdb_store.upsert_news(ctx.conn, news)
        except Exception as exc:  # noqa: BLE001 — surface as agent-level error
            return AgentResult(ok=False, error=f"persistence failed: {exc!s}")

        context_block = build_context_block(ticker, quote, fundamentals, news)
        source_dossier = _dossier.build_source_dossier(ticker, quote, fundamentals, news)

        payload = {
            "quote": quote,
            "fundamentals": fundamentals,
            "news": news,
            "context_block": context_block,
            "source_dossier": source_dossier,
        }
        return AgentResult(ok=True, payload=payload)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_data_agent.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/agents/data.py finterminal/tests/agents/test_data_agent.py && git commit -m "feat(agents): add deterministic Data agent with parallel fetches + dossier"
```

---

## Task 6: Persistence — `002_critiques.sql` migration + helpers

**What:** Migration adds the `critiques` table + a nullable `payload_json` column on `analyses`. New helper functions: `record_critique`, `recent_analysis` (rehydrates a full result for the cache), and a small extension to `record_analysis` (accepts optional `payload`).

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/data/migrations/002_critiques.sql`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/data/duckdb_store.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_persistence.py`

- [ ] **Step 1: Write the failing tests**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_persistence.py`:

```python
"""Schema migration + persistence helpers for /analyze 4a."""
from __future__ import annotations

import os
import tempfile

import pytest

from finterminal.data.duckdb_store import (
    get_conn,
    record_analysis,
    record_critique,
    recent_analysis,
)


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DUCKDB_PATH"] = f"{tmp}/test.duckdb"
        c = get_conn()
        yield c
        c.close()


def test_critiques_table_exists(conn):
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    assert "critiques" in tables


def test_analyses_payload_json_column_exists(conn):
    cols = [r[0] for r in conn.execute("DESCRIBE analyses").fetchall()]
    assert "payload_json" in cols


def test_record_analysis_accepts_optional_payload(conn):
    aid = record_analysis(
        conn,
        ticker="RELIANCE.NS",
        bull_case="bull",
        bear_case="bear",
        confidence=0.6,
        sources={"model": "test"},
        payload={"variant_perception": "vp", "conviction": "Watch Long"},
    )
    assert isinstance(aid, str)
    rows = conn.execute(
        "SELECT payload_json FROM analyses WHERE id = ?", [aid]
    ).fetchall()
    assert len(rows) == 1
    assert "Watch Long" in rows[0][0]


def test_record_analysis_payload_optional(conn):
    """Existing call sites that don't pass payload still work (None stored)."""
    aid = record_analysis(
        conn, ticker="X.NS", bull_case="b", bear_case="r", confidence=0.5
    )
    row = conn.execute(
        "SELECT payload_json FROM analyses WHERE id = ?", [aid]
    ).fetchone()
    assert row[0] is None


def test_record_critique_inserts_row(conn):
    aid = record_analysis(
        conn, ticker="RELIANCE.NS", bull_case="b", bear_case="r", confidence=0.6
    )
    cid = record_critique(
        conn,
        analysis_id=aid,
        verdict="REVISE",
        issues_md="- one issue",
        missing_md="- pledge",
        confidence_adj=0.5,
        raw_text="full text",
        model="claude-sonnet-4-6",
        tokens_in=1200,
        tokens_out=380,
        degraded=False,
        error=None,
    )
    assert isinstance(cid, str)
    row = conn.execute(
        "SELECT verdict, confidence_adj, degraded, error FROM critiques WHERE id = ?",
        [cid],
    ).fetchone()
    assert row[0] == "REVISE"
    assert row[1] == 0.5
    assert row[2] is False
    assert row[3] is None


def test_record_critique_can_be_degraded(conn):
    aid = record_analysis(
        conn, ticker="X.NS", bull_case="b", bear_case="r", confidence=0.4
    )
    cid = record_critique(
        conn, analysis_id=aid, verdict=None, issues_md="", missing_md="",
        confidence_adj=None, raw_text="", model=None,
        tokens_in=0, tokens_out=0, degraded=True, error="timeout after 30s",
    )
    row = conn.execute(
        "SELECT degraded, error FROM critiques WHERE id = ?", [cid]
    ).fetchone()
    assert row[0] is True
    assert row[1] == "timeout after 30s"


def test_recent_analysis_returns_none_when_empty(conn):
    assert recent_analysis(conn, "GHOST.NS", ttl_s=300) is None


def test_recent_analysis_returns_within_ttl(conn):
    aid = record_analysis(
        conn,
        ticker="RELIANCE.NS",
        bull_case="bull",
        bear_case="bear",
        confidence=0.6,
        sources={"model": "test"},
        payload={"variant_perception": "vp", "conviction": "Watch Long"},
    )
    record_critique(
        conn, analysis_id=aid, verdict="ACCEPT", issues_md="",
        missing_md="", confidence_adj=0.6, raw_text="x",
        model="m", tokens_in=10, tokens_out=10, degraded=False, error=None,
    )
    out = recent_analysis(conn, "RELIANCE.NS", ttl_s=300)
    assert out is not None
    assert out["analysis_id"] == aid
    assert out["analyst_payload"]["conviction"] == "Watch Long"
    assert out["critic_payload"]["verdict"] == "ACCEPT"


def test_recent_analysis_stale_returns_none(conn):
    record_analysis(conn, ticker="OLD.NS", bull_case="b", bear_case="r", confidence=0.5)
    # Negative TTL → everything is stale.
    assert recent_analysis(conn, "OLD.NS", ttl_s=-1) is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_persistence.py -v
```

Expected: failures across all 9 tests (no `critiques` table, no `payload_json` column, no `record_critique` / `recent_analysis` exports).

- [ ] **Step 3: Write the migration SQL**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/data/migrations/002_critiques.sql`:

```sql
-- Phase 2 / 4a: persist Critic output + cache the full Analyst payload.
-- Additive only. Existing rows in `analyses` get NULL for payload_json.

CREATE TABLE IF NOT EXISTS critiques (
    id              VARCHAR PRIMARY KEY,
    analysis_id     VARCHAR NOT NULL,
    verdict         VARCHAR,
    issues_md       VARCHAR,
    missing_md      VARCHAR,
    confidence_adj  DOUBLE,
    raw_text        VARCHAR,
    model           VARCHAR,
    tokens_in       BIGINT,
    tokens_out      BIGINT,
    degraded        BOOLEAN DEFAULT FALSE,
    error           VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_critiques_analysis ON critiques(analysis_id);

ALTER TABLE analyses ADD COLUMN payload_json VARCHAR;
```

> Note: the migration system runs each `.sql` file once via the `_migrations` ledger, so `ALTER TABLE ADD COLUMN` (without `IF NOT EXISTS`) is safe — re-runs are gated upstream.

- [ ] **Step 4: Extend `duckdb_store.py` with the new helpers**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/data/duckdb_store.py`:

a) Replace the existing `record_analysis` (current lines 175-192) with:

```python
def record_analysis(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    bull_case: str,
    bear_case: str,
    confidence: float,
    sources: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Returns the inserted row's id (uuid4).

    `payload` is the full Analyst parsed dict (variant/conviction/assumptions/
    what_would_change in addition to bull/bear/confidence). Stored as JSON in
    the additive `payload_json` column for use by the result-cache rehydration.
    """
    aid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO analyses (id, ticker, bull_case, bear_case, confidence, sources_json, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            aid, ticker, bull_case, bear_case, confidence,
            json.dumps(sources or {}),
            json.dumps(payload) if payload is not None else None,
        ],
    )
    return aid
```

b) Append at the end of the file (after `latest_analysis`):

```python
# ---------- critiques (Phase 2 / 4a) ----------

def record_critique(
    conn: duckdb.DuckDBPyConnection,
    *,
    analysis_id: str,
    verdict: str | None,
    issues_md: str,
    missing_md: str,
    confidence_adj: float | None,
    raw_text: str,
    model: str | None,
    tokens_in: int,
    tokens_out: int,
    degraded: bool,
    error: str | None,
) -> str:
    """Returns the inserted critique row's id (uuid4)."""
    cid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO critiques (
            id, analysis_id, verdict, issues_md, missing_md,
            confidence_adj, raw_text, model, tokens_in, tokens_out,
            degraded, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            cid, analysis_id, verdict, issues_md, missing_md,
            confidence_adj, raw_text, model, tokens_in, tokens_out,
            degraded, error,
        ],
    )
    return cid


def recent_analysis(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    ttl_s: int,
) -> dict | None:
    """Return the most recent analysis (joined with its latest critique) for `ticker`
    if its created_at is within `ttl_s` seconds of now. Otherwise None.

    Result shape (matches the orchestrator's AnalysisResult contract):
      {
        "analysis_id": str,
        "ticker": str,
        "created_at": datetime,
        "analyst_payload": dict,        # rehydrated from payload_json (or {} if NULL)
        "critic_payload": dict | None,  # None when no critique row OR degraded=True
        "degraded": bool,
        "critic_error": str | None,
      }
    """
    if ttl_s < 0:
        return None
    from datetime import datetime as _dt, timedelta as _td
    cutoff = _dt.now() - _td(seconds=ttl_s)
    row = conn.execute(
        """
        SELECT id, ticker, created_at, bull_case, bear_case, confidence,
               sources_json, payload_json
        FROM analyses
        WHERE ticker = ? AND created_at > ?
        ORDER BY created_at DESC LIMIT 1
        """,
        [ticker, cutoff],
    ).fetchone()
    if not row:
        return None
    aid, t, created, bull, bear, conf, sources_json, payload_json = row

    analyst_payload: dict = json.loads(payload_json) if payload_json else {}
    # Always include the columns the panel needs even if payload_json is empty
    # (e.g. for analyses written before 4a):
    analyst_payload.setdefault("ticker", t)
    analyst_payload.setdefault("bull_case", bull)
    analyst_payload.setdefault("bear_case", bear)
    analyst_payload.setdefault("confidence", conf)

    crit_row = conn.execute(
        """
        SELECT verdict, issues_md, missing_md, confidence_adj, raw_text,
               degraded, error
        FROM critiques
        WHERE analysis_id = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        [aid],
    ).fetchone()

    critic_payload: dict | None = None
    degraded = False
    critic_error: str | None = None
    if crit_row:
        verdict, issues_md, missing_md, conf_adj, raw_text, degraded_flag, err = crit_row
        degraded = bool(degraded_flag)
        critic_error = err
        if not degraded:
            critic_payload = {
                "verdict": verdict,
                "issues_md": issues_md,
                "missing_md": missing_md,
                "confidence_adj": conf_adj,
                "raw_text": raw_text,
            }

    return {
        "analysis_id": aid,
        "ticker": t,
        "created_at": created,
        "analyst_payload": analyst_payload,
        "critic_payload": critic_payload,
        "degraded": degraded,
        "critic_error": critic_error,
    }
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_persistence.py tests/test_smoke.py -v
```

Expected: 9 new tests + all existing smoke tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/data/migrations/002_critiques.sql finterminal/src/finterminal/data/duckdb_store.py finterminal/tests/agents/test_persistence.py && git commit -m "feat(data): critiques table + payload_json column + recent_analysis cache helper"
```

---

## Task 7: Critic agent + parser

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/critic.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_critic.py`

- [ ] **Step 1: Write the failing tests**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_critic.py`:

```python
"""Critic parser + agent. LLM call is mocked; we only test parsing + agent surface."""
from __future__ import annotations

import asyncio

import pytest

from finterminal.agents.base import AgentContext
from finterminal.agents.critic import CriticAgent, parse_critique
from finterminal.llm.base import Completion


_WELL_FORMED = """## Issues
- [HIGH] PE claim 23.4 unsourced; [FUND-PE] missing
- [MEDIUM] Bear case ignores GST collection slowdown

## Missing Data
- pledge status
- FII flow last 30d

## Confidence Adjustment
0.55  — initial 0.72 is too high given missing pledge data

## Verdict
REVISE
"""


def test_parse_critique_well_formed():
    out = parse_critique(_WELL_FORMED)
    assert out["verdict"] == "REVISE"
    assert "[HIGH]" in out["issues_md"]
    assert "pledge status" in out["missing_md"]
    assert out["confidence_adj"] == 0.55


def test_parse_critique_handles_accept():
    out = parse_critique("## Verdict\nACCEPT\n")
    assert out["verdict"] == "ACCEPT"
    assert out["issues_md"] == ""
    assert out["confidence_adj"] is None


def test_parse_critique_handles_reject():
    out = parse_critique("## Verdict\nREJECT\n")
    assert out["verdict"] == "REJECT"


def test_parse_critique_unparseable_returns_none_verdict():
    out = parse_critique("the model returned prose without sections")
    assert out["verdict"] is None
    assert out["raw_text"] == "the model returned prose without sections"


def test_parse_critique_clamps_confidence():
    out = parse_critique("## Confidence Adjustment\n1.5\n## Verdict\nACCEPT\n")
    assert out["confidence_adj"] == 1.0
    out = parse_critique("## Confidence Adjustment\n-0.2\n## Verdict\nACCEPT\n")
    assert out["confidence_adj"] == 0.0


# ---------- agent surface ----------


class _StubProvider:
    def __init__(self, completion: Completion):
        self._c = completion
        self.last_kwargs: dict | None = None

    async def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self._c


def _ok_completion(text: str = _WELL_FORMED) -> Completion:
    return Completion(text=text, tokens_in=1200, tokens_out=350,
                      model="claude-sonnet-4-6", provider="anthropic")


def test_critic_agent_happy_path():
    provider = _StubProvider(_ok_completion())
    agent = CriticAgent(get_provider=lambda: provider)

    ctx = AgentContext(
        ticker="RELIANCE.NS", conn=None,  # type: ignore[arg-type]
        prior={
            "analyst": {"bull_case": "...", "bear_case": "...", "variant_perception": "...",
                        "confidence": 0.72, "conviction": "Watch Long"},
            "data": {"source_dossier": "[QUOTE] ..."},
        },
    )
    result = asyncio.run(agent.run(ctx))

    assert result.ok is True
    assert result.payload["verdict"] == "REVISE"
    assert result.payload["confidence_adj"] == 0.55
    assert result.tokens_in == 1200
    assert result.tokens_out == 350
    assert result.model == "claude-sonnet-4-6"
    assert provider.last_kwargs is not None
    assert provider.last_kwargs["max_tokens"] == 500
    assert provider.last_kwargs["cache_system"] is True


def test_critic_agent_provider_error_returns_not_ok():
    from finterminal.llm.base import ProviderError

    class _ErrProvider:
        async def complete(self, **kwargs):
            raise ProviderError("rate limited")

    agent = CriticAgent(get_provider=lambda: _ErrProvider())
    ctx = AgentContext(
        ticker="X.NS", conn=None,  # type: ignore[arg-type]
        prior={"analyst": {}, "data": {"source_dossier": ""}},
    )
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "rate limited" in (result.error or "")


def test_critic_agent_unparseable_output_returns_not_ok():
    """Malformed LLM text → ok=False so the orchestrator can degrade gracefully."""
    provider = _StubProvider(_ok_completion("just some prose, no sections"))
    agent = CriticAgent(get_provider=lambda: provider)
    ctx = AgentContext(
        ticker="X.NS", conn=None,  # type: ignore[arg-type]
        prior={"analyst": {}, "data": {"source_dossier": ""}},
    )
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "parse" in (result.error or "").lower()


def test_critic_agent_metadata():
    agent = CriticAgent(get_provider=lambda: _StubProvider(_ok_completion()))
    assert agent.name == "critic"
    assert agent.is_llm is True
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_critic.py -v
```

Expected: ImportError on `finterminal.agents.critic`.

- [ ] **Step 3: Implement Critic + parser**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/critic.py`:

```python
"""Critic agent — adversarial review of Analyst output.

Sees: Analyst payload + compact source dossier (NOT the full context block).
Produces: {issues_md, missing_md, confidence_adj, verdict, raw_text}.

LLM provider injected via `get_provider` so tests can stub. Production wiring
in analyze_flow._build_default_registry resolves via router.for_agent('critic').
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from ..llm.base import LLMProvider, Message, ProviderError
from ..llm.budget import record
from .base import AgentContext, AgentResult

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "critic.md"

_SECTIONS = ("Issues", "Missing Data", "Confidence Adjustment", "Verdict")
_VALID_VERDICTS = {"ACCEPT", "REVISE", "REJECT"}


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def parse_critique(text: str) -> dict:
    """Parse Critic output into structured dict.

    Lenient: missing sections become empty strings. Confidence parses the first
    float and clamps to [0, 1]. Verdict matches ACCEPT/REVISE/REJECT as a
    case-insensitive substring; unparseable → None (tells the orchestrator to
    degrade).
    """
    pattern = re.compile(
        r"^##\s+(" + "|".join(re.escape(s) for s in _SECTIONS) + r")\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(1)] = text[start:end].strip()

    verdict: str | None = None
    raw_v = sections.get("Verdict", "").upper()
    for label in _VALID_VERDICTS:
        if label in raw_v:
            verdict = label
            break

    conf_adj: float | None = None
    raw_conf = sections.get("Confidence Adjustment", "")
    if raw_conf:
        m = re.search(r"-?\d+(?:\.\d+)?", raw_conf)
        if m:
            try:
                v = float(m.group(0))
                conf_adj = max(0.0, min(1.0, v))
            except ValueError:
                conf_adj = None

    return {
        "verdict": verdict,
        "issues_md": sections.get("Issues", ""),
        "missing_md": sections.get("Missing Data", ""),
        "confidence_adj": conf_adj,
        "raw_text": text,
    }


def _format_user_message(analyst_payload: dict, source_dossier: str) -> str:
    """Serialize the inputs the Critic needs into a single user message."""
    parts = [
        "ANALYST OUTPUT TO REVIEW",
        "========================",
        f"## Variant Perception\n{analyst_payload.get('variant_perception', '')}",
        f"## Bull Case\n{analyst_payload.get('bull_case', '')}",
        f"## Bear Case\n{analyst_payload.get('bear_case', '')}",
        f"## Conviction\n{analyst_payload.get('conviction', '')}",
        f"## Confidence\n{analyst_payload.get('confidence', '')}",
        f"## Assumptions\n{analyst_payload.get('assumptions', '')}",
        f"## What Would Change My Mind\n{analyst_payload.get('what_would_change', '')}",
        "",
        source_dossier,
    ]
    return "\n\n".join(parts)


class CriticAgent:
    name = "critic"
    is_llm = True

    def __init__(self, get_provider: Callable[[], LLMProvider]) -> None:
        self._get_provider = get_provider

    async def run(self, ctx: AgentContext) -> AgentResult:
        analyst = ctx.prior.get("analyst") or {}
        data = ctx.prior.get("data") or {}
        dossier = data.get("source_dossier", "")
        user_msg = _format_user_message(analyst, dossier)

        try:
            provider = self._get_provider()
            completion = await provider.complete(
                system=_load_prompt(),
                messages=[Message(role="user", content=user_msg)],
                max_tokens=500,
                temperature=0.2,
                cache_system=True,
            )
        except ProviderError as exc:
            return AgentResult(ok=False, error=str(exc))

        record("critic", completion)

        parsed = parse_critique(completion.text)
        if parsed["verdict"] is None:
            return AgentResult(
                ok=False,
                error=f"parse failed: no verdict in critic output ({len(completion.text)} chars)",
                model=completion.model,
                tokens_in=completion.tokens_in,
                tokens_out=completion.tokens_out,
                payload=parsed,
            )

        return AgentResult(
            ok=True,
            payload=parsed,
            model=completion.model,
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
        )
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_critic.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/agents/critic.py finterminal/tests/agents/test_critic.py && git commit -m "feat(agents): add Critic agent with parse_critique and retry-friendly failure mode"
```

---

## Task 8: Analyst agent (extracted from `supervisor.py`)

**What:** Move the LLM call + `parse_analysis` from `supervisor.py` into `agents/analyst.py`. Wrap as an Agent. **Leave `supervisor.py` in place for now** — it stays callable (commands.py still imports it) until Task 10 rewires the command. Deletion happens in Task 11.

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/analyst.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_analyst_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_analyst_agent.py`:

```python
"""Analyst agent surface tests."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from finterminal.agents.analyst import AnalystAgent, parse_analysis
from finterminal.agents.base import AgentContext
from finterminal.llm.base import Completion


_BASELINE = Path(__file__).parent / "fixtures" / "analyst_baseline_RELIANCE.json"


def test_parse_analysis_against_baseline():
    """The new parser MUST produce the same output as the captured baseline."""
    data = json.loads(_BASELINE.read_text())
    parsed_now = parse_analysis(data["raw_response"])
    expected = data["parsed"]
    assert parsed_now == expected, (
        "parse_analysis output drifted from baseline. "
        "If this is intended, regenerate via "
        "`uv run python tests/agents/fixtures/baseline_capture.py`."
    )


class _StubProvider:
    def __init__(self, completion: Completion):
        self._c = completion
        self.last_kwargs: dict | None = None

    async def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self._c


def test_analyst_agent_happy_path():
    raw = json.loads(_BASELINE.read_text())["raw_response"]
    completion = Completion(
        text=raw, tokens_in=2200, tokens_out=1800,
        model="gpt-5-mini", provider="openai",
    )
    provider = _StubProvider(completion)
    agent = AnalystAgent(get_provider=lambda: provider)

    ctx = AgentContext(
        ticker="RELIANCE.NS", conn=None,  # type: ignore[arg-type]
        prior={"data": {"context_block": "# RELIANCE.NS\n## Quote ..."}},
    )
    result = asyncio.run(agent.run(ctx))

    assert result.ok is True
    assert result.payload["bull_case"]
    assert result.payload["bear_case"]
    assert result.payload["confidence"] == 0.55
    assert result.payload["conviction"] == "Watch Long"
    assert result.tokens_in == 2200
    assert result.tokens_out == 1800
    assert result.model == "gpt-5-mini"
    assert provider.last_kwargs["cache_system"] is True
    assert provider.last_kwargs["max_tokens"] == 2000


def test_analyst_agent_provider_error_returns_not_ok():
    from finterminal.llm.base import ProviderError

    class _Err:
        async def complete(self, **kwargs):
            raise ProviderError("boom")

    agent = AnalystAgent(get_provider=lambda: _Err())
    ctx = AgentContext(
        ticker="X.NS", conn=None,  # type: ignore[arg-type]
        prior={"data": {"context_block": ""}},
    )
    result = asyncio.run(agent.run(ctx))
    assert result.ok is False
    assert "boom" in (result.error or "")


def test_analyst_agent_metadata():
    agent = AnalystAgent(get_provider=lambda: _StubProvider(
        Completion(text="", tokens_in=0, tokens_out=0, model="m", provider="p")))
    assert agent.name == "analyst"
    assert agent.is_llm is True
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_analyst_agent.py -v
```

Expected: ImportError on `finterminal.agents.analyst`.

- [ ] **Step 3: Implement AnalystAgent + extract `parse_analysis`**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/analyst.py`:

```python
"""Analyst agent — runs analyst.md to produce the 7-section structured analysis.

This module is the LLM-bearing successor to today's `agents/supervisor.py`.
The fetching + persistence side of that file moves to `agents/data.py` and
`agents/analyze_flow.py` respectively.

`parse_analysis` is preserved verbatim from supervisor.py to guarantee
non-regression against the captured baseline (tests/agents/fixtures/).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from ..llm.base import LLMProvider, Message, ProviderError
from ..llm.budget import record
from .base import AgentContext, AgentResult

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "analyst.md"

_SECTIONS = (
    "Variant Perception",
    "Bull Case",
    "Bear Case",
    "Conviction",
    "Confidence",
    "Assumptions",
    "What Would Change My Mind",
)

_VALID_CONVICTION = {
    "Conviction Long",
    "Watch Long",
    "Avoid",
    "Conviction Short",
    "Pair-Short",
}


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def parse_analysis(text: str) -> dict:
    """Splits the analyst's structured response into fields.

    Lenient: missing sections become empty strings; missing confidence becomes None.
    Confidence parses the first float in the section and clamps to [0, 1].
    Conviction matches the first valid label as a case-insensitive substring.

    NOTE: this is identical to the previous supervisor.parse_analysis; preserved
    so the non-regression baseline test is meaningful.
    """
    pattern = re.compile(
        r"^##\s+(" + "|".join(re.escape(s) for s in _SECTIONS) + r")\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(1)] = text[start:end].strip()

    confidence: float | None = None
    raw_conf = sections.get("Confidence", "")
    if raw_conf:
        m = re.search(r"-?\d+(?:\.\d+)?", raw_conf)
        if m:
            try:
                v = float(m.group(0))
                confidence = max(0.0, min(1.0, v))
            except ValueError:
                confidence = None

    conviction: str | None = None
    raw_conv = sections.get("Conviction", "").strip()
    if raw_conv:
        for label in _VALID_CONVICTION:
            if label.lower() in raw_conv.lower():
                conviction = label
                break

    return {
        "variant_perception": sections.get("Variant Perception", ""),
        "bull_case": sections.get("Bull Case", ""),
        "bear_case": sections.get("Bear Case", ""),
        "conviction": conviction,
        "confidence": confidence,
        "assumptions": sections.get("Assumptions", ""),
        "what_would_change": sections.get("What Would Change My Mind", ""),
    }


class AnalystAgent:
    name = "analyst"
    is_llm = True

    def __init__(self, get_provider: Callable[[], LLMProvider]) -> None:
        self._get_provider = get_provider

    async def run(self, ctx: AgentContext) -> AgentResult:
        data = ctx.prior.get("data") or {}
        context_block = data.get("context_block", "")
        user_msg = (
            context_block
            + "\n\nProduce the analysis per your output format. "
            "Every numeric claim must trace to a [src: ...] tag from the context above."
        )
        try:
            provider = self._get_provider()
            completion = await provider.complete(
                system=_load_prompt(),
                messages=[Message(role="user", content=user_msg)],
                max_tokens=2000,
                temperature=0.3,
                cache_system=True,
            )
        except ProviderError as exc:
            return AgentResult(ok=False, error=str(exc))

        record("analyst", completion)

        parsed = parse_analysis(completion.text)
        parsed["ticker"] = ctx.ticker

        return AgentResult(
            ok=True,
            payload=parsed,
            model=completion.model,
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
        )
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_analyst_agent.py -v
```

Expected: 4 passed (including the baseline non-regression test).

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/agents/analyst.py finterminal/tests/agents/test_analyst_agent.py && git commit -m "feat(agents): add Analyst agent (extracted from supervisor.py); preserves baseline parse"
```

---

## Task 9: Orchestrator (`agents/analyze_flow.py`)

**What:** The flow that composes Data → Analyst → Critic, applies retry-then-degrade for the Critic, persists, and respects the 5-min result cache. Builds its own registry from the `router.for_agent` chain.

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/analyze_flow.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_analyze_flow.py`

- [ ] **Step 1: Write failing integration tests**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_analyze_flow.py`:

```python
"""End-to-end /analyze flow tests with all LLM calls mocked."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from finterminal.agents.analyze_flow import (
    AnalysisError,
    AnalysisResult,
    RESULT_CACHE_TTL_S,
    _build_registry_with_overrides,
    run_analyze,
)
from finterminal.agents.base import AgentContext, AgentResult
from finterminal.agents.data import DataAgent
from finterminal.data.duckdb_store import get_conn
from finterminal.llm.base import Completion, ProviderError


_BASELINE = Path(__file__).parent / "fixtures" / "analyst_baseline_RELIANCE.json"
_RAW_ANALYST = json.loads(_BASELINE.read_text())["raw_response"]
_RAW_CRITIC = """## Issues
- [HIGH] Bull case "margin expansion" — only [NEWS-1] supports; weak.

## Missing Data
- pledge status

## Confidence Adjustment
0.45  — initial 0.55 too high without pledge data

## Verdict
REVISE
"""


def _quote(t):
    return {
        "ticker": t, "as_of": datetime.now(timezone.utc),
        "last_price": 100.0, "change_pct": 0.0,
        "volume": 1, "market_cap": 1, "provider": "stub",
    }


def _fund(t):
    return {"ticker": t, "as_of": datetime.now(timezone.utc).date(),
            "pe_ttm": 20.0, "eps_ttm": None, "roe": 0.1, "roce": None,
            "debt_to_equity": 0.5, "revenue_ttm": None, "net_income_ttm": None,
            "provider": "stub"}


def _news(t, limit=10):
    return [{"id": "n1", "ticker": t, "source": "Mint",
             "headline": "x", "url": "u", "published_at": "2026-04-26",
             "body": ""}]


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DUCKDB_PATH"] = f"{tmp}/test.duckdb"
        c = get_conn()
        yield c
        c.close()


class _MockProvider:
    def __init__(self, text: str, model: str = "mock"):
        self._text = text
        self._model = model
        self.calls = 0

    async def complete(self, **kwargs):
        self.calls += 1
        return Completion(text=self._text, tokens_in=100, tokens_out=80,
                          model=self._model, provider="mock")


class _ErrProvider:
    async def complete(self, **kwargs):
        raise ProviderError("simulated failure")


def _registry(*, analyst_provider, critic_primary, critic_fallback=None):
    """Build a flow registry with stubbed providers + stub fetchers."""
    data_agent = DataAgent(_quote, _fund, _news)
    return _build_registry_with_overrides(
        data_agent=data_agent,
        analyst_provider=lambda: analyst_provider,
        critic_primary=lambda: critic_primary,
        critic_fallback=(lambda: critic_fallback) if critic_fallback else None,
    )


def test_run_analyze_happy_path(conn):
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST, "gpt-5-mini"),
        critic_primary=_MockProvider(_RAW_CRITIC, "claude-sonnet-4-6"),
    )
    result: AnalysisResult = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))

    assert result.degraded is False
    assert result.analyst_payload["confidence"] == 0.55
    assert result.analyst_payload["conviction"] == "Watch Long"
    assert result.critic_payload is not None
    assert result.critic_payload["verdict"] == "REVISE"
    assert result.analysis_id  # uuid string


def test_run_analyze_persists_critique(conn):
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )
    asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    n = conn.execute("SELECT count(*) FROM critiques").fetchone()[0]
    assert n == 1


def test_run_analyze_critic_failure_with_fallback_succeeds(conn):
    primary = _ErrProvider()
    fallback = _MockProvider(_RAW_CRITIC)
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=primary,
        critic_fallback=fallback,
    )
    result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    assert result.degraded is False
    assert result.critic_payload["verdict"] == "REVISE"
    assert fallback.calls == 1


def test_run_analyze_critic_total_failure_degrades(conn):
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_ErrProvider(),
        critic_fallback=_ErrProvider(),
    )
    result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    assert result.degraded is True
    assert result.critic_payload is None
    assert "simulated failure" in (result.critic_error or "")
    # Analyst-side data still complete:
    assert result.analyst_payload["bull_case"]
    # Degraded row written:
    row = conn.execute(
        "SELECT degraded, error FROM critiques WHERE analysis_id = ?",
        [result.analysis_id],
    ).fetchone()
    assert row[0] is True
    assert "simulated failure" in row[1]


def test_run_analyze_analyst_failure_raises(conn):
    reg = _registry(
        analyst_provider=_ErrProvider(),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )
    with pytest.raises(AnalysisError):
        asyncio.run(run_analyze("X.NS", conn, reg))


def test_run_analyze_result_cache_hit_skips_llm(conn):
    primary = _MockProvider(_RAW_ANALYST)
    crit = _MockProvider(_RAW_CRITIC)
    reg = _registry(analyst_provider=primary, critic_primary=crit)

    asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    primary_calls_after_first = primary.calls
    crit_calls_after_first = crit.calls

    # Second call within TTL — should not invoke either provider:
    result2 = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    assert primary.calls == primary_calls_after_first
    assert crit.calls == crit_calls_after_first
    assert result2.analyst_payload["conviction"] == "Watch Long"


def test_run_analyze_fresh_flag_bypasses_cache(conn):
    primary = _MockProvider(_RAW_ANALYST)
    crit = _MockProvider(_RAW_CRITIC)
    reg = _registry(analyst_provider=primary, critic_primary=crit)
    asyncio.run(run_analyze("RELIANCE.NS", conn, reg))
    asyncio.run(run_analyze("RELIANCE.NS", conn, reg, fresh=True))
    assert primary.calls == 2
    assert crit.calls == 2


def test_run_analyze_non_regression_analyst_fields_match_baseline(conn):
    """The crown-jewel test: post-refactor flow's Analyst output equals the captured snapshot."""
    expected = json.loads(_BASELINE.read_text())["parsed"]
    reg = _registry(
        analyst_provider=_MockProvider(_RAW_ANALYST),
        critic_primary=_MockProvider(_RAW_CRITIC),
    )
    result = asyncio.run(run_analyze("RELIANCE.NS", conn, reg))

    actual = {k: result.analyst_payload[k] for k in expected.keys()}
    assert actual == expected


def test_result_cache_ttl_constant_is_300():
    assert RESULT_CACHE_TTL_S == 300
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_analyze_flow.py -v
```

Expected: ImportError on `finterminal.agents.analyze_flow`.

- [ ] **Step 3: Implement the orchestrator**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/analyze_flow.py`:

```python
"""Orchestrator for /analyze.

Flow:
  1. Result-cache check (5-min TTL on analyses+critiques rows).
  2. Data agent (deterministic, parallel fetches).
  3. Analyst agent (LLM, system-cached).
  4. Critic agent with retry-then-degrade fallback.
  5. Persist analyses + critiques rows.
  6. Return AnalysisResult.

The Critic's failure is non-fatal: a degraded row is written and the result
returned with `degraded=True`. The Analyst's failure IS fatal — there is no
analysis without an Analyst.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import duckdb

from ..data import duckdb_store, openbb_client
from ..llm.base import LLMProvider
from ..llm.router import Router
from .analyst import AnalystAgent
from .base import AgentContext, AgentRegistry
from .critic import CriticAgent
from .data import DataAgent

RESULT_CACHE_TTL_S = 300  # 5 min — see spec §6 lever 4


class AnalysisError(Exception):
    """Raised when /analyze cannot produce any usable output (Analyst failure or data failure)."""


@dataclass
class AnalysisResult:
    analysis_id: str
    ticker: str
    created_at: datetime
    analyst_payload: dict          # parsed Analyst output (7 sections + ticker)
    critic_payload: dict | None    # Critic parsed output OR None when degraded
    degraded: bool                 # True when Critic failed
    critic_error: str | None       # populated when degraded


def _build_default_registry(router: Router) -> AgentRegistry:
    """Production registry. Wires real fetchers + router-resolved providers."""
    reg = AgentRegistry()
    reg.register(DataAgent(
        fetch_quote=openbb_client.fetch_quote,
        fetch_fundamentals=openbb_client.fetch_fundamentals,
        fetch_news=openbb_client.fetch_news,
    ))
    reg.register(AnalystAgent(get_provider=lambda: router.for_agent("analyst")))
    reg.register(CriticAgent(get_provider=lambda: router.for_agent("critic")))
    reg._critic_fallback = _critic_fallback_factory(router)  # type: ignore[attr-defined]
    return reg


def _critic_fallback_factory(router: Router) -> Callable[[], LLMProvider] | None:
    """Returns a callable that builds the Critic's first fallback provider, or None."""
    chain = router.fallback_chain("critic")
    if len(chain) < 2:
        return None
    fallback_provider = chain[1]
    return lambda: fallback_provider


def _build_registry_with_overrides(
    *,
    data_agent: DataAgent,
    analyst_provider: Callable[[], LLMProvider],
    critic_primary: Callable[[], LLMProvider],
    critic_fallback: Callable[[], LLMProvider] | None = None,
) -> AgentRegistry:
    """Test-only registry builder. Used by unit tests to inject mocks."""
    reg = AgentRegistry()
    reg.register(data_agent)
    reg.register(AnalystAgent(get_provider=analyst_provider))
    reg.register(CriticAgent(get_provider=critic_primary))
    if critic_fallback is not None:
        reg._critic_fallback = critic_fallback  # type: ignore[attr-defined]
    return reg


async def _run_critic_with_fallback(
    reg: AgentRegistry,
    ctx: AgentContext,
):
    """Run primary critic; on ok=False, retry once on the fallback provider.
    Returns the AgentResult (ok=True or ok=False — caller handles degrade)."""
    critic = reg.get("critic")
    result = await critic.run(ctx)
    if result.ok:
        return result

    fallback_factory = getattr(reg, "_critic_fallback", None)
    if fallback_factory is None:
        return result

    fallback_critic = CriticAgent(get_provider=fallback_factory)
    return await fallback_critic.run(ctx)


def _rehydrate_cached(cached: dict) -> AnalysisResult:
    return AnalysisResult(
        analysis_id=cached["analysis_id"],
        ticker=cached["ticker"],
        created_at=cached["created_at"],
        analyst_payload=cached["analyst_payload"],
        critic_payload=cached["critic_payload"],
        degraded=cached["degraded"],
        critic_error=cached["critic_error"],
    )


async def run_analyze(
    ticker: str,
    conn: duckdb.DuckDBPyConnection,
    registry: AgentRegistry | None = None,
    *,
    fresh: bool = False,
) -> AnalysisResult:
    """Top-level /analyze entry point.

    Raises AnalysisError if Data or Analyst fails. Critic failures degrade
    silently into the result (degraded=True, critic_payload=None).
    """
    if not fresh:
        cached = duckdb_store.recent_analysis(conn, ticker, ttl_s=RESULT_CACHE_TTL_S)
        if cached is not None:
            return _rehydrate_cached(cached)

    if registry is None:
        from ..llm.router import build_router as _build_router  # late import; avoids cycle
        router = _build_router()
        registry = _build_default_registry(router)

    ctx = AgentContext(ticker=ticker, conn=conn)

    # 1. Data
    data_result = await registry.get("data").run(ctx)
    if not data_result.ok:
        raise AnalysisError(f"data fetch failed: {data_result.error}")
    ctx.prior["data"] = data_result.payload

    # 2. Analyst
    analyst_result = await registry.get("analyst").run(ctx)
    if not analyst_result.ok:
        raise AnalysisError(f"analyst failed: {analyst_result.error}")
    ctx.prior["analyst"] = analyst_result.payload

    # 3. Critic (with retry-then-degrade)
    critic_result = await _run_critic_with_fallback(registry, ctx)

    degraded = not critic_result.ok
    critic_payload = critic_result.payload if critic_result.ok else None
    critic_error = critic_result.error if not critic_result.ok else None

    # 4. Persist analyses row
    sources = {
        "model": analyst_result.model,
        "tokens_in": analyst_result.tokens_in,
        "tokens_out": analyst_result.tokens_out,
        "data_quote_provider": (data_result.payload.get("quote") or {}).get("provider"),
    }
    aid = duckdb_store.record_analysis(
        conn,
        ticker=ticker,
        bull_case=analyst_result.payload.get("bull_case", ""),
        bear_case=analyst_result.payload.get("bear_case", ""),
        confidence=(analyst_result.payload.get("confidence") or 0.0),
        sources=sources,
        payload=analyst_result.payload,
    )

    # 5. Persist critique row
    cp = critic_payload or {}
    duckdb_store.record_critique(
        conn,
        analysis_id=aid,
        verdict=cp.get("verdict"),
        issues_md=cp.get("issues_md", ""),
        missing_md=cp.get("missing_md", ""),
        confidence_adj=cp.get("confidence_adj"),
        raw_text=cp.get("raw_text", "") if not degraded else "",
        model=critic_result.model,
        tokens_in=critic_result.tokens_in,
        tokens_out=critic_result.tokens_out,
        degraded=degraded,
        error=critic_error,
    )

    return AnalysisResult(
        analysis_id=aid,
        ticker=ticker,
        created_at=datetime.now(),
        analyst_payload=analyst_result.payload,
        critic_payload=critic_payload,
        degraded=degraded,
        critic_error=critic_error,
    )
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_analyze_flow.py -v
```

Expected: 9 passed (including non-regression test against the baseline).

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/agents/analyze_flow.py finterminal/tests/agents/test_analyze_flow.py && git commit -m "feat(agents): add analyze_flow orchestrator with retry-degrade Critic + result cache"
```

---

## Task 10: UI — extend `analysis_panel` with Critic block

**Files:**
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/ui/panels.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_panels_critic.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_panels_critic.py`:

```python
"""Verify analysis_panel renders critic block when provided + degrades cleanly."""
from __future__ import annotations

from rich.console import Console

from finterminal.ui.panels import analysis_panel


_ANALYSIS = {
    "ticker": "RELIANCE.NS",
    "variant_perception": "consensus too bullish",
    "bull_case": "- margins improving",
    "bear_case": "- new-energy capex risk",
    "conviction": "Watch Long",
    "confidence": 0.55,
    "assumptions": "- crude $70-95",
    "what_would_change": "- pledge increase",
}


def _render(panel) -> str:
    console = Console(record=True, width=120, file=open("/dev/null", "w"))
    console.print(panel)
    return console.export_text()


def test_panel_renders_without_critic_today_layout():
    panel = analysis_panel(_ANALYSIS)
    text = _render(panel)
    assert "RELIANCE.NS" in text
    assert "margins" in text
    assert "Watch Long" in text


def test_panel_renders_critic_block_when_present():
    critic = {
        "verdict": "REVISE",
        "issues_md": "- [HIGH] PE claim unsourced",
        "missing_md": "- pledge status",
        "confidence_adj": 0.45,
    }
    panel = analysis_panel(_ANALYSIS, critic=critic)
    text = _render(panel)
    assert "REVISE" in text
    assert "PE claim" in text
    assert "pledge" in text
    # Both numbers (raw + adjusted) visible:
    assert "0.55" in text
    assert "0.45" in text


def test_panel_renders_degraded_critic_badge():
    panel = analysis_panel(_ANALYSIS, critic_error="timeout after 30s")
    text = _render(panel)
    assert "Critic unavailable" in text
    assert "timeout" in text
    # Original confidence still rendered, no adjustment shown:
    assert "0.55" in text
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_panels_critic.py -v
```

Expected: failures on `unexpected keyword argument 'critic'`.

- [ ] **Step 3: Extend `analysis_panel`**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/ui/panels.py`, replace the `analysis_panel` function (current lines 191-259) with:

```python
def analysis_panel(
    analysis: dict,
    critic: dict | None = None,
    critic_error: str | None = None,
) -> Panel:
    """analysis = {ticker, variant_perception, bull_case, bear_case, conviction,
                  confidence, assumptions, what_would_change}.

    critic (optional) = {verdict, issues_md, missing_md, confidence_adj}.
    critic_error (optional) = string explaining why Critic was unavailable.
    Pass at most one of (critic, critic_error). When both are None, the panel
    renders today's pre-4a layout — no behavioral regression for callers.
    """
    variant = (analysis.get("variant_perception") or "").strip()
    variant_panel = (
        Panel(variant, title="variant perception", border_style="magenta")
        if variant and "no consensus" not in variant.lower()
        else None
    )

    bull = Panel(
        analysis.get("bull_case") or "[dim]—[/]",
        title="bull",
        border_style="green",
    )
    bear = Panel(
        analysis.get("bear_case") or "[dim]—[/]",
        title="bear",
        border_style="red",
    )

    body = Table.grid(expand=True)
    body.add_column(ratio=1)
    body.add_column(ratio=1)
    body.add_row(bull, bear)

    # Conviction + confidence (with optional critic adjustment) on a single line
    conv = analysis.get("conviction")
    confidence = analysis.get("confidence")
    summary = Text()
    if conv and conv in _CONVICTION_STYLE:
        style, glyph = _CONVICTION_STYLE[conv]
        summary.append(f"{glyph} {conv}", style=style)
        summary.append("    ")
    elif conv:
        summary.append(f"conviction: {conv}    ", style="dim")
    if confidence is None:
        summary.append("confidence: —", style="dim")
    else:
        summary.append("confidence  ")
        summary.append(_confidence_gauge(float(confidence)))
        if critic and critic.get("confidence_adj") is not None:
            summary.append(f"  →  {critic['confidence_adj']:.2f} (critic)",
                           style="bold yellow")

    assumptions = analysis.get("assumptions") or "[dim]—[/]"
    wwcm = analysis.get("what_would_change") or "[dim]—[/]"

    footer = Table.grid(expand=True)
    footer.add_column(ratio=1)
    footer.add_column(ratio=1)
    footer.add_row(
        Panel(assumptions, title="assumptions", border_style="cyan"),
        Panel(wwcm, title="what would change my mind", border_style="cyan"),
    )

    stack = Table.grid(expand=True)
    stack.add_column()
    if variant_panel is not None:
        stack.add_row(variant_panel)
    stack.add_row(body)
    stack.add_row(summary)
    stack.add_row(footer)

    if critic is not None:
        verdict = critic.get("verdict") or "?"
        verdict_color = {
            "ACCEPT": "green", "REVISE": "yellow", "REJECT": "red",
        }.get(verdict, "white")
        crit_body = Text()
        crit_body.append(f"verdict: {verdict}\n", style=f"bold {verdict_color}")
        if critic.get("issues_md"):
            crit_body.append("\nIssues:\n", style="bold")
            crit_body.append(critic["issues_md"] + "\n")
        if critic.get("missing_md"):
            crit_body.append("\nMissing:\n", style="bold")
            crit_body.append(critic["missing_md"] + "\n")
        stack.add_row(Panel(crit_body, title="critic", border_style=verdict_color))
    elif critic_error is not None:
        stack.add_row(Panel(
            Text(f"Critic unavailable: {critic_error}", style="dim italic"),
            title="critic", border_style="dim",
        ))

    ts = analysis.get("created_at") or datetime.now(timezone.utc)
    subtitle = f"[dim]{ts.isoformat() if hasattr(ts, 'isoformat') else ts}[/]"
    return Panel(
        stack,
        title=f"/analyze {analysis.get('ticker', '?')}",
        subtitle=subtitle,
        border_style="cyan",
    )
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_panels_critic.py tests/test_smoke.py -v
```

Expected: all panel tests pass + smoke tests still green.

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add finterminal/src/finterminal/ui/panels.py finterminal/tests/agents/test_panels_critic.py && git commit -m "feat(ui): extend analysis_panel with optional critic block + degraded badge"
```

---

## Task 11: Wire `commands.py` + `agents.yaml` rename + delete supervisor.py

**What:** Rewire `_cmd_analyze` to use `analyze_flow.run_analyze`. Rename `supervisor:` → `analyst:` in `agents.yaml`. Add `--fresh` flag parsing. Delete `agents/supervisor.py` + `prompts/supervisor.md`. Update `tests/test_smoke.py` imports for the parser tests (move them to `tests/agents/test_parse_analysis_smoke.py`).

**Files:**
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/commands.py`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/config/agents.yaml`
- Delete: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/supervisor.py`
- Delete: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/prompts/supervisor.md`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/test_smoke.py`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_commands_analyze.py`

- [ ] **Step 1: Write failing test for the `--fresh` flag parsing + new flow wiring**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/agents/test_commands_analyze.py`:

```python
"""Surface tests for the rewired _cmd_analyze."""
from __future__ import annotations

from finterminal import commands


def test_analyze_flag_parser_extracts_fresh():
    args = ["RELIANCE", "--fresh"]
    parsed_ticker, fresh = commands._parse_analyze_args(args)
    assert parsed_ticker == "RELIANCE"
    assert fresh is True


def test_analyze_flag_parser_default_no_fresh():
    parsed_ticker, fresh = commands._parse_analyze_args(["INFY"])
    assert parsed_ticker == "INFY"
    assert fresh is False


def test_analyze_flag_parser_rejects_zero_args():
    import pytest
    with pytest.raises(commands._UsageError):
        commands._parse_analyze_args([])


def test_analyze_flag_parser_rejects_extra_positionals():
    import pytest
    with pytest.raises(commands._UsageError):
        commands._parse_analyze_args(["RELIANCE", "INFY"])


def test_analyze_flag_parser_rejects_unknown_flags():
    import pytest
    with pytest.raises(commands._UsageError):
        commands._parse_analyze_args(["RELIANCE", "--bogus"])
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest tests/agents/test_commands_analyze.py -v
```

Expected: AttributeError on `commands._parse_analyze_args`.

- [ ] **Step 3: Rewire `commands.py`**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/commands.py`:

a) Replace the `_cmd_analyze` function (current lines 145-163) with:

```python
# ---------- /analyze ----------


def _parse_analyze_args(args: list[str]) -> tuple[str, bool]:
    """Returns (ticker, fresh). Raises _UsageError on invalid input."""
    fresh = False
    positionals: list[str] = []
    for a in args:
        if a == "--fresh":
            fresh = True
        elif a.startswith("--"):
            raise _UsageError(f"unknown flag: {a}")
        else:
            positionals.append(a)
    if len(positionals) != 1:
        raise _UsageError("/analyze SYMBOL [--fresh]  (e.g. /analyze RELIANCE)")
    return positionals[0], fresh


def _cmd_analyze(args: list[str], console: Console) -> None:
    raw, fresh = _parse_analyze_args(args)
    ticker = normalize_ticker(raw)

    from .agents.analyze_flow import AnalysisError, run_analyze

    conn = duckdb_store.get_conn()
    try:
        with console.status(
            f"analyzing {ticker} (Analyst + Critic)…", spinner="dots"
        ):
            try:
                result = asyncio.run(run_analyze(ticker, conn, fresh=fresh))
            except AnalysisError as exc:
                console.print(panels.error_panel(str(exc), title="/analyze failed"))
                return
    finally:
        conn.close()

    panel_kwargs: dict = {}
    if result.degraded:
        panel_kwargs["critic_error"] = result.critic_error or "unknown"
    elif result.critic_payload is not None:
        panel_kwargs["critic"] = result.critic_payload

    console.print(panels.analysis_panel(result.analyst_payload, **panel_kwargs))
```

(`asyncio`, `Console`, `panels`, `duckdb_store`, `normalize_ticker` are already imported at the top of the file — no new top-level imports needed.)

- [ ] **Step 4: Update `agents.yaml`**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/config/agents.yaml`, change the first agent block (currently `supervisor:` with the swap-back comment) to `analyst:`:

Old:
```yaml
agents:
  # ---- Phase 1 ----
  supervisor:
    primary: gpt-5-mini
    fallbacks: [gpt-5]
    description: "Decomposes user query, routes to specialists, synthesizes final answer"
    # Swap back to Claude when ANTHROPIC_API_KEY is set:
    # primary: claude-sonnet-4-6
    # fallbacks: [claude-opus-4-7]
```

New:
```yaml
agents:
  # ---- Phase 2 / 4a ----
  analyst:
    primary: gpt-5-mini
    fallbacks: [gpt-5]
    description: "Runs analyst.md to produce 7-section structured analysis (variant/bull/bear/conviction/confidence/assumptions/what-would-change)"
    # Swap to Claude when ANTHROPIC_API_KEY is set:
    # primary: claude-sonnet-4-6
    # fallbacks: [claude-opus-4-7]
```

(The rest of the file — `data`, `news`, `critic`, `bull_bear`, and the commented Phase 2.5 block — stays as-is.)

- [ ] **Step 5: Update `tests/test_smoke.py` to drop supervisor references**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/tests/test_smoke.py`:

a) Replace the `test_supervisor_resolves_to_a_provider` function (lines 23-45) with:

```python
def test_analyst_resolves_to_a_provider():
    """The Analyst's primary must resolve to *some* registered model.

    Whether the actual provider instantiates depends on which API key is set.
    """
    from finterminal.llm import ProviderError, build_router

    router = build_router()
    registry = router._registry  # type: ignore[attr-defined]

    cfg = router._agents.get("analyst")  # type: ignore[attr-defined]
    primary_name = cfg["primary"]
    assert any(m.name == primary_name for m in registry.all()), (
        f"analyst.primary={primary_name} is not in models.yaml"
    )

    try:
        provider = router.for_agent("analyst")
        assert provider.metadata.name == primary_name
    except ProviderError as exc:
        assert "API_KEY" in str(exc)
```

b) Replace the three `parse_analysis` tests (lines 128-173) with imports from the new location:

```python
def test_analysis_parser_extracts_all_sections():
    from finterminal.agents.analyst import parse_analysis

    sample = """## Bull Case
- Margin expansion likely [src: fundamentals.roe]
- Revenue trend up [src: fundamentals.revenue_ttm]

## Bear Case
- High D/E vs peers [src: fundamentals.debt_to_equity]
- Recent block deal pressure [src: news[2]]

## Confidence
0.55

## Assumptions
- Crude stays in range
- No regulatory surprise

## What Would Change My Mind
- Promoter pledge increase
- ROE drop below 8%
"""
    result = parse_analysis(sample)
    assert "Margin expansion" in result["bull_case"]
    assert "block deal" in result["bear_case"]
    assert result["confidence"] == 0.55
    assert "Crude" in result["assumptions"]
    assert "Promoter pledge" in result["what_would_change"]


def test_analysis_parser_handles_missing_sections():
    from finterminal.agents.analyst import parse_analysis

    result = parse_analysis("## Bull Case\n- one bullet only\n")
    assert "one bullet only" in result["bull_case"]
    assert result["bear_case"] == ""
    assert result["confidence"] is None


def test_analysis_parser_clamps_confidence():
    from finterminal.agents.analyst import parse_analysis

    high = parse_analysis("## Confidence\n1.5\n")
    low = parse_analysis("## Confidence\n-0.2\n")
    assert high["confidence"] == 1.0
    assert low["confidence"] == 0.0
```

- [ ] **Step 6: Delete the now-orphaned files**

```bash
rm /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/agents/supervisor.py
rm /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal/src/finterminal/prompts/supervisor.md
```

- [ ] **Step 7: Run the full test suite**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest -v
```

Expected: every test passes (smoke + agents/* + persistence + flow + commands + dossier + critic + analyst + base + provider_cache_kwarg). No "supervisor" import error anywhere.

If you see `ImportError: cannot import name 'parse_analysis' from 'finterminal.agents.supervisor'`, search the codebase for stragglers:

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && grep -r "agents.supervisor" src tests
```

Fix each one to import from `finterminal.agents.analyst` instead.

- [ ] **Step 8: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add -A && git commit -m "refactor: rewire /analyze to multi-agent flow; rename supervisor→analyst; drop legacy module"
```

---

## Task 12: Vault docs (ADR-013 + Phase 2 page + build log)

**Files:**
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/02 - Decisions/ADR-013 Hand-rolled Async over CrewAI for Phase 2.md`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/03 - Phases/Phase 2 - Multi-Agent Foundation.md`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/01 - Architecture/Agent System.md`
- Create: `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/05 - Build Log/2026-04-28 — Multi-Agent Scaffold (4a).md`
- Modify: `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/Index.md`

- [ ] **Step 1: Write ADR-013**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/02 - Decisions/ADR-013 Hand-rolled Async over CrewAI for Phase 2.md`:

```markdown
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

## Cross-links
- Supersedes: parts of [[ADR-002 CrewAI then LangGraph]] (Phase 2 framework only — Phase 3 plan stands)
- Implementation spec: `docs/superpowers/specs/2026-04-28-multi-agent-scaffold-4a-design.md`
- Implementation plan: `docs/superpowers/plans/2026-04-28-multi-agent-scaffold-4a.md`
- Brainstorm: 2026-04-28 (4a path through Phase 2 decomposition)
```

- [ ] **Step 2: Update Phase 2 page**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/03 - Phases/Phase 2 - Multi-Agent Foundation.md`, append a new section right after "## Scope":

```markdown

---

## Status (2026-04-28)

Phase 2 split into independent sub-deliverables for incremental shipping:

| Sub | Name | Status |
|---|---|---|
| 4a | Multi-agent scaffold (`/analyze` → Data + Analyst + Critic) | Shipped — see [[ADR-013 Hand-rolled Async over CrewAI for Phase 2]] |
| 4b | News & Trend agent + `/trends` | Planned (next) |
| 4c | Watchlist persistence | Already shipped in Phase 1 |
| 4d | Textual TUI migration | Deferred |

Framework note: per ADR-013, 4a uses hand-rolled async over the existing `router.for_agent()` interface, not CrewAI. ADR-002's Phase 3 LangGraph migration plan is unchanged.
```

- [ ] **Step 3: Refresh Agent System architecture page**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/01 - Architecture/Agent System.md`, find the section that lists current Phase-1 supervisor and append:

```markdown

### After 4a (2026-04-28) — actual `/analyze` flow

```
/analyze TICKER [--fresh]
  → result-cache check (5-min TTL)        ← skip everything if hit
  → Data agent (deterministic, parallel)  ← no LLM
  → Analyst agent (LLM, analyst.md)       ← system prompt cached on Anthropic
  → Critic agent (LLM, critic.md)         ← retry-then-degrade; max 500 tokens
  → assemble + persist (analyses + critiques rows)
  → render panel (analyst sections + critic block; degraded badge if Critic failed)
```

Files:
- `agents/base.py` — Agent protocol + Registry
- `agents/data.py` — deterministic fetch + dossier
- `agents/analyst.py` — LLM, parses 7 sections (renamed from old `supervisor.py`)
- `agents/critic.py` — LLM, parses verdict
- `agents/analyze_flow.py` — orchestrator
- `agents/_dossier.py` — compact source builder for Critic

See [[ADR-013 Hand-rolled Async over CrewAI for Phase 2]] for framework rationale.
```

- [ ] **Step 4: Build log entry**

Create `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/05 - Build Log/2026-04-28 — Multi-Agent Scaffold (4a).md`:

```markdown
# 2026-04-28 — Multi-Agent Scaffold (Phase 2 / 4a)

**TL;DR:** `/analyze` is no longer a single LLM call. It's now Data → Analyst → Critic over a hand-rolled async orchestrator with prompt caching, a 5-min result cache, and a non-regression test that locks the Analyst output to a captured baseline.

## Commits in this PR

(populate from `git log --oneline` of this branch before merging)

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
```

- [ ] **Step 5: Index update**

In `/Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/Index.md`, find the ADR list and add a row for ADR-013. Find the Build Log list and add a row for `2026-04-28 — Multi-Agent Scaffold (4a)`. (Exact format follows the existing rows in the file — match column shapes.)

- [ ] **Step 6: Verify the doc bundle**

```bash
ls /Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/02\ -\ Decisions/ADR-013*
ls /Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault/05\ -\ Build\ Log/2026-04-28*
```

Expected: both files listed.

- [ ] **Step 7: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git add TerminalVault/ && git commit -m "docs: ADR-013 + Phase 2 status update + 4a build log"
```

---

## Final verification

- [ ] **Step 1: Full test suite green**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run pytest -v
```

Expected: every test passes. If anything fails, fix before declaring 4a done — don't merge red.

- [ ] **Step 2: Lint clean**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run ruff check src tests
```

Expected: zero errors. Auto-fix any minor issues with `uv run ruff check --fix src tests` and commit them as a separate "chore: ruff" commit.

- [ ] **Step 3: Manual smoke against a real ticker**

Set required env vars, then:

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal && uv run finterminal
# at the prompt:
/analyze RELIANCE
```

Expected: panel renders with bull / bear / variant / conviction / confidence / assumptions / what-would-change AND a critic block (or "Critic unavailable" badge if Critic flaked).

Then:

```
/analyze RELIANCE
```

Expected: returns near-instantly with the same panel (result cache hit). No LLM calls.

Then:

```
/analyze RELIANCE --fresh
```

Expected: re-runs the full flow. Slower than the cache-hit case.

- [ ] **Step 4: Push the branch (do NOT merge yet)**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL && git status
git log --oneline | head -20
```

Hand off to the user for code review before merging to main.

---

## Self-Review Notes

**Spec coverage:**
- §1 Goals + Non-goals → Tasks 1-12 collectively
- §2 ADRs (ADR-013 supersession) → Task 12
- §3 File layout → Tasks 2-9
- §4 Agent protocol → Task 2
- §5 Data flow → Task 9 (orchestrator) + Task 5 (Data) + Task 7 (Critic) + Task 8 (Analyst)
- §6 Token economy: lever 1 → Task 4 (dossier); lever 2 → Task 3 (cache_system kwarg) + Tasks 7,8 (cache_system=True); lever 3 → Task 7 (max_tokens=500); lever 4 → Task 6 (recent_analysis) + Task 9 (cache check)
- §7 Failure semantics → Task 5 (data error paths) + Task 9 (`AnalysisError` + retry-degrade)
- §8 Persistence schema → Task 6
- §9 UI panel + degraded variant → Task 10
- §10 Testing strategy: unit tests across Tasks 2-8; integration in Task 9; non-regression captured Task 1, asserted Tasks 8 + 9; failure modes in Tasks 5, 7, 9
- §11 Rollout (commits 0-7 in spec) → Tasks 1-12 here (1:1 mapping with one extra docs task)
- §12 Open questions: `--fresh` parsing → Task 11; TTL hardcoded constant → Task 9 (`RESULT_CACHE_TTL_S = 300`); `/critique-redo` deferred per spec

**Type consistency check:**
- `AgentResult.payload`, `AgentResult.tokens_in/out`, `AgentResult.model` — used identically in tasks 5, 7, 8, 9 ✓
- `AnalysisResult.analyst_payload` / `critic_payload` / `degraded` / `critic_error` — defined in Task 9, consumed in Task 11 ✓
- `record_analysis(..., payload=)` extension — added in Task 6, called in Task 9 ✓
- `record_critique(...)` — defined Task 6, called Task 9 ✓
- `recent_analysis(...)` — defined Task 6, called Task 9 ✓
- `parse_critique` returns dict with keys `verdict / issues_md / missing_md / confidence_adj / raw_text` — same shape consumed by Task 9 + Task 10 ✓

**Placeholder scan:** no TBDs, TODOs, or "fill in" prompts. Every code block in this plan is the actual content the engineer types/pastes.
