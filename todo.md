# TODO — Sub-project #3: Quality Engine v1

**Status:** Planning pending (next session)
**Predecessor:** Sub-project #5 (Feature Store) — COMPLETE. 266 tests passing on `main`.
**Roadmap ref:** ADR-019 `TerminalVault/02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models.md`

---

## What this sub-project ships

Quality Engine v1 lights up the four `#3` placeholders in `features/registry.py`:

| Feature | Type | Currently |
|---------|------|-----------|
| `roe` | fundamentals | `is_missing=true` placeholder |
| `leverage` | fundamentals | `is_missing=true` placeholder |
| `earnings_growth` | fundamentals | `is_missing=true` placeholder |
| `quality_score` | derived from above | `is_missing=true` placeholder |

And introduces a new `mgmt_claims` ledger — a table that records discrete claims made by management in earnings calls / press releases / news stories (e.g. "we will double revenue in 2 years"), with a follow-up outcome column filled when the claim horizon passes.

---

## Architecture context

### Where quality_score fits in the feature vector

`emit_signal` (in `outcomes/ledger.py`) calls `features/orchestrator.py:compute_for_signal`, which returns the full 18-key dict. The four `#3` features currently come back as `{"value": None, "is_missing": True}` because `PLACEHOLDER_NAMES` short-circuits them. After #3:

1. A new `features/compute_quality.py` replaces the placeholder logic for those four names.
2. Fundamentals data (`roe`, `leverage`, `earnings_growth`) is sourced — either from a new `fundamentals_eod` table (screener-style data, quarterly cadence) or derived from available NSE filing data.
3. `quality_score` is a weighted composite z-score of the three fundamentals (or a logistic output — TBD in spec).

### mgmt_claims ledger

A new table `mgmt_claims (claim_id, ticker, claimed_at, claim_text, horizon_days, outcome_date, outcome_verified BOOLEAN, source_ref)`. This is the structural building block for the `signal_success_rate` feature planned in #6. For #3, the ledger just needs to exist and be writable.

**Leakage rule (from ADR-019 fix #3):** any historical-success feature derived from `mgmt_claims` must use an `as_of` cutoff and exclude claims that resolved after `as_of - horizon_days`.

### Pipeline isolation stays the same (D9)

`market_data/`, `outcomes/`, `news/` may not import `features/` at module top level. The AST-walk guard in `tests/test_pipeline_isolation.py` enforces this. #3 adds code only inside `features/` (and possibly a new migration), so no D9 changes needed.

---

## Dependencies

- `feature/feature-store` work merged to `main` ✅
- `signal_features` table exists (migration 005) ✅
- `features/registry.py` already has the 4 placeholder slots ✅
- Fundamentals data source — **needs decision during planning**: scrape NSE filings vs. third-party API vs. manual seed for now
- `mgmt_claims` — new migration (006) needed

---

## Key files to read before planning

```
src/finterminal/features/registry.py          # see PLACEHOLDER_NAMES + the 4 #3 slots
src/finterminal/features/orchestrator.py      # how to add a new compute block
src/finterminal/features/compute_price.py     # pattern to copy for compute_quality.py
src/finterminal/features/freshness.py         # D12 gate pattern (apply to fundamentals too)
src/finterminal/data/duckdb_store.py          # migration list — add 006 after 005
src/finterminal/outcomes/ledger.py            # emit_signal — no changes expected in #3
tests/features/test_atomicity.py              # existing atomicity tests must still pass
tests/test_pipeline_isolation.py              # AST guard — must cover any new modules
```

---

## Open questions for planning session

1. **Fundamentals data source:** Where does `roe` / `leverage` / `earnings_growth` come from? Options:
   - New `fundamentals` table seeded from NSE quarterly filings (screener.in export or manual)
   - Compute from `prices_eod` proxies (not ideal — price-based only)
   - Placeholder-but-structured: create the table + migration, seed test data, wire compute but leave prod ingestion as a follow-up
2. **quality_score formula:** Simple weighted z-sum? Or expose all three individually and let model #6 learn the weight?
3. **mgmt_claims scope for v1:** Do we need an NLP extractor in #3, or just the ledger schema + manual insert + the outcome-tracking logic?
4. **Freshness gate for fundamentals (D12 extension):** Quarterly data is always "stale" by daily standards — need a new `MAX_FUNDAMENTALS_STALENESS_DAYS` constant (e.g. 120 = one quarter).

---

## Model-selection rule (unchanged from #5)

| Model | When |
|-------|------|
| **Haiku** | Single-file, plan-spelled-out, mechanical (migration, registry edit, simple helpers) |
| **Sonnet** | Multi-file, requires reading existing code, integration wiring, end-to-end tests |
| **Opus** | Final review only |

## Branch discipline (unchanged from #5)

- Cut branch from current `main` head.
- One implementer subagent per task.
- Never push, never amend; commit messages match the plan verbatim.
- Reviewer = Haiku, combined spec+quality, after each task.

---

## Test baseline

Run before starting any task:

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal
uv run pytest -q --tb=no
# expect: 266 passed
```

Target after #3: ~290+ (new fundamentals store tests + compute_quality tests + mgmt_claims tests).
