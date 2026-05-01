# Data — mgmt_claims

Maps to: `src/finterminal/data/migrations/006_mgmt_claims.sql` + `src/finterminal/data/duckdb_store.py` (CRUD helpers)

**Related:** [[04 - Code Map/data — duckdb_store]] · [[04 - Code Map/features — compute_quality]]

---

## Overview

Ledger table for tracking management claims (guidance, restructuring, strategic announcements, etc.) tied to equities. Structural foundation for sub-project #6's `signal_success_rate` feature, which will measure claim → actual outcome accuracy.

**Added in:** [[05 - Build Log/2026-05-01 — Sub-project 3 Quality Engine v1]] (Sub-project #3)

**Status in v1:** CRUD only (Create, Read, Upsert, Delete). No NLP extractor. Manual or external pipeline feeds claims into this table.

---

## Schema

**Table:** `mgmt_claims` (migration 006)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, autoincrement | Sequential ID |
| `ticker` | VARCHAR | NOT NULL, FK to fundamentals.ticker | NSE/BSE symbol (e.g., "RELIANCE.NS") |
| `claim_date` | DATE | NOT NULL | When claim was filed/announced |
| `claim_type` | VARCHAR | NOT NULL | Category: "guidance", "restructuring", "dividend", "acquisition", "strategy", etc. |
| `claim_text` | TEXT | NOT NULL | Claim summary (≤500 chars typical; no markup) |
| `claim_source` | VARCHAR | NOT NULL | Origin: "mgmt" (official), "analyst" (consensus), "news" (aggregated) |
| `resolved` | BOOLEAN | DEFAULT FALSE | Outcome recorded (true when resolved_at is not null) |
| `resolved_at` | DATE | NULLABLE | When outcome was recorded |

**Indexes:**
1. `ix_mgmt_claims_ticker_date` — (ticker, claim_date DESC)
2. `ix_mgmt_claims_resolved` — (resolved, resolved_at DESC)

---

## Leakage Rule (Critical)

**Any feature derived from mgmt_claims MUST apply cutoff discipline to prevent look-ahead bias.**

Documented in migration 006 SQL comment:

```sql
-- LEAKAGE RULE:
-- Any FeatureSpec that derives from mgmt_claims must:
--   1. Use as_of date as cutoff: only claims.claim_date <= as_of
--   2. Exclude resolved claims after horizon:
--      WHERE claim_date <= as_of AND (resolved IS FALSE OR resolved_at <= as_of - horizon_days)
-- Without this, claims resolved after the forecast date leak future information.
```

**Example (sub-project #6):**
```
signal_success_rate(ticker, as_of, horizon_days=90):
  SELECT COUNT(CASE WHEN outcome matches claim THEN 1 END) / COUNT(*) as rate
  FROM mgmt_claims
  WHERE ticker = ?
    AND claim_date <= as_of
    AND resolved IS TRUE
    AND resolved_at <= as_of - horizon_days
```

---

## CRUD Helpers

### `insert_mgmt_claim(ticker, claim_date, claim_type, claim_text, claim_source) -> int`

**Returns:** Inserted row ID.

**Behavior:**
- Inserts new row into mgmt_claims
- Auto-increments id
- resolved = FALSE, resolved_at = NULL
- Returns the inserted id for logging

**Error handling:** Raises if ticker not in fundamentals (FK constraint).

---

### `list_mgmt_claims(ticker: str, unresolved_only: bool = False) -> list[dict]`

**Returns:** List of claim dicts with keys: id, claim_date, claim_type, claim_text, claim_source, resolved, resolved_at.

**Behavior:**
- Filters by ticker
- If unresolved_only=True, filters WHERE resolved=FALSE
- Orders by claim_date DESC (most recent first)

**Use case:** Human review, sub-project #6 audit, claim backfill.

---

## Design Rationale

1. **Separate ledger table:** Claims are distinct events with asynchronous resolution. Merging into fundamentals or outcomes tables would require wide nullable columns.

2. **No NLP in v1:** Extraction is complex and error-prone. v1 lays structure; claims are manually entered or piped from a structured source (e.g., NSE announcements API, or earnings call transcripts post-NLP).

3. **Resolved flag + timestamp:** Decoupled resolution tracking allows:
   - Unresolved claims to linger (useful for signal recency)
   - Resolved date separate from claim date (needed for leakage rule: only count resolved claims after observation window)

4. **claim_source enum:** Distinguishes mgmt official guidance ("mgmt") from analyst consensus ("analyst") from news-derived inference ("news"). Sub-project #6 may weight by source.

5. **Leakage rule in SQL comment:** Must be followed by any derived feature. Documented at schema level to catch future developers.

---

## Dependencies

| Dependency | File | Role |
|---|---|---|
| Fundamentals table | Migration 001 | FK target for ticker; claim_date semantically tied to reporting cycles |
| DuckDB connection | `src/finterminal/data/duckdb_store.py` | CRUD implementation; migration applied on first connection |

---

## Future Extensions (Sub-project #6+)

- **NLP extractor:** Parse earnings call transcripts, press releases, analyst notes → auto-populate claims
- **Claim validation:** Cross-reference against outcomes table; compute success_rate signal
- **Claim enrichment:** Sentiment, certainty confidence, claim magnitude (e.g., "dividend 50% hike" vs "dividend cut")
- **Claim clustering:** Group related claims (e.g., multi-phase restructuring) to avoid double-counting

---

## Testing

- `tests/test_mgmt_claims.py` (5 tests)
  - CRUD helpers
  - FK constraint validation
  - Leakage rule documentation

---

## Cross-Links

- **Phase:** [[03 - Phases/Phase 2 - Multi-Agent Foundation]]
- **Build Log:** [[05 - Build Log/2026-05-01 — Sub-project 3 Quality Engine v1]]
- **ADR:** [[02 - Decisions/ADR-019 — Feature Store as the Bridge from Signals to Models]]
