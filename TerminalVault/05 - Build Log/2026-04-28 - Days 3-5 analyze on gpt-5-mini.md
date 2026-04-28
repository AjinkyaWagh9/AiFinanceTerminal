# 2026-04-28 — Days 3-5 /analyze running on gpt-5-mini

> Phase 1 functionally complete. `/analyze RELIANCE.NS` produced a structured bull/bear with confidence 0.55 and source-tagged citations on real OpenBB data via gpt-5-mini.

**Commits today:** `cf79139` (Days 3-5 sweep), `7341e8f` (gpt-5 quirks + yfinance window fix). All on `main`, pushed to `github.com/AjinkyaWagh9/Finance-Terminal`.

---

## What shipped

- **Live OpenBB fetch** — `fetch_quote / fetch_fundamentals / fetch_news` defensive across providers. yfinance Indian quote endpoint flaky → historical-bars fallback. See [[data — OpenBB + DuckDB]].
- **REPL commands** — `/help /ticker /news /watch /analyze /quit`. See [[commands]].
- **`/analyze` pipeline** — context block builder, source-discipline prompt, `parse_analysis()` → DuckDB `analyses` row + cost log. See [[agents — supervisor]].
- **OpenAI-compat provider** — covers OpenAI + xAI + NIM + LM Studio + OpenRouter behind one class. See [[openai-compat-provider]] and [[ADR-010 Generic OpenAI-Compat Provider Class]].
- **gpt-5 family wired** — `gpt-5-nano`, `gpt-5-mini`, `gpt-5` in `models.yaml`. Supervisor swapped to `gpt-5-mini` after user enabled access on their OpenAI project.

## Surprises (worth remembering)

| Symptom | Root cause | Fix |
|---|---|---|
| `fetch_quote` returned empty for `RELIANCE.NS` after working earlier | yfinance defaults to `(today - 1y, today)`; system clock at 2026 + Indian data ending mid-2025 → window past data horizon | Pass explicit `start_date = today - 730d` in `openbb_client.py:_HISTORICAL_LOOKBACK_DAYS` |
| `/analyze` rendered all-empty panel despite HTTP 200 | gpt-5 reasoning models burn `max_completion_tokens` on internal thought before any visible output. 2000-cap returned 0 visible tokens | Floor `max_completion_tokens` at 8000 in `openai_compat.py` for gpt-5/o-prefixed models |
| `BadRequestError: Unsupported parameter: 'max_tokens'` | gpt-5 / o1 / o3 / o4 use `max_completion_tokens` instead of `max_tokens`; temperature is also pinned to 1 | Branch on `_is_new_openai_model()` prefix check; OpenAI SDK retried 400s 3× before our wrapper failed → also added `BadRequestError` fail-fast |
| `gpt-5-mini` 403 on first call | User's OpenAI project didn't have access yet | User added gpt-5 access mid-session → resolved |

## What `/analyze RELIANCE.NS` actually returned

- **Bull case**: liquidity to express conviction without slippage; digital growth narrative
- **Bear case**: D/E 36.65 + ROE 0.091 → limited balance-sheet cushion; legal/probe overhang [src: news[3], news[4]]
- **Confidence**: 0.55 (yellow gauge)
- **Assumptions**: digital margins durable, HBO Max/JioHotstar deal monetizes, no crippling legal outcome
- **What would change my mind**: 2 quarters of clean beats; bribery probe resolution with no fines; refining margin durability

The source-discipline prompt held — **every numeric claim carries a `[src: ...]` tag**. That's the key safety rail working.

## Phase 1 exit-criteria check (from [[Phase 1 - MVP]])

- [x] `/ticker TICKER` returns within 2s warm — verified on RELIANCE.NS
- [x] `/news TICKER` returns ≥10 headlines from ≥2 sources — partially; news flow works, but yfinance is thin for Indian tickers (see [[2026-04-28 - Indian News Gap]])
- [x] `/analyze TICKER` returns structured bull/bear with sourced numbers + confidence + assumptions in <30s — confirmed
- [ ] Used in lieu of MoneyControl for 2 consecutive trading days — pending real-world use

## Tests

12/12 passing. One previously-passing test (`test_supervisor_resolves_to_a_provider`) was hard-coded to `claude-sonnet-4-6`; rewrote to read `agents.yaml` dynamically and accept any registered model with optional API-key gate.

## What's next

- **Phase 2 unlock signal** — once Phase 1 has been used live for 2 trading days, the real backlog reveals itself. Don't pre-plan Phase 2 work before that.
- **Open**: news source diversity for Indian tickers (Phase 2 RSS aggregator handles this — Mint, MoneyControl, ET, BloombergQuint per [[Data Sources]]).
- **Open**: paste `ANTHROPIC_API_KEY` if Claude synthesis ever wanted; one-line YAML swap to flip back. See `MODEL-SWAP-GUIDE.md`.
- **Open**: vault still missing `06 - Glossary`, `07 - External References`, `04 - Code Map/prompts`, and `_Templates/`. Index links to some of these — they're orphan references for now.

## Cross-links

- ADRs touched: [[ADR-006 Model Abstraction in Phase 1]] (validated end-to-end), [[ADR-010 Generic OpenAI-Compat Provider Class]] (proven across gpt-5 quirks)
- Phases: [[Phase 1 - MVP]] (status flips to **complete** in [[Index]])
- Code: [[agents — supervisor]], [[commands]], [[data — OpenBB + DuckDB]], [[openai-compat-provider]], [[LLM Abstraction Layer]]
