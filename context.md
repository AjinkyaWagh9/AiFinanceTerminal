# FINTERMINAL — Context for Next Session

**Last updated:** 2026-05-01 (end of Sub-project #5 ML Pipeline v1 session)

> Read this first. It's a tight pointer to where things are; the authoritative architecture lives in `docs/CLAUDE.md`, `TerminalVault/`, and the spec/ADR files referenced below.

---

## Where the repo lives

- **Working dir:** `/Users/ajinkyawagh/Desktop/FINTERMINAL/`
- **Single git repo at root** (the previous nested `finterminal/.git` submodule was absorbed 2026-05-01).
- **Remote:** `origin` → `https://github.com/AjinkyaWagh9/AiFinanceTerminal.git`
- **Branch:** `main` (only branch, in sync with origin)
- **Legacy archive (do NOT push to):** `https://github.com/AjinkyaWagh9/Finance-Terminal.git` — frozen pre-absorb history; pre-absorb commit log preserved at `docs/finterminal-pre-absorb-history.txt`

Push rules + branching policy + "files NOT to commit" are in `docs/CLAUDE.md` § "Git push rules". Read that section first.

---

## What's shipped (Phase 2)

| # | Sub-project | Status | Tests | Vault build log |
|---|---|---|---|---|
| 4a | Multi-Agent Scaffold | ✅ | — | `2026-04-28 — Multi-Agent Scaffold (4a)` |
| B-2a | News Trend Pipeline | ✅ | 173 | `2026-04-29 — Sprint B-2a News Trend` |
| #1 | Outcomes Ledger | ✅ | — | ADR-017 |
| #2 | Feature Store | ✅ | — | ADR-019 |
| #3 | Quality Engine v1 | ✅ | 293 | `2026-05-01 — Sub-project 3 Quality Engine v1` |
| #4 | Reflexivity Engine v1 | ✅ | 318 | `2026-05-01 — Sub-project 4 Reflexivity Engine v1` + ADR-020 |
| #5 | **ML Pipeline v1** | ✅ | **365** | `2026-05-01 — Sub-project 5 ML Pipeline v1` + ADR-021 |

**Pre-existing failing tests (3, NOT regressions):** `tests/news/test_pipeline.py::test_pipeline_returns_result|persists_stories|persists_clusters` — they fail because they need live news data sources. Ignore in regression checks; baseline is "365 passed + 3 pre-existing fails".

---

## What's left (priority order)

| Next | What | Where it's specced |
|---|---|---|
| **#6 — mgmt_claims engine** | Build on migration 006 (`mgmt_claims` ledger laid down by #3); claims-vs-outcomes scoring | mentioned in #3 build log |
| **v1.5 ML upgrades** | Path signatures (interface stubbed in `ml/dataset.py:extra_feature_builders`), triple-barrier labelling, CPCV, `/predict TCS` REPL command | ADR-021 + spec §2 non-goals |
| **Phase 2.5 — Analyst-Grade** | Earnings-call transcripts, Consensus + revisions, Ownership flows (FII/DII/promoter/pledges), deep Quality (Piotroski/Beneish/Altman/Montier), Peer-Comp tables, Macro 3-layer heatmap | `docs/PLAN.md` §6 + ADR-008 + ADR-011 |
| **Phase 3 — Synthesis Layer** (the actual edge) | Regime Detector, Scenario Engine (probabilistic bull/bear), Signal Weighter, Calibration Loop, Bias Auditor — these consume #5's calibrated probabilities | ADR-011 + PLAN §6.6 |
| **Phase 3 — US tickers + LangGraph migration** | Hot paths to LangGraph; US coverage via Finnhub | PLAN §4.1 + BACKLOG 1.2 |

**Parked in BACKLOG:** Hierarchical Risk Parity (portfolio sizing — separate sub-project), fractional differentiation (lands when backtest engine does).

---

## Key files to read in this order

1. `docs/CLAUDE.md` — workspace instructions, push rules, vault protocol. **Auto-loaded by Claude Code, but re-read it.**
2. `TerminalVault/Index.md` — durable knowledge base; phase status, ADR list, code-map, build log links.
3. `docs/PLAN.md` — multi-phase project plan.
4. `docs/BACKLOG.md` — deferred work + non-goals.
5. `docs/superpowers/specs/2026-05-01-ml-pipeline-v1-design.md` — most recent spec; informs how to approach #6's spec.
6. `TerminalVault/02 - Decisions/ADR-019` → `ADR-020` → `ADR-021` — the engineering arc that landed us here (feature store → versioning + freeze → ML pipeline).

---

## Conventions to honor

- **Indian markets first.** NSE/BSE primary; US in Phase 3.
- **No model names in agent code.** Always `router.for_agent(name)` — see `docs/MODEL-SWAP-GUIDE.md`.
- **DuckDB gotcha:** `asof` is a reserved keyword. Use `as_of` everywhere.
- **`.env` keys local.** Never commit; never echo full keys in tool output.
- **Vault update protocol** is mandatory after meaningful changes — see `docs/CLAUDE.md` § "Vault update protocol". Spawn a Haiku sub-agent for it.
- **Sub-agents:** Haiku for non-thinking work (commits, mechanical edits, vault writes); Sonnet for plan-execution and compute layer; main thread for sequenced decisions and cross-file integration.
- **TDD:** every new module gets failing tests first, then implementation.
- **Pre-absorb single-repo rule:** there is ONE git repo at the workspace root. `finterminal/` is just a directory — has no `.git/` of its own.

---

## Open follow-ups (small, optional)

- Untracked: `SystemPrompts/` — unknown contents, ask user before touching.
- Modified-uncommitted in working tree at end of last session: `.claude/settings.local.json`, `input.md`, `todo.md` — personal/scratch files; never commit without explicit user approval.
- Polish was done at end of #5 (`fix(#5): manifest carries feature_columns`). No outstanding ML-pipeline TODOs.

---

## Auto-memory (loaded each session)

Stored at `~/.claude/projects/-Users-ajinkyawagh-Desktop-FINTERMINAL/memory/`:

- **Use Haiku sub-agents for non-thinking work** (commits, mechanical edits) and Sonnet for repetitive/templated multi-file work — keep main thread tight.
- **Bundle clarifying questions in one message** during brainstorm/spec/plan flows — user prefers numbered multiple-choice list with picks + reasons over one-question-per-turn.

If memory drift suggests anything stale, verify against current code/git before acting.
