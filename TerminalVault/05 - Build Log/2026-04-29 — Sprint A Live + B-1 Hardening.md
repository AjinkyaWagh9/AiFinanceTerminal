# 2026-04-29 — Sprint A Live-Verified + Sprint B-1 Data-Layer Hardening (Q-5 + Q-6)

**TL;DR:** Sprint A (Ollama provider, commit `53abea9`) is now live-verified end-to-end against real qwen3.5:9b running on M4 Air. Sprint B-1 shipped three commits hardening the data layer: NSE direct quote fallback (Q-5) and Rich markup escaping for `[src: ...]` tags (Q-6). Live smoke on `/analyze ITC` at 12:37 confirmed both fixes hold under real throttle conditions. Tests: 104 → 123 (+19). Q-7 logged for backlog.

**Predecessors (same day):**
- [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]]
- [[05 - Build Log/2026-04-29 — C Sprint (FU-2 Q-1 Q-2 Smoke Green)]]

**Spec:** `docs/superpowers/specs/2026-04-29-data-layer-hardening-q5-q6.md`

---

## Sprint A — Live Verification (Ollama Provider)

**Commit:** `4ea88f9` feat(llm): register qwen3.5:9b + gemma4:e4b; live-verify Ollama provider

| Model | Size | Status |
|---|---|---|
| `qwen3.5:9b` | 6.6 GB | Pulled + live-verified (46 s cold start; ~1–3 s warm) |
| `gemma4:e4b` | 9.6 GB | Pulled; available as second mid-tier option |

**What changed from unit-test to live:**
- Previous state: `OllamaProvider` (`53abea9`) was verified only via mocked-HTTP unit tests — live smoke was deferred because no qwen model was pulled.
- Today: user pulled both models on M4 Air 16 GB.
- Live smoke test passed against `qwen3.5:9b` — 46 s on cold start (model load); warm calls expected ~1–3 s.
- Test bumped `max_tokens` 10 → 256 to give visible output room (qwen3.x burns tokens on internal thought before visible output — same reasoning-tier pattern as gpt-5 thinking).

**Key notes:**
- `gemma4:e4b` is 9.6 GB despite the "e4b" tag suggesting "efficient 4B" — it is NOT a fast classifier; it's a second mid-tier option.
- Fast-classifier role (Phase 2.5 Quality / Macro / Calendar / Ownership per PLAN.md §6.5.5) has no candidate model pulled yet — phi-class or qwen2.5:3b deferred pending actual latency requirements.
- Cloud agents (Analyst, Critic) keep OpenAI defaults — local routing is opt-in via `agents.yaml`; Sprint A delivered infrastructure, not a routing change.

---

## Sprint B-1 — Data-Layer Hardening Commits

| SHA | Type | Summary |
|---|---|---|
| `cc16a01` | test | Add NSE quote + quote-fallthrough + markup-escape regression tests (red) — 19 new tests |
| `bc269cb` | feat(data) | NSE direct quote API as yfinance fallback (Q-5) — new `data/india/nse_quote.py`; `_QUOTE_PROVIDERS = ["yfinance", "nse"]` chain |
| `0b5e723` | fix(ui) | Escape Rich markup in LLM content so `[src: ...]` tags render (Q-6) — `_escape_markup()` in `ui/panels.py` |

---

## Q-5 — NSE Quote Fallthrough

**Root cause:** `_QUOTE_PROVIDERS = ["yfinance"]` in `openbb_client.py:29`. When yfinance throttled (multiple times on `RELIANCE.NS`), the entire quote chain bailed with `EmptyDataError`. Both the live quote endpoint and the historical-bars fallback share yfinance — the "fallback" was not a real fallback.

**Fix:**
- New module `src/finterminal/data/india/nse_quote.py`
- Talks to NSE's public `/api/quote-equity` endpoint via httpx
- Two-step session warmup: browser-like User-Agent required — NSE blocks default httpx UA
- `fetch_quote()` chain now: `["yfinance", "nse"]`; NSE fires only for `.NS` / `.BO` tickers

**NSE field mapping:**

| Return field | NSE JSON path |
|---|---|
| `last_price` | `priceInfo.lastPrice` |
| `change_pct` | `priceInfo.pChange` |
| `volume` | `priceInfo.totalTradedVolume` → fallback `marketDeptOrderBook.tradeInfo.totalTradedVolume` |
| `market_cap` | `marketDeptOrderBook.tradeInfo.totalMarketCap` × 100,000 (lakhs → rupees) → fallback `securityInfo.issuedSize × lastPrice` |

---

## Q-6 — Rich Markup Escaping

**Root cause:** Rich's `Panel(string)` constructor interprets bracketed text as style markup and silently strips unknown styles. The Analyst correctly emitted `[src: quote.last_price]` citations but they vanished in the rendered panel — breaking source-discipline UX.

**Fix:**
- `_escape_markup()` helper added at `ui/panels.py:13` — escapes `[` to `\[`
- Applied to: `variant_perception`, `bull_case`, `bear_case`, `assumptions`, `what_would_change`
- Critic block unchanged — `Text.append()` already treats input as plain text

---

## Live Smoke — `/analyze ITC` (12:37 today)

| Signal | Expected | Observed |
|---|---|---|
| Q-6 tag rendering | `[src: ...]` literals visible in panel | Every bullet shows literal `[src: fundamentals.roce]`, `[src: fundamentals.net_income_ttm]`, `[src: quote.change_pct]`, `[src: news[0]]` — multiple tags per bullet |
| Q-5 fallthrough | yfinance throttle does not kill analysis | yfinance failed (`curl: (28) Connection timed out`); analysis completed with correct ITC numbers via NSE fallthrough |
| Conglomerate guard | Fires for ITC (diversified) | Confidence 0.50; Assumptions cites "Conglomerate guard (segmental P&L not in SOURCES)" with all 5 ITC segments named |
| Critic calibration | ≤2 HIGH | 0 HIGH, 2 MEDIUM (FCF unsourced, margin sustainability), 3 LOW |

---

## Test Count

| State | Count |
|---|---|
| Before Sprint B-1 | 104 |
| After Sprint B-1 | 123 |
| New tests | +19 |

---

## Q-7 — Analyst Confidence-Cap Wording (Backlog)

Surfaced by the ITC Critic: `prompts/analyst.md` says "Cap your `Confidence` at 0.55" — model chose 0.50 (correct; cap = ceiling, not target). Critic flagged it as a small inconsistency.

**Queued fix:** change "Cap your `Confidence` at 0.55" → "Confidence may not exceed 0.55" in `prompts/analyst.md`. Small prompt tweak; not blocking; deferred to Phase 2.5 prompt-tuning batch.

Tracked in [[03 - Phases/Phase 2 - Multi-Agent Foundation]] backlog.

---

## Files Affected

| File | Change |
|---|---|
| `src/finterminal/data/india/nse_quote.py` | New — NSE direct quote provider |
| `src/finterminal/data/openbb_client.py:29` | `_QUOTE_PROVIDERS = ["yfinance", "nse"]`; extracted `_fetch_via_yfinance()` |
| `src/finterminal/ui/panels.py:13` | `_escape_markup()` helper added; applied to 5 LLM fields |
| `tests/data/test_nse_quote.py` | New — NSE quote unit tests |
| `tests/data/test_quote_fallthrough.py` | New — provider chain fallthrough tests |
| `tests/ui/test_markup_escape.py` | New — markup escape regression tests |
| `config/models.yaml` | `qwen3.5:9b` + `gemma4:e4b` registered (commit `4ea88f9`) |
| `tests/llm/test_ollama_provider.py` | `max_tokens` bumped 10 → 256 for reasoning-tier models |

---

## Cross-Links

- Predecessors (same day): [[05 - Build Log/2026-04-29 — 4a Scaffold Smoke + Post-Smoke Fixes]] · [[05 - Build Log/2026-04-29 — C Sprint (FU-2 Q-1 Q-2 Smoke Green)]]
- Phase: [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- ADR: [[02 - Decisions/ADR-012 Custom Indian Data Layer]] · [[02 - Decisions/ADR-015 Provider Chain Pattern for Fallthrough]]
- Code map: [[04 - Code Map/data — india — nse_quote]] · [[04 - Code Map/data — OpenBB + DuckDB]] · [[04 - Code Map/ui — Rich-Textual]] · [[04 - Code Map/llm — abstraction layer]]
- Spec: `docs/superpowers/specs/2026-04-29-data-layer-hardening-q5-q6.md`
