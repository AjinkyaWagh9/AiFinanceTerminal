# 2026-04-28 — OpenAI-Compatible Provider Added

> Back to [[Index]] | See also [[ADR-010 Generic OpenAI-Compat Provider Class]] · [[04 - Code Map/llm — abstraction layer]] · [[04 - Code Map/openai-compat-provider]] · [[2026-04-28 - Phase 1 REPL Wiring Complete]]

---

## What was added

- **`OpenAICompatProvider`** — single class serving `openai_compat`, `openai`, and `xai` aliases via the providers registry.
- Grok now routes through this class with `provider: xai` + its own `api_key_env` + `base_url` in `models.yaml` — no separate `XAIProvider` class needed.
- Three OpenAI models registered: `gpt-5-nano`, `gpt-5-mini`, `gpt-5`.
- `ModelMetadata` gained three optional fields: `api_key_env`, `base_url`, `base_url_env`.
- `OPENAI_API_KEY` placeholder added to `.env.example`.

---

## Why (cost rationale)

Per `/analyze` call (~3 k in / ~600 out tokens):

| Model | $/call |
|---|---|
| Claude Sonnet 4.6 | ~$0.0180 |
| gpt-5 | ~$0.0100 |
| gpt-5-mini | ~$0.0019 |
| gpt-5-nano | ~$0.0004 |

- `gpt-5-nano` is ~45× cheaper than Sonnet 4.6 for the same call shape.
- Swap path: one line in `config/agents.yaml` (`model: gpt-5-mini`) — no code change. See [[ADR-010 Generic OpenAI-Compat Provider Class]] and `MODEL-SWAP-GUIDE.md` Playbook 1.5.

---

## Files touched

| File | Change |
|---|---|
| `src/finterminal/llm/providers/openai_compat.py` | NEW — `OpenAICompatProvider`; resolution logic + `complete()` |
| `src/finterminal/llm/providers/__init__.py` | Registered under `openai_compat`, `openai`, `xai` |
| `src/finterminal/llm/base.py` | `ModelMetadata` + `api_key_env`, `base_url`, `base_url_env` |
| `src/finterminal/llm/registry.py` | Threads the three new fields from YAML |
| `src/finterminal/llm/budget.py` | `_FALLBACK_COSTS`: gpt-5-nano (0.05/0.40), gpt-5-mini (0.25/2.00), gpt-5 (1.25/10.00) |
| `config/models.yaml` | 3 OpenAI models added; Grok moved to `provider: xai` |
| `config/agents.yaml` | Supervisor default unchanged (claude-sonnet-4-6); swap recipes commented |
| `.env.example` | `OPENAI_API_KEY=<your-key>` placeholder added |
| `pyproject.toml` | `openai>=1.60.0` dependency added |
| `tests/test_smoke.py` | 2 new tests; 12/12 pass |

---

## Test coverage

- 12/12 smoke tests pass after addition.
- New tests cover provider resolution (env-var key + base-url override) and alias dispatch.

---

> [!WARNING] Security near-miss
> A real `OPENAI_API_KEY` was briefly pasted into `.env.example` (the committed template) instead of the gitignored `.env`. Caught before any commit; key was rotated. No leak to GitHub.
> **Rule: real keys go in `.env` only — never in `.env.example`.**
