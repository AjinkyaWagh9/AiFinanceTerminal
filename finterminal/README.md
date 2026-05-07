# FINTERMINAL

A local-first, AI-augmented equity research terminal — Bloomberg-style density, retail-friendly cost.

Indian equities first (NSE/BSE), US in Phase 3. Built around OpenBB for data, Claude for synthesis, local Qwen/Phi models for cheap classification, and Grok (optional) for X sentiment.

See `../PLAN.md`, `../BACKLOG.md`, `../Phase-1-Kickoff.md`, `../MODEL-SWAP-GUIDE.md` at the workspace root for design and roadmap.

## Phase 1 status

Bootstrap complete. Building toward `/ticker`, `/news`, `/watch`, `/analyze` commands.

## Install

```bash
# Prereqs: Python 3.13+, uv
uv sync                       # installs all deps from pyproject.toml
cp .env.example .env          # then paste your Anthropic key
```

## Run (once Day 4 is built)

```bash
uv run python -m finterminal.terminal
```

## Architecture

- `src/finterminal/llm/` — model abstraction layer (see `../MODEL-SWAP-GUIDE.md`)
- `src/finterminal/data/` — OpenBB + DuckDB + NSE/BSE
- `src/finterminal/agents/` — CrewAI agents (Phase 2+)
- `src/finterminal/ui/` — Rich/Textual TUI
- `config/models.yaml` + `config/agents.yaml` — model registry and per-agent assignment
