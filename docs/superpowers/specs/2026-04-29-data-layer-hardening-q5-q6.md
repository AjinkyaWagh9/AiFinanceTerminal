# Spec — Data-layer hardening: Q-5 (provider fallthrough) + Q-6 (Rich tag escape)

**Date:** 2026-04-29
**Author:** Claude (Opus 4.7)
**Phase:** 4c — Phase 2 hardening before News & Trend agent
**Predecessor:** `2026-04-29-prompt-rewrite-fu2-q1-q2.md`
**Time budget:** 2-3 hrs

---

## 1. Problems

### Q-5 — yfinance throttle kills the entire quote chain

`src/finterminal/data/openbb_client.py:29` declares `_QUOTE_PROVIDERS = ["yfinance"]` — single provider. When yfinance throttles (frequent for `.NS` tickers — happened 2× today on RELIANCE), the historical fallback also fails (same source, same throttle), and `RuntimeError("All providers failed")` propagates up. The `/analyze` command crashes before any LLM call.

**Observed in `input.md:75-88` and live today:**
```
yfinance: $RELIANCE.NS: possibly delisted; no price data found
yfinance: ['RELIANCE.NS']: possibly delisted; no price data found
WARNING ... historical fallback via yfinance failed for RELIANCE.NS:
[Empty] -> No results found
```

`possibly delisted` is yfinance's misleading throttle message — RELIANCE.NS is not delisted.

### Q-6 — Rich panel strips `[src: ...]` tags from rendered output

The Analyst correctly emits `[src: quote.last_price]` in its output (Critic confirms it parses them). But `ui/panels.py` passes the bullet text into Rich's `Text` / `Panel` constructors which interpret `[...]` as style markup. Rich silently drops the unrecognized "style" `src: quote.last_price` and renders the bullet without the tag — the user sees `... PE 19.10  .` (note trailing whitespace before period).

This breaks the user's ability to spot-check the analyst's source discipline. Source-citation UX is a core differentiator.

---

## 2. Goals

1. **Provider fallthrough for quotes.** When yfinance fails on an Indian ticker, fall through to NSE's public API (no auth, no rate limit on small queries). Don't crash if both fail — bubble the real error.
2. **Source tags visibly render.** `[src: quote.last_price]` appears verbatim in the panel, dim-styled, after each bullet's claim.
3. **Regression tests** for both behaviors.

## Non-goals

- Adding US-fallback providers (Stooq, finnhub for quotes) — Phase 3 covers US expansion. Out of scope.
- Refactoring the entire provider chain into a strategy pattern — premature; we have 2 sources, not N.
- Building a full NSE client (only fetch_quote needed; fundamentals stay on yfinance/screener).
- Q-4 fundamentals enrichment (cash flow, segmentals, peer multiples, forward EPS) — separate ADR, separate sprint.

---

## 3. Decisions

### 3.1 NSE source: direct `nseindia.com/api/quote-equity` vs OpenBB-via-NSE

OpenBB doesn't have an NSE provider. Options:
- **A.** Direct HTTP to `https://www.nseindia.com/api/quote-equity?symbol=RELIANCE` (returns JSON, requires a session-cookie warmup — see NSE's own pattern)
- **B.** Use a third-party library (`nsepython`, `nse-python`) — adds a dep we don't control
- **C.** Skip NSE; add Stooq via OpenBB as a global fallback

**Choice: A (direct HTTP).** NSE's API is the authoritative source; no third-party dep adds to maintenance surface. The session-cookie pattern is well-documented and we already use httpx for screener.in. Implementation lives in `src/finterminal/data/india/nse_quote.py` (new module).

**Rationale:** the user's stated priority is "no compromise on data extraction." Stooq is delayed and lossy for Indian quotes; nse-python is a community project with sporadic updates. Direct NSE is the source of truth.

### 3.2 Provider chain order

```
_QUOTE_PROVIDERS = ["yfinance"]        # Phase 1
_QUOTE_PROVIDERS = ["yfinance", "nse"] # New: Phase 2 hardening
```

yfinance stays primary because:
- Works for .NS, .BO, US tickers, EU tickers — universal
- Faster (no session warmup)
- NSE only covers Indian symbols

NSE is fallback ONLY for `.NS` / `.BO` tickers. For US / non-Indian, yfinance failure → real error (no NSE coverage).

### 3.3 Rich tag preservation: escape vs replace

Two ways to keep `[src: ...]` visible:
- **A.** `markup=False` on the Text/Panel — disables ALL Rich markup, kills our color/styling for the panel
- **B.** Escape brackets in user content (`[` → `\[`) so Rich treats them as literal text but keep markup mode for our own styling

**Choice: B.** We need to keep panel borders, severity coloring on the critic block, conviction-arrow color. Escape only the analyst-content bullets.

Implementation: a small `_escape_markup(s: str) -> str` helper that escapes `[` (Rich's documented escape pattern). Apply in `panels.py` everywhere we render LLM-generated text into a `Text` / `Panel` body.

---

## 4. Concrete changes

### 4.1 New module — `src/finterminal/data/india/nse_quote.py`

```python
"""NSE direct quote API. Fallback for yfinance throttle.

NSE requires a session cookie before serving the API; first GET to
nseindia.com warms it up. Standard pattern. We re-use a single httpx
client across calls to amortize the warmup.
"""
def fetch_nse_quote(symbol: str) -> dict:
    """Returns the same dict shape as openbb_client.fetch_quote.
    Raises NSEQuoteError on auth/network/parse failure."""
```

Returns the same dict shape as `fetch_quote`:
```python
{
    "ticker": ticker,                  # the original input (e.g. RELIANCE.NS)
    "as_of": <datetime utc>,
    "last_price": float,
    "change_pct": float | None,
    "volume": int | None,
    "market_cap": int | None,         # NSE returns this in their priceInfo block
    "provider": "nse",
    "raw": <full nse json>,
}
```

**Symbol mapping:** strip `.NS` / `.BO` to get the bare NSE symbol (`RELIANCE.NS` → `RELIANCE`).

**Session warmup:** `GET https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE` first to seed cookies, then `GET /api/quote-equity?symbol=RELIANCE`. User-Agent must look like a browser — NSE blocks default httpx UA.

**Field mapping** from NSE response:
- `last_price` ← `priceInfo.lastPrice`
- `change_pct` ← `priceInfo.pChange`
- `volume` ← `marketDeptOrderBook.tradeInfo.totalTradedVolume` OR `priceInfo.totalTradedVolume`
- `market_cap` ← `securityInfo.issuedCap * priceInfo.lastPrice` OR a direct field if present

### 4.2 Wire into `openbb_client.fetch_quote`

```python
_QUOTE_PROVIDERS = ["yfinance", "nse"]
```

Loop unchanged but add NSE branch:

```python
for provider in _QUOTE_PROVIDERS:
    if provider == "nse":
        if not _is_indian_ticker(ticker):
            continue
        try:
            from .india.nse_quote import fetch_nse_quote
            return fetch_nse_quote(ticker)
        except Exception as exc:
            last_err = exc
            logger.warning("quote fetch via nse failed for %s: %s", ticker, exc)
            continue
    # ... existing yfinance branch ...
```

### 4.3 `ui/panels.py` — escape markup in LLM-generated content

```python
def _escape_markup(s: str) -> str:
    """Escape Rich markup brackets so [src: ...] tags render literally."""
    return s.replace("[", r"\[")
```

Apply it in:
- `format_quote_for_context` / `format_fundamentals_for_context` — wait, those go INTO the analyst, not OUT of it. Skip.
- The analyst-output renderers in `analysis_panel`. Find every place we pass `analyst_payload["bull_case"]`, `analyst_payload["bear_case"]`, `analyst_payload["assumptions"]`, `analyst_payload["what_would_change"]`, `analyst_payload["variant_perception"]`, `critic_payload["issues_md"]`, `critic_payload["missing_md"]` into a `Text(...)` / `Panel(body)` and wrap with `_escape_markup`.

But preserve our intentional styling (`[bold]...[/]`, `[dim]...[/]`). Solution: escape user content separately, then concat with our own markup strings:
```python
Text.from_markup("[bold]Bull[/bold]\n" + _escape_markup(bull_md))
```

### 4.4 New tests

**`tests/data/test_nse_quote.py`** — mock httpx, verify request shape + response parse + error mapping.

**`tests/data/test_quote_fallthrough.py`** — patch yfinance to raise, patch nse to succeed, verify `fetch_quote` returns NSE result without raising.

**`tests/ui/test_panels_markup_escape.py`** — render a panel with bullet text containing `[src: quote.last_price]`, assert the rendered output (via Rich's `Console.export_text()`) contains the literal substring `[src: quote.last_price]`.

---

## 5. Rollout (commit plan)

1. `test: add nse_quote + quote-fallthrough + markup-escape regression tests (red)`
2. `feat(data): NSE direct quote API as yfinance fallback (Q-5)`
3. `fix(ui): escape Rich markup in LLM content so [src: ...] tags render (Q-6)`
4. `chore: smoke-verify Q-5 + Q-6 via /analyze RELIANCE` — vault-only

---

## 6. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| NSE blocks our User-Agent / IP | Medium | Use realistic UA, single-session keep-alive, exponential backoff on 429. If NSE still blocks, fall through to next provider — yfinance was already that fallback. Order is yfinance → NSE; on .NS we now have 2 sources where Phase 1 had 0 working ones. |
| NSE response shape changes | Low | Field mapping is small (4 fields). Snapshot one response in `tests/data/fixtures/nse_quote_RELIANCE.json` and parse it in tests. |
| Rich markup escape breaks our intentional styling | Medium | Apply escape ONLY to LLM-generated content variables. Keep `Text.from_markup` for our hand-crafted markup strings. Test suite includes a render-and-export test that asserts both the escaped tag AND the bold styling are present. |
| Q-6 fix touches every analyst-output renderer in panels.py | High | Bound the change: one helper function + a list of variables to wrap. Surgical not architectural. |

---

## 7. Done criteria

- [ ] All 4 commits land green
- [ ] `uv run pytest -q` passes (target: 110+ tests, currently 104)
- [ ] `uv run ruff check src tests` clean
- [ ] Manual smoke `/analyze RELIANCE` works even when yfinance is throttled (test by killing internet briefly OR running through a known-throttled timeframe)
- [ ] Panel output for `/analyze ITC` shows `[src: quote.last_price]` literally on bullets, dim-styled
- [ ] Vault build-log entry committed
