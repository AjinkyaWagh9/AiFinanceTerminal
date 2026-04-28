# FINTERMINAL — Phase 1 Kickoff Checklist

Step-by-step from "empty folder" to "working `/analyze RELIANCE` command." Designed to be runnable in **one focused day** (~6 hours) for someone who already codes Python.

**Prerequisites:** macOS (M1+), Python 3.12+, Homebrew, an Anthropic API key.

**Definition of Done:** All checkboxes ticked + the four Phase-1 exit criteria in §6 pass.

---

## Day 0 — Pre-flight (15 min)

- [ ] Confirm Python ≥ 3.12: `python3 --version`
- [ ] Confirm Homebrew: `brew --version`
- [ ] Get an Anthropic API key from console.anthropic.com → save somewhere safe
- [ ] Decide: virtualenv tool (`uv` recommended for speed, else `venv`)
- [ ] Free disk: ≥10 GB (Ollama models eat space)

```bash
# install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Day 1 — Repo bootstrap (45 min)

### 1.1 Create the project

```bash
cd ~/Desktop/FINTERMINAL
uv init --package finterminal
cd finterminal
```

### 1.2 Add core dependencies

```bash
uv add openbb rich textual duckdb chromadb anthropic httpx pydantic python-dotenv
uv add --dev pytest ruff black mypy pre-commit
```

Note: `openbb` pulls a lot. Expect 2–3 minutes. If install fails, try `uv add openbb --extra all` or fall back to selective installs (`openbb-equity`, `openbb-news`).

### 1.3 Create the folder skeleton

```bash
mkdir -p src/finterminal/{ui,data,llm,prompts,agents,llm}
mkdir -p src/finterminal/data/migrations
mkdir tests
touch src/finterminal/{__init__.py,terminal.py}
touch src/finterminal/ui/{__init__.py,panels.py,layout.py}
touch src/finterminal/data/{__init__.py,openbb_client.py,nse.py,duckdb_store.py}
touch src/finterminal/llm/{__init__.py,claude.py,ollama_client.py,router.py}
touch src/finterminal/prompts/{supervisor.md,critic.md,analyst.md}
touch .env.example .gitignore README.md
```

### 1.4 `.env.example` and `.gitignore`

`.env.example`:
```
ANTHROPIC_API_KEY=sk-ant-...
GROK_API_KEY=                   # Phase 2.5, optional
SENTIMENT_ENABLED=false
DUCKDB_PATH=./data/finterminal.duckdb
LOG_LEVEL=INFO
```

`.gitignore`:
```
.env
data/
.venv/
__pycache__/
*.pyc
.ruff_cache/
.mypy_cache/
.pytest_cache/
*.duckdb
*.duckdb.wal
```

Then: `cp .env.example .env` and paste your real Anthropic key.

### 1.5 Init git + first commit

```bash
git init
git add .
git commit -m "Initial scaffold"
```

---

## Day 2 — Local LLM + Ollama (30 min)

Phase 1 only needs Claude. But pull the local model now so Phase 2 isn't blocked.

```bash
brew install ollama
ollama serve &                  # starts daemon (or run in another terminal)
ollama pull qwen3:8b            # ~5 GB download
ollama pull phi4-mini           # ~2.5 GB, used for fast classification later
```

Smoke test:
```bash
ollama run qwen3:8b "What is the PE ratio of Reliance Industries? One sentence."
# (you'll get a hallucinated number — that's expected; tests connectivity only)
```

---

## Day 3 — DuckDB schema + first OpenBB fetch (90 min)

### 3.1 Phase-1 schema

Create `src/finterminal/data/migrations/001_initial.sql`:

```sql
CREATE TABLE IF NOT EXISTS quotes (
    ticker        VARCHAR NOT NULL,
    asof          TIMESTAMP NOT NULL,
    last_price    DOUBLE,
    change_pct    DOUBLE,
    volume        BIGINT,
    market_cap    DOUBLE,
    PRIMARY KEY (ticker, asof)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker        VARCHAR NOT NULL,
    asof          DATE NOT NULL,
    pe_ttm        DOUBLE,
    eps_ttm       DOUBLE,
    roe           DOUBLE,
    roce          DOUBLE,
    debt_to_equity DOUBLE,
    revenue_ttm   DOUBLE,
    net_income_ttm DOUBLE,
    PRIMARY KEY (ticker, asof)
);

CREATE TABLE IF NOT EXISTS news (
    id            VARCHAR PRIMARY KEY,
    ticker        VARCHAR,
    source        VARCHAR,
    headline      VARCHAR,
    url           VARCHAR,
    published_at  TIMESTAMP,
    body          VARCHAR
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker        VARCHAR PRIMARY KEY,
    added_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes         VARCHAR
);

CREATE TABLE IF NOT EXISTS analyses (
    id            VARCHAR PRIMARY KEY,
    ticker        VARCHAR,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    bull_case     VARCHAR,
    bear_case     VARCHAR,
    confidence    DOUBLE,
    sources_json  VARCHAR
);
```

### 3.2 `duckdb_store.py` skeleton (concept; write it yourself)

Functions to implement:
- `get_conn()` → returns a DuckDB connection at `DUCKDB_PATH`, runs migrations on first open
- `upsert_quote(ticker, asof, …)`
- `latest_quote(ticker)` → returns most recent quote row
- `upsert_fundamentals(ticker, asof, …)`
- `add_to_watchlist(ticker, notes=None)`
- `record_analysis(ticker, bull, bear, confidence, sources)`

### 3.3 `openbb_client.py` skeleton

Functions:
- `fetch_quote(ticker: str) -> dict` — uses `obb.equity.price.quote()`
- `fetch_fundamentals(ticker: str) -> dict` — uses `obb.equity.fundamental.metrics()`
- `fetch_news(ticker: str, limit=20) -> list[dict]` — uses `obb.news.company()`

For Indian tickers, use `.NS` suffix (NSE) or `.BO` (BSE) where required: `RELIANCE.NS`.

### 3.4 Smoke test

Quick REPL check:
```bash
uv run python -c "
from finterminal.data.openbb_client import fetch_quote
print(fetch_quote('RELIANCE.NS'))
"
```

If you get a quote dict, you're wired up. Common failure: OpenBB asks for a free API key for some providers — sign up at my.openbb.co and add `OPENBB_PAT` to `.env`.

---

## Day 4 — REPL + Rich panel (90 min)

### 4.1 `terminal.py` — the entrypoint

Concept (write your own; this is the shape, not the code):

```python
# pseudocode shape
import sys
from rich.console import Console
from rich.panel import Panel
from .commands import dispatch

console = Console()

def main():
    console.print(Panel("FINTERMINAL v0.1 — type /help", style="bold cyan"))
    while True:
        try:
            line = console.input("[bold green]>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        dispatch(line, console)

if __name__ == "__main__":
    main()
```

### 4.2 Phase-1 commands to implement

- `/help` — list available commands
- `/ticker <SYMBOL>` — fetch quote + fundamentals → render in a Rich panel
- `/news <SYMBOL>` — fetch + render news table
- `/watch add <SYMBOL>`, `/watch list`, `/watch remove <SYMBOL>`
- `/quit` — exit

### 4.3 Rich panel layout

Use `rich.layout.Layout` to split terminal into:
- Header (1 line, ticker name + last price + change)
- Body (split: left = fundamentals key/value, right = recent headlines)
- Footer (1 line, prompt status / data freshness timestamp)

Color rules:
- Green `change_pct > 0`, red `< 0`, yellow `|change_pct| > 5%`
- Stale data (>15 min for quote) → dim grey

### 4.4 Run it

```bash
uv run python -m finterminal.terminal
```

You should be able to type `/ticker RELIANCE.NS` and see a panel.

---

## Day 5 — `/analyze` with Claude (90 min)

This is the validation moment for the whole architecture. Get *one* AI command working end-to-end with discipline.

### 5.1 LLM abstraction layer (PLAN.md §3.1)

**Build the abstraction now**, even though Phase 1 only uses Claude. Adding it later means refactoring 13 agents in Phase 2.5. Now it's ~200 lines.

Files to create:
- `src/finterminal/llm/base.py` — define `Message`, `Completion`, `ModelMetadata`, `LLMProvider` protocol
- `src/finterminal/llm/registry.py` — `ModelRegistry` class that loads `config/models.yaml`, instantiates providers
- `src/finterminal/llm/router.py` — `Router` class that loads `config/agents.yaml`, exposes `for_agent(name)`
- `src/finterminal/llm/budget.py` — log every call into DuckDB `llm_calls (ts, agent, model, tokens_in, tokens_out, cost_usd, latency_ms)`
- `src/finterminal/llm/providers/anthropic.py` — implements `LLMProvider`, wraps Anthropic SDK with retry
- `src/finterminal/llm/providers/null.py` — no-op for non-LLM agents
- `src/finterminal/llm/providers/ollama.py` — stub for Phase 2 (importable but only needs to work in Phase 2)

Plus `config/models.yaml` and `config/agents.yaml` per §3.1 examples (Phase 1 only needs the Claude entry and supervisor/data/critic/bull_bear agents).

The Anthropic provider wraps the SDK with:
- `complete(system, messages, max_tokens=2000, ...) -> Completion`
- Built-in retry with exponential backoff
- Cost logging via `budget.py` (every call → DuckDB row)

**No agent code names a model.** Agents say `router.for_agent("critic")` and get a handle.

### 5.2 `prompts/analyst.md` — first system prompt

Write the prompt frame from `PLAN.md` §5.3 explicitly. Include:
- Rich Dad asset/liability lens
- Stoic uncertainty (name what you cannot know)
- Munger inversion (state the bear case crisply or you don't understand the bull)
- **Source discipline:** only cite numbers that came in via the user message; tag every numeric claim with `[src: …]`

### 5.3 `/analyze TICKER` flow

1. Fetch quote + fundamentals + last 10 news headlines from DuckDB (or live if stale).
2. Format into a single user-message context block: `# RELIANCE.NS\n## Quote\n…\n## Fundamentals\n…\n## Recent News\n…`
3. Resolve LLM via the router: `llm = router.for_agent("supervisor")` — never `Anthropic(...)` directly.
4. Call `llm.complete(system=load_prompt("analyst.md"), messages=[...])` with instruction: "Produce a structured response with sections: Bull Case, Bear Case, Confidence (0–1), Assumptions, What Would Change My Mind."
5. Parse response into structured fields.
6. Persist into `analyses` table.
7. Render in a Rich panel with bull/bear side-by-side and confidence as a colored gauge.

### 5.4 Smoke test the discipline

Run `/analyze RELIANCE.NS` three times. Verify:
- [ ] Every number in bull/bear has a `[src: …]` tag
- [ ] No numeric claim is invented (cross-check 3 of them)
- [ ] "What Would Change My Mind" section is non-empty and concrete
- [ ] Confidence is calibrated (0.9 should be rare; default to 0.4–0.7)
- [ ] Total Claude cost per call < $0.05 (log shows token counts)

If any of those fail, **fix the prompt before moving on**. The whole project rests on this discipline.

---

## Day 6 — Polish + commit + tag (60 min)

- [ ] Add `pre-commit` hooks: ruff, black, end-of-file-fixer
- [ ] Write `tests/test_smoke.py`: imports work, DuckDB opens, OpenBB quote fetch returns shape
- [ ] Update `README.md` with: install instructions, env vars, Phase-1 command list, screenshot
- [ ] Commit: `git commit -m "Phase 1 MVP — /ticker /news /watch /analyze working"`
- [ ] Tag: `git tag v0.1.0-phase1`

---

## 6. Phase-1 Exit Criteria (must pass before starting Phase 2)

Tested on a 5-name watchlist (RELIANCE, HDFCBANK, INFY, TCS, ITC):

1. [ ] `/ticker TICKER` returns a panel within 2 seconds (warm), 5 seconds (cold).
2. [ ] `/news TICKER` returns ≥10 headlines from ≥2 distinct sources.
3. [ ] `/analyze TICKER` returns a structured bull/bear with sourced numbers, confidence, and assumptions in under 30 seconds.
4. [ ] Used in lieu of MoneyControl for the morning check-in for **2 consecutive trading days** without falling back to a browser.

If criterion 4 fails, fix the gap before adding agents in Phase 2 — the foundation isn't ready.

---

## 7. Likely first hiccups (and fixes)

| Symptom | Likely cause | Fix |
|---|---|---|
| `openbb` install hangs | Building wheels for scientific deps | `uv add openbb --no-cache` and let it run; or use `pip install openbb` in a fresh venv |
| OpenBB returns empty for `RELIANCE.NS` | Provider not enabled or PAT missing | Sign up at my.openbb.co → set `OPENBB_PAT` in `.env` |
| Ollama "model not found" | Daemon not running | `ollama serve` in a separate terminal |
| Claude returns hallucinated numbers | Prompt not strict enough on source discipline | Strengthen `analyst.md` — explicit "if a number isn't in the user message, say 'data unavailable'" |
| Rich panels overflow on small terminal | Default width too high | Use `console.size` to detect, switch to compact layout below 100 cols |
| DuckDB locked error | Two processes opened the same file | Single-process for now; if you need concurrent reads, set `read_only=True` |

---

## 8. After Phase 1

Once exit criteria pass:
1. Re-read `PLAN.md` §6 Phase 2 — make sure scope still feels right.
2. Resolve open question Q4 (CEO list) before Phase 2.5.
3. Spend 1 week using only the Phase 1 terminal before adding agents. You'll discover what's actually missing — and that list is more honest than what you'd plan in advance.

The biggest risk to this project isn't building the wrong thing — it's building everything in `PLAN.md` before validating that the foundation feels good to use.
