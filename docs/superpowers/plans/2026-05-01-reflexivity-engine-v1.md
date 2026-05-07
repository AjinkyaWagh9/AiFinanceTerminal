# Reflexivity Engine v1 Implementation Plan (Fixed)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the three sentiment placeholder FeatureSpecs in the feature store, add `entropy_change` and `feature_health` as new features, and harden the feature layer for *evolution*: feature versioning, freeze-on-write, ingestion-time snapshot, and a swappable sentiment model. After this plan, the ML pipeline (Sub-project #5) sees five stable, deterministic, version-tagged reflexivity features per signal.

**Why this revision (vs. earlier draft):** The earlier plan produced correct values for *today's* model, but locked itself to VADER, allowed silent overwrites, and used `published_at <= ts` only — exposing the system to ingestion-time leakage and unversioned drift. This plan fixes all seven gaps from `input.md`:

| Gap from input.md | Fix |
|---|---|
| Hardcoded VADER | `_sentiment_model(text)` wrapper — swap to FinBERT later with zero callsite changes |
| No reproducible evolution | `feature_version` column + `FEATURE_VERSION` constant per row |
| No feature lifecycle / freeze | upsert refuses overwrite when version matches existing row |
| Ingestion-time leakage | fetch query: `published_at <= ts AND fetched_at <= ts` |
| No z-norm activation rule | `normalized` boolean flag (always `False` in v1; activator lives in #5) |
| No feature health metric | `feature_health = confidence * (1 - entropy_sentiment)` as 5th feature |
| No debug traceability | compute functions return a `debug` dict (`mean_score`, `std`, `unique_ratio`); not persisted in v1, available for in-memory inspection |

**Architecture:** A new `compute_reflexivity.py` module reads from `news_stories` using **snapshot + ingestion** semantics (`published_at <= ts_emitted AND fetched_at <= ts_emitted`), scores each headline through `_sentiment_model()` (VADER wrapper today, swap path tomorrow), and emits cells tagged with `FEATURE_VERSION = "reflexivity_v1_vader_decay_0.5"`. Migration 007 extends `signal_features` with `n_samples`, `confidence`, `feature_version`, `normalized`. `upsert_features` enforces freeze-on-write: rows with a matching `(signal_id, feature_name, feature_version)` triple are NOT overwritten — protecting historical truth.

**Build order (correct):** schema → freeze enforcement → compute functions → wiring. Compute logic is the *last* thing built because the schema/store contract is what the ML layer depends on.

**Tech Stack:** Python 3.11, DuckDB 1.5+, `vaderSentiment 3.3.2`, `numpy` (already in deps), `statistics` (stdlib).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `finterminal/pyproject.toml` | Modify | Add `vaderSentiment>=3.3.2` |
| `src/finterminal/data/migrations/007_reflexivity.sql` | Create | Add `n_samples`, `confidence`, `feature_version`, `normalized` to `signal_features` |
| `src/finterminal/features/store.py` | Modify | Extend `FeatureCell` + add freeze-on-write + version-aware upsert |
| `src/finterminal/features/compute_reflexivity.py` | Create | `_sentiment_model()` wrapper + 5 compute functions + helpers |
| `src/finterminal/features/registry.py` | Modify | Promote 4 placeholders + add `entropy_change` + `feature_health` |
| `src/finterminal/features/orchestrator.py` | Modify | Reflexivity block (5 features, ordered so `feature_health` reads `entropy_sentiment`) |
| `tests/features/test_store.py` | Modify | Add n_samples/confidence/version round-trip + freeze tests |
| `tests/features/test_compute_reflexivity.py` | Create | ~25 tests covering all compute functions + ingestion-time + version stamping |
| `tests/features/test_orchestrator.py` | Modify | Update key-count to 20; add reflexivity-present + feature_health tests |

---

## Task 1: Dependency + Migration (schema first)

**Files:**
- Modify: `finterminal/pyproject.toml`
- Create: `src/finterminal/data/migrations/007_reflexivity.sql`

- [ ] **Step 1: Add vaderSentiment to pyproject.toml**

Open `finterminal/pyproject.toml`. In the `dependencies` list, after `"scipy>=1.13.0"`, add:

```toml
"vaderSentiment>=3.3.2",
```

- [ ] **Step 2: Install the new dependency**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal
uv sync
```

Expected: resolves and installs `vaderSentiment`. No errors.

- [ ] **Step 3: Verify import works**

```bash
python -c "from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Create migration 007**

Create `src/finterminal/data/migrations/007_reflexivity.sql` with:

```sql
-- Sub-project #4: Reflexivity Engine v1.
-- Quality + evolution columns on signal_features.
--   n_samples / confidence : ML layer (#5) weights features by data quality.
--   feature_version        : per-row stamp; required for safe model upgrade
--                             (e.g. VADER -> FinBERT) and for backtest replay.
--   normalized             : z-norm activation flag; always FALSE in v1.
--                             Activator lives in #5 once 30-signal history is built.
-- NULL is intentional for non-reflexivity rows; price/regime features have
-- no meaningful sample count.
ALTER TABLE signal_features ADD COLUMN n_samples INTEGER;
ALTER TABLE signal_features ADD COLUMN confidence DOUBLE;
ALTER TABLE signal_features ADD COLUMN feature_version VARCHAR;
ALTER TABLE signal_features ADD COLUMN normalized BOOLEAN DEFAULT FALSE;
```

- [ ] **Step 5: Verify migration runs cleanly**

```bash
python -c "
from finterminal.data.duckdb_store import connect
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    conn = connect(os.path.join(d, 't.duckdb'))
    cols = conn.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='signal_features'\").fetchall()
    names = [c[0] for c in cols]
    for required in ('n_samples', 'confidence', 'feature_version', 'normalized'):
        assert required in names, f'missing {required} in {names}'
    print('migration ok:', names)
"
```

Expected: all four new columns present.

- [ ] **Step 6: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL
git add finterminal/pyproject.toml finterminal/src/finterminal/data/migrations/007_reflexivity.sql
git commit -m "$(cat <<'EOF'
feat(#4): vaderSentiment dep + migration 007 — n_samples/confidence/feature_version/normalized

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Extend FeatureCell + Freeze-on-Write Upsert

**Files:**
- Modify: `src/finterminal/features/store.py`
- Modify: `tests/features/test_store.py`

**Context:** This task hardens the write path *before* any reflexivity compute exists. Two contracts:
1. Cells may carry `n_samples`, `confidence`, `feature_version`, `normalized` (all optional).
2. **Freeze-on-write:** if a row already exists with a matching `feature_version`, the upsert is a no-op (preserves historical truth). A *different* version overwrites — that's how we evolve.

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/features/test_store.py`:

```python
def test_upsert_stores_n_samples_confidence_version(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.25, "is_missing": False,
                            "n_samples": 8, "confidence": 0.8,
                            "feature_version": "reflexivity_v1_vader_decay_0.5",
                            "normalized": False},
    })
    row = conn.execute(
        "SELECT feature_value, is_missing, n_samples, confidence, feature_version, normalized "
        "FROM signal_features WHERE signal_id='sig1' AND feature_name='sentiment_level'",
    ).fetchone()
    assert row == (0.25, False, 8, 0.8, "reflexivity_v1_vader_decay_0.5", False)


def test_upsert_stores_none_for_non_reflexivity_features(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {
        "mom_7d": {"value": 0.05, "is_missing": False},
    })
    row = conn.execute(
        "SELECT n_samples, confidence, feature_version FROM signal_features "
        "WHERE signal_id='sig1' AND feature_name='mom_7d'",
    ).fetchone()
    assert row == (None, None, None)


def test_upsert_freeze_same_version_does_not_overwrite(tmp_path):
    """Same (signal_id, feature_name, feature_version) → upsert is no-op.
    Protects historical truth from accidental recompute."""
    conn = connect(str(tmp_path / "t.duckdb"))
    v = "reflexivity_v1_vader_decay_0.5"
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.25, "is_missing": False,
                            "n_samples": 5, "confidence": 0.5,
                            "feature_version": v},
    })
    # Attempt to overwrite with same version, different value
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.99, "is_missing": False,
                            "n_samples": 99, "confidence": 1.0,
                            "feature_version": v},
    })
    row = conn.execute(
        "SELECT feature_value, n_samples FROM signal_features "
        "WHERE signal_id='sig1' AND feature_name='sentiment_level'",
    ).fetchone()
    assert row == (0.25, 5), "freeze violated: same-version write must not overwrite"


def test_upsert_different_version_overwrites(tmp_path):
    """Different feature_version → overwrite allowed. That's how we evolve VADER → FinBERT."""
    conn = connect(str(tmp_path / "t.duckdb"))
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.25, "is_missing": False,
                            "n_samples": 5, "confidence": 0.5,
                            "feature_version": "reflexivity_v1_vader_decay_0.5"},
    })
    upsert_features(conn, "sig1", {
        "sentiment_level": {"value": 0.42, "is_missing": False,
                            "n_samples": 7, "confidence": 0.7,
                            "feature_version": "reflexivity_v2_finbert"},
    })
    row = conn.execute(
        "SELECT feature_value, n_samples, feature_version FROM signal_features "
        "WHERE signal_id='sig1' AND feature_name='sentiment_level'",
    ).fetchone()
    assert row == (0.42, 7, "reflexivity_v2_finbert")
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal
python -m pytest tests/features/test_store.py -v 2>&1 | tail -25
```

Expected: 4 new tests FAIL — n_samples/version columns + freeze logic not implemented.

- [ ] **Step 3: Replace store.py with version-aware, freeze-enforcing upsert**

Replace the entire content of `src/finterminal/features/store.py` with:

```python
from __future__ import annotations
from typing import TypedDict
import duckdb


class FeatureCell(TypedDict, total=False):
    value: float | None
    is_missing: bool
    n_samples: int | None
    confidence: float | None
    feature_version: str | None
    normalized: bool


def upsert_features(conn: duckdb.DuckDBPyConnection,
                    signal_id: str,
                    features: dict[str, FeatureCell]) -> None:
    """Version-aware upsert with FREEZE-ON-WRITE semantics.

    Rule: if a row with matching (signal_id, feature_name, feature_version)
    already exists, this call is a no-op for that feature. A *different*
    feature_version overwrites — that is the model-evolution path.
    Cells without a feature_version (legacy / non-reflexivity features)
    overwrite as before.
    """
    if not features:
        return
    rows = [
        (
            signal_id,
            name,
            cell.get("value"),
            cell.get("is_missing", True),
            cell.get("n_samples"),
            cell.get("confidence"),
            cell.get("feature_version"),
            cell.get("normalized", False),
        )
        for name, cell in features.items()
    ]
    # Freeze-on-write is enforced via WHERE clause on UPDATE: only allow
    # overwrite when the existing row has NULL feature_version (legacy)
    # or a DIFFERENT feature_version (evolution). Same version → no-op.
    conn.executemany(
        """
        INSERT INTO signal_features
            (signal_id, feature_name, feature_value, is_missing,
             n_samples, confidence, feature_version, normalized)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (signal_id, feature_name) DO UPDATE SET
            feature_value   = EXCLUDED.feature_value,
            is_missing      = EXCLUDED.is_missing,
            n_samples       = EXCLUDED.n_samples,
            confidence      = EXCLUDED.confidence,
            feature_version = EXCLUDED.feature_version,
            normalized      = EXCLUDED.normalized
        WHERE signal_features.feature_version IS DISTINCT FROM EXCLUDED.feature_version
        """,
        rows,
    )
```

- [ ] **Step 4: Run tests to confirm passing**

```bash
python -m pytest tests/features/test_store.py -v
```

Expected: all tests pass (legacy + 4 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL
git add finterminal/src/finterminal/features/store.py finterminal/tests/features/test_store.py
git commit -m "$(cat <<'EOF'
feat(#4): freeze-on-write upsert + version/n_samples/confidence on FeatureCell

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: compute_sentiment_level (with model-swap wrapper + ingestion-time fix)

**Files:**
- Create: `src/finterminal/features/compute_reflexivity.py`
- Create: `tests/features/test_compute_reflexivity.py`

**Context:** `sentiment_level` is the recency-weighted mean of `_sentiment_model(headline)` over articles tagged to `ticker` whose `published_at` AND `fetched_at` are both `<= ts_emitted` (window: 7 days). Returns `(None, True)` when the data quality gate rejects the window. Every cell carries `FEATURE_VERSION` and a `debug` dict for inspection.

- [ ] **Step 1: Write the failing tests**

Create `tests/features/test_compute_reflexivity.py`:

```python
from __future__ import annotations
import math
from datetime import datetime, timedelta

import pytest

from finterminal.data.duckdb_store import connect

TS = datetime(2026, 5, 1, 10, 0)
EXPECTED_VERSION = "reflexivity_v1_vader_decay_0.5"


def _seed_story(conn, headline: str, pub_at: datetime,
                ticker: str = "TCS", fetched_at: datetime | None = None) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO news_stories
            (id, url, source, headline, body, published_at, fetched_at, tickers, sectors)
        VALUES (?, ?, 'test', ?, NULL, ?, ?, ?, [])
        """,
        [headline, f"http://x/{headline[:30]}", headline, pub_at,
         fetched_at if fetched_at is not None else pub_at, [ticker]],
    )


# ── sentiment_level ──────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import (
    compute_sentiment_level,
    FEATURE_VERSION,
)


def test_sentiment_level_version_constant_matches_expected():
    assert FEATURE_VERSION == EXPECTED_VERSION


def test_sentiment_level_missing_when_no_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True and cell["value"] is None
    assert cell["feature_version"] == FEATURE_VERSION


def test_sentiment_level_missing_when_fewer_than_5_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    for i in range(4):
        _seed_story(conn, f"good news {i}", TS - timedelta(days=i))
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_sentiment_level_returns_value_with_5_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    for i in range(5):
        _seed_story(conn, f"strong profit growth rally {i}", TS - timedelta(hours=i * 12))
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is False
    assert isinstance(cell["value"], float)
    assert cell["n_samples"] == 5
    assert cell["confidence"] == pytest.approx(0.5)
    assert cell["feature_version"] == FEATURE_VERSION
    assert cell["normalized"] is False
    assert "debug" in cell


def test_sentiment_level_confidence_caps_at_1(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    for i in range(12):
        _seed_story(conn, f"strong profit growth {i}", TS - timedelta(hours=i * 6))
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["confidence"] == pytest.approx(1.0)


def test_sentiment_level_ignores_future_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    for i in range(5):
        _seed_story(conn, f"strong profit {i}", TS - timedelta(hours=i * 12))
    cell_before = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    for i in range(10):
        _seed_story(conn, f"crash bankruptcy crisis {i}", TS + timedelta(days=i + 1))
    cell_after = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell_before["value"] == pytest.approx(cell_after["value"])


def test_sentiment_level_excludes_late_arriving_articles(tmp_path):
    """Article published BEFORE ts but FETCHED AFTER ts must be excluded.
    Without this, ingestion-time leakage poisons replay."""
    conn = connect(str(tmp_path / "t.duckdb"))
    # 5 valid articles (published+fetched before ts)
    for i in range(5):
        _seed_story(conn, f"strong profit {i}", TS - timedelta(hours=i * 12))
    cell_clean = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)

    # Now insert "late-arriving" articles: published BEFORE ts (eligible by
    # naive snapshot) but fetched AFTER ts. They must NOT change the value.
    for i in range(20):
        _seed_story(
            conn,
            f"hidden disaster bankruptcy crash {i}",
            pub_at=TS - timedelta(hours=1),
            fetched_at=TS + timedelta(days=1 + i),
        )
    cell_with_late = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell_clean["value"] == pytest.approx(cell_with_late["value"]), (
        "late-arriving articles leaked into snapshot — fetched_at filter missing")


def test_sentiment_level_ignores_other_tickers(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    for i in range(5):
        _seed_story(conn, f"strong profit {i}", TS - timedelta(hours=i * 12), ticker="INFY")
    cell = compute_sentiment_level(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL/finterminal
python -m pytest tests/features/test_compute_reflexivity.py -v 2>&1 | tail -10
```

Expected: ImportError — module doesn't exist yet.

- [ ] **Step 3: Create compute_reflexivity.py with sentiment_model wrapper + sentiment_level**

Create `src/finterminal/features/compute_reflexivity.py`:

```python
"""Reflexivity feature compute layer.

Architecture notes (from input.md review):
  * `_sentiment_model(text)` is the only callsite that knows about VADER.
    Swap to FinBERT later by replacing the body — zero changes upstream.
  * Every emitted cell carries `feature_version`. The ML layer uses this
    to compare model generations and avoid mixing distributions.
  * Fetch query enforces BOTH `published_at <= ts` AND `fetched_at <= ts`
    to defend against ingestion-time leakage.
  * `normalized` is always False in v1; z-norm activator lives in #5.
"""
from __future__ import annotations
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

import duckdb
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Public — the ML layer reads this for comparability.
FEATURE_VERSION = "reflexivity_v1_vader_decay_0.5"

_vader = SentimentIntensityAnalyzer()

_DECAY_LAMBDA = 0.5
_MIN_ARTICLES = 5
_MIN_UNIQUE_RATIO = 0.7
_MIN_SCORE_STD = 0.05
_MAX_AGE_DAYS = 7
_CONFIDENCE_SCALE = 10
_WINDOW_DAYS = 7


def _sentiment_model(text: str) -> float:
    """Single point of model dependency. Returns a compound score in [-1, 1].

    Today: VADER. Tomorrow: FinBERT / hybrid. To swap, replace this body
    and bump FEATURE_VERSION above. No other code in the project should
    import a sentiment library directly.
    """
    return _vader.polarity_scores(text)["compound"]


@dataclass
class _Article:
    headline: str
    compound: float
    age_days: float


def _fetch_articles(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    start: datetime,
    end: datetime,
) -> list[_Article]:
    """Snapshot + ingestion-safe fetch.

    `published_at <= end` keeps only articles dated in-window.
    `fetched_at  <= end` excludes late-arriving articles whose ingestion
    timestamp is *after* the signal — they didn't exist in the system
    when the signal was emitted, so they cannot inform it.
    """
    rows = conn.execute(
        """
        SELECT headline, published_at
        FROM news_stories
        WHERE list_contains(tickers, ?)
          AND published_at >= ?
          AND published_at <= ?
          AND published_at IS NOT NULL
          AND fetched_at   <= ?
        ORDER BY published_at DESC
        """,
        [ticker, start, end, end],
    ).fetchall()
    out: list[_Article] = []
    for headline, pub_at in rows:
        compound = _sentiment_model(headline)
        age_days = (end - pub_at).total_seconds() / 86400.0
        out.append(_Article(headline=headline, compound=compound,
                            age_days=max(0.0, age_days)))
    return out


def _passes_quality_gate(articles: list[_Article]) -> bool:
    if len(articles) < _MIN_ARTICLES:
        return False
    unique_ratio = len({a.headline.lower() for a in articles}) / len(articles)
    if unique_ratio < _MIN_UNIQUE_RATIO:
        return False
    scores = [a.compound for a in articles]
    if statistics.stdev(scores) < _MIN_SCORE_STD:
        return False
    if any(a.age_days > _MAX_AGE_DAYS for a in articles):
        return False
    return True


def _weighted_mean(articles: list[_Article]) -> float:
    weights = [math.exp(-_DECAY_LAMBDA * a.age_days) for a in articles]
    scores = [a.compound for a in articles]
    total_w = sum(weights)
    return sum(s * w for s, w in zip(scores, weights)) / total_w


def _debug_dict(articles: list[_Article]) -> dict:
    if not articles:
        return {"mean_score": None, "std": None, "unique_ratio": None}
    scores = [a.compound for a in articles]
    return {
        "mean_score":   statistics.fmean(scores),
        "std":          statistics.stdev(scores) if len(scores) > 1 else 0.0,
        "unique_ratio": len({a.headline.lower() for a in articles}) / len(articles),
    }


def _make_cell(value: float | None, is_missing: bool,
               n_samples: int = 0, debug: dict | None = None) -> dict:
    confidence = (min(1.0, n_samples / _CONFIDENCE_SCALE)
                  if not is_missing else 0.0)
    return {
        "value":           value,
        "is_missing":      is_missing,
        "n_samples":       n_samples,
        "confidence":      confidence,
        "feature_version": FEATURE_VERSION,
        "normalized":      False,
        "debug":           debug or {},
    }


def compute_sentiment_level(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    ts_emitted: datetime,
    **_,
) -> dict:
    """Recency-weighted mean sentiment over [ts_emitted-7d, ts_emitted]."""
    start = ts_emitted - timedelta(days=_WINDOW_DAYS)
    articles = _fetch_articles(conn, ticker, start, ts_emitted)
    debug = _debug_dict(articles)
    if not _passes_quality_gate(articles):
        return _make_cell(None, True, debug=debug)
    value = _weighted_mean(articles)
    return _make_cell(value, False, n_samples=len(articles), debug=debug)
```

- [ ] **Step 4: Run tests to confirm passing**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -k "sentiment_level or version_constant" -v
```

Expected: 8 tests pass (including the ingestion-leak test).

- [ ] **Step 5: Run full suite to check no regressions**

```bash
python -m pytest --tb=short -q 2>&1 | tail -10
```

Expected: previous baseline + 8 new passes.

---

## Task 4: compute_sentiment_delta

**Files:**
- Modify: `src/finterminal/features/compute_reflexivity.py`
- Modify: `tests/features/test_compute_reflexivity.py`

**Context:** `sentiment_delta = level(current 7d) − level(prior 7d)` over non-overlapping windows. Returns `(None, True)` when either window fails the quality gate.

- [ ] **Step 1: Write the failing tests**

Append to `tests/features/test_compute_reflexivity.py`:

```python
# ── sentiment_delta ──────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import compute_sentiment_delta


def _seed_positive_window(conn, ts_anchor, ticker="TCS", count=6):
    for i in range(count):
        _seed_story(conn, f"strong profit record growth rally {i}",
                    ts_anchor - timedelta(hours=i * 10), ticker=ticker)


def _seed_negative_window(conn, ts_anchor, ticker="TCS", count=6):
    for i in range(count):
        _seed_story(conn, f"loss debt crisis bankruptcy collapse {i}",
                    ts_anchor - timedelta(hours=i * 10), ticker=ticker)


def test_sentiment_delta_missing_when_current_window_fails(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_positive_window(conn, TS - timedelta(days=7))
    cell = compute_sentiment_delta(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_sentiment_delta_missing_when_prior_window_fails(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_positive_window(conn, TS)
    cell = compute_sentiment_delta(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_sentiment_delta_positive_when_sentiment_improves(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_negative_window(conn, TS - timedelta(days=7))
    _seed_positive_window(conn, TS)
    cell = compute_sentiment_delta(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is False
    assert cell["value"] > 0
    assert cell["feature_version"] == FEATURE_VERSION


def test_sentiment_delta_negative_when_sentiment_deteriorates(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_positive_window(conn, TS - timedelta(days=7))
    _seed_negative_window(conn, TS)
    cell = compute_sentiment_delta(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is False
    assert cell["value"] < 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -k "sentiment_delta" -v 2>&1 | tail -10
```

Expected: ImportError — `compute_sentiment_delta` not defined.

- [ ] **Step 3: Append compute_sentiment_delta**

Append to `src/finterminal/features/compute_reflexivity.py`:

```python
def compute_sentiment_delta(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    ts_emitted: datetime,
    **_,
) -> dict:
    """Raw delta between non-overlapping 7-day sentiment windows.

    Window A (current): [ts_emitted - 7d,  ts_emitted]
    Window B (prior):   [ts_emitted - 14d, ts_emitted - 7d)

    Z-normalization deferred — `normalized=False` until #5 activator.
    """
    boundary    = ts_emitted - timedelta(days=_WINDOW_DAYS)
    prior_start = ts_emitted - timedelta(days=2 * _WINDOW_DAYS)

    articles_now  = _fetch_articles(conn, ticker, boundary, ts_emitted)
    articles_prev = _fetch_articles(conn, ticker, prior_start, boundary)

    debug = {"now": _debug_dict(articles_now), "prev": _debug_dict(articles_prev)}

    if not _passes_quality_gate(articles_now) or not _passes_quality_gate(articles_prev):
        return _make_cell(None, True, debug=debug)

    delta = _weighted_mean(articles_now) - _weighted_mean(articles_prev)
    n = len(articles_now) + len(articles_prev)
    return _make_cell(delta, False, n_samples=n, debug=debug)
```

- [ ] **Step 4: Run tests to confirm passing**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -k "sentiment_delta" -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL
git add finterminal/src/finterminal/features/compute_reflexivity.py \
        finterminal/tests/features/test_compute_reflexivity.py
git commit -m "$(cat <<'EOF'
feat(#4): compute_sentiment_level + delta with model wrapper, version stamp, ingestion-time fix

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: compute_entropy_sentiment

**Files:**
- Modify: `src/finterminal/features/compute_reflexivity.py`
- Modify: `tests/features/test_compute_reflexivity.py`

**Context:** Shannon entropy `H = -Σ p·log(p)` over three VADER bins (`compound < -0.05` → neg, `−0.05 ≤ x ≤ 0.05` → neu, `> 0.05` → pos). Low = consensus; high = disagreement.

- [ ] **Step 1: Write the failing tests**

Append to `tests/features/test_compute_reflexivity.py`:

```python
# ── entropy_sentiment ────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import compute_entropy_sentiment


def test_entropy_missing_when_insufficient_articles(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    cell = compute_entropy_sentiment(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_entropy_max_when_three_equal_bins(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    pos = ["record profits soar strong earnings growth rally",
           "outstanding revenue beats expectations significantly higher"]
    neu = ["company held annual general meeting today",
           "board approved routine agenda items quarterly"]
    neg = ["massive loss debt default bankruptcy crisis collapse",
           "severe decline revenue miss disappointing earnings crash"]
    for h in pos + neu + neg:
        _seed_story(conn, h, TS - timedelta(hours=1))
    cell = compute_entropy_sentiment(conn, ticker="TCS", ts_emitted=TS)
    if not cell["is_missing"]:
        assert cell["value"] <= math.log(3) + 0.01
        assert cell["n_samples"] == 6
        assert cell["feature_version"] == FEATURE_VERSION


def test_entropy_is_deterministic(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    pos = ["record profits soar strong earnings growth rally",
           "outstanding revenue beats expectations significantly higher"]
    neg = ["massive loss debt default bankruptcy crisis collapse",
           "severe decline revenue miss disappointing earnings crash"]
    neu = ["company held annual general meeting today",
           "board approved routine agenda items quarterly"]
    for h in pos + neg + neu:
        _seed_story(conn, h, TS - timedelta(hours=1))
    a = compute_entropy_sentiment(conn, ticker="TCS", ts_emitted=TS)
    for i in range(5):
        _seed_story(conn, f"future news {i}", TS + timedelta(days=i + 1))
    b = compute_entropy_sentiment(conn, ticker="TCS", ts_emitted=TS)
    assert a["value"] == b["value"]
    assert a["is_missing"] == b["is_missing"]
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -k "entropy" -v 2>&1 | tail -10
```

Expected: ImportError — `compute_entropy_sentiment` not defined.

- [ ] **Step 3: Append _entropy + compute_entropy_sentiment**

Append to `src/finterminal/features/compute_reflexivity.py`:

```python
def _entropy(scores: list[float]) -> float:
    """Shannon entropy over VADER neg/neu/pos bins."""
    n = len(scores)
    if n == 0:
        return 0.0
    counts = {"neg": 0, "neu": 0, "pos": 0}
    for s in scores:
        if s < -0.05:
            counts["neg"] += 1
        elif s > 0.05:
            counts["pos"] += 1
        else:
            counts["neu"] += 1
    h = 0.0
    for c in counts.values():
        if c > 0:
            p = c / n
            h -= p * math.log(p)
    return h


def compute_entropy_sentiment(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    ts_emitted: datetime,
    **_,
) -> dict:
    """Shannon entropy of sentiment-bin distribution over [ts-7d, ts]."""
    start = ts_emitted - timedelta(days=_WINDOW_DAYS)
    articles = _fetch_articles(conn, ticker, start, ts_emitted)
    debug = _debug_dict(articles)
    if not _passes_quality_gate(articles):
        return _make_cell(None, True, debug=debug)
    value = _entropy([a.compound for a in articles])
    return _make_cell(value, False, n_samples=len(articles), debug=debug)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -k "entropy" -v
```

Expected: 3 entropy_sentiment tests pass.

---

## Task 6: compute_entropy_change

**Files:**
- Modify: `src/finterminal/features/compute_reflexivity.py`
- Modify: `tests/features/test_compute_reflexivity.py`

**Context:** `entropy_change = entropy(current 7d) − entropy(prior 7d)`. Positive → narrative breaking down; negative → consensus forming.

- [ ] **Step 1: Append failing tests**

```python
# ── entropy_change ───────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import compute_entropy_change


def test_entropy_change_missing_when_either_window_fails(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    headlines = ["record profits soar strong earnings growth rally x",
                 "outstanding revenue beats expectations significantly x",
                 "massive loss debt default bankruptcy crisis x",
                 "severe decline miss disappointing earnings x",
                 "mixed results moderate neutral report x",
                 "company board meeting schedule x"]
    for h in headlines:
        _seed_story(conn, h, TS - timedelta(hours=1))
    cell = compute_entropy_change(conn, ticker="TCS", ts_emitted=TS)
    assert cell["is_missing"] is True


def test_entropy_change_is_deterministic(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    boundary = TS - timedelta(days=7)
    base = [
        ("record profits soar strong growth A", boundary - timedelta(hours=2)),
        ("outstanding revenue beats B",          boundary - timedelta(hours=4)),
        ("massive loss default C",               boundary - timedelta(hours=6)),
        ("severe decline miss D",                boundary - timedelta(hours=8)),
        ("company held meeting E",               boundary - timedelta(hours=10)),
        ("board approved agenda F",              boundary - timedelta(hours=12)),
        ("record profits soar strong 1",         TS - timedelta(hours=2)),
        ("outstanding revenue beats 2",          TS - timedelta(hours=4)),
        ("strong profit growth 3",               TS - timedelta(hours=6)),
        ("earnings beat forecast 4",             TS - timedelta(hours=8)),
        ("market rally strong 5",                TS - timedelta(hours=10)),
        ("revenue surge targets 6",              TS - timedelta(hours=12)),
    ]
    for h, ts in base:
        _seed_story(conn, h, ts)
    a = compute_entropy_change(conn, ticker="TCS", ts_emitted=TS)
    for i in range(5):
        _seed_story(conn, f"future {i}", TS + timedelta(days=i + 1))
    b = compute_entropy_change(conn, ticker="TCS", ts_emitted=TS)
    assert a["value"] == b["value"]
    assert a["is_missing"] == b["is_missing"]
```

- [ ] **Step 2: Run failing**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -k "entropy_change" -v 2>&1 | tail -10
```

Expected: ImportError.

- [ ] **Step 3: Append compute_entropy_change**

```python
def compute_entropy_change(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    ts_emitted: datetime,
    **_,
) -> dict:
    """Delta of Shannon entropy between non-overlapping 7-day windows."""
    boundary    = ts_emitted - timedelta(days=_WINDOW_DAYS)
    prior_start = ts_emitted - timedelta(days=2 * _WINDOW_DAYS)
    articles_now  = _fetch_articles(conn, ticker, boundary, ts_emitted)
    articles_prev = _fetch_articles(conn, ticker, prior_start, boundary)
    debug = {"now": _debug_dict(articles_now), "prev": _debug_dict(articles_prev)}
    if not _passes_quality_gate(articles_now) or not _passes_quality_gate(articles_prev):
        return _make_cell(None, True, debug=debug)
    h_now  = _entropy([a.compound for a in articles_now])
    h_prev = _entropy([a.compound for a in articles_prev])
    n = len(articles_now) + len(articles_prev)
    return _make_cell(h_now - h_prev, False, n_samples=n, debug=debug)
```

- [ ] **Step 4: Run all reflexivity tests**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL
git add finterminal/src/finterminal/features/compute_reflexivity.py \
        finterminal/tests/features/test_compute_reflexivity.py
git commit -m "$(cat <<'EOF'
feat(#4): compute_entropy_sentiment + compute_entropy_change with VADER bins

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: compute_feature_health (the meta-signal)

**Files:**
- Modify: `src/finterminal/features/compute_reflexivity.py`
- Modify: `tests/features/test_compute_reflexivity.py`

**Context:** From `input.md`, this is the "hidden edge". `feature_health = confidence * (1 - entropy_sentiment / log(3))`. Both inputs come from `compute_sentiment_level` / `compute_entropy_sentiment`. Normalised by `log(3)` so the multiplier sits in `[0, 1]`. High value → high-confidence consensus narrative. Low value → either too few articles or maximally split sentiment.

This function takes already-computed cells (not `conn`) so the orchestrator can pass the cells it already has — no double DB hit.

- [ ] **Step 1: Write failing tests**

Append to `tests/features/test_compute_reflexivity.py`:

```python
# ── feature_health ───────────────────────────────────────────────────────────

from finterminal.features.compute_reflexivity import compute_feature_health


def test_feature_health_missing_when_inputs_missing():
    sl = {"value": None, "is_missing": True, "confidence": 0.0,
          "feature_version": EXPECTED_VERSION}
    es = {"value": None, "is_missing": True, "confidence": 0.0,
          "feature_version": EXPECTED_VERSION}
    cell = compute_feature_health(sentiment_level=sl, entropy_sentiment=es)
    assert cell["is_missing"] is True
    assert cell["value"] is None


def test_feature_health_high_when_high_confidence_low_entropy():
    sl = {"value": 0.6, "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    es = {"value": 0.0, "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    cell = compute_feature_health(sentiment_level=sl, entropy_sentiment=es)
    assert cell["is_missing"] is False
    assert cell["value"] == pytest.approx(1.0)


def test_feature_health_zero_when_max_entropy():
    sl = {"value": 0.6, "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    es = {"value": math.log(3), "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    cell = compute_feature_health(sentiment_level=sl, entropy_sentiment=es)
    assert cell["value"] == pytest.approx(0.0, abs=1e-9)


def test_feature_health_zero_when_zero_confidence():
    sl = {"value": 0.6, "is_missing": False, "confidence": 0.0,
          "feature_version": EXPECTED_VERSION}
    es = {"value": 0.0, "is_missing": False, "confidence": 1.0,
          "feature_version": EXPECTED_VERSION}
    cell = compute_feature_health(sentiment_level=sl, entropy_sentiment=es)
    assert cell["value"] == pytest.approx(0.0)
```

- [ ] **Step 2: Run failing**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -k "feature_health" -v 2>&1 | tail -10
```

Expected: ImportError.

- [ ] **Step 3: Append compute_feature_health**

Append to `src/finterminal/features/compute_reflexivity.py`:

```python
_LOG3 = math.log(3)


def compute_feature_health(
    *,
    sentiment_level: dict,
    entropy_sentiment: dict,
    **_,
) -> dict:
    """Meta-signal: how trustworthy is this signal's narrative state?

    health = confidence_level * (1 - entropy_norm)
    where entropy_norm = entropy_sentiment / log(3)  ∈ [0, 1]

    High → high-confidence consensus (model can lean on this signal).
    Low  → either thin data or maximally split narrative.
    Missing whenever either input is missing.
    """
    if sentiment_level.get("is_missing") or entropy_sentiment.get("is_missing"):
        return _make_cell(None, True, debug={})
    conf = float(sentiment_level.get("confidence") or 0.0)
    h    = float(entropy_sentiment.get("value") or 0.0)
    h_norm = max(0.0, min(1.0, h / _LOG3))
    health = conf * (1.0 - h_norm)
    n = int(sentiment_level.get("n_samples") or 0)
    return _make_cell(health, False, n_samples=n,
                      debug={"conf": conf, "entropy_norm": h_norm})
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -k "feature_health" -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Run full reflexivity suite**

```bash
python -m pytest tests/features/test_compute_reflexivity.py -v
```

Expected: ~25 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL
git add finterminal/src/finterminal/features/compute_reflexivity.py \
        finterminal/tests/features/test_compute_reflexivity.py
git commit -m "$(cat <<'EOF'
feat(#4): compute_feature_health — meta-signal of narrative trustworthiness

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Promote FeatureSpecs + Wire Orchestrator

**Files:**
- Modify: `src/finterminal/features/registry.py`
- Modify: `src/finterminal/features/orchestrator.py`
- Modify: `tests/features/test_orchestrator.py`

**Context:** Promote 3 placeholders, add 2 new (`entropy_change`, `feature_health`). After this task, `PLACEHOLDER_NAMES = ()`. Orchestrator computes the four DB-backed reflexivity features first, then `feature_health` from the in-memory cells (no second DB hit).

- [ ] **Step 1: Write failing orchestrator tests**

Append to `tests/features/test_orchestrator.py`:

```python
def test_reflexivity_features_present_in_output(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    out = compute_for_signal(
        conn, signal_id="test-r1",
        signal_type=SignalType.SENTIMENT_DELTA, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0), payload={},
    )
    for name in ("sentiment_level", "sentiment_delta",
                 "entropy_sentiment", "entropy_change", "feature_health"):
        assert name in out, f"{name} missing"
        assert "value" in out[name] and "is_missing" in out[name]


def test_no_placeholder_features_remain():
    from finterminal.features.registry import PLACEHOLDER_NAMES
    assert PLACEHOLDER_NAMES == ()


def test_compute_for_signal_returns_20_keys(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    out = compute_for_signal(
        conn, signal_id="test-r2",
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0),
        payload={"story_count_delta": 3.0, "cluster_id": "c1"},
    )
    from finterminal.features.registry import V1_FEATURES
    assert set(out.keys()) == {f.name for f in V1_FEATURES}
    assert len(out) == 20
```

- [ ] **Step 2: Run failing**

```bash
python -m pytest tests/features/test_orchestrator.py -k "reflexivity_features_present or no_placeholder or 20_keys" -v 2>&1 | tail -15
```

- [ ] **Step 3: Update registry.py**

In `src/finterminal/features/registry.py`, replace the `# Reflexivity placeholders (#4 fills these)` block:

```python
    # Reflexivity placeholders (#4 fills these)
    FeatureSpec("sentiment_level",         None, "Grok / news (#4)"),
    FeatureSpec("sentiment_delta",         None, "derived (#4)"),
    FeatureSpec("entropy_sentiment",       None, "derived (#4)"),
```

with:

```python
    # Reflexivity (#4)
    FeatureSpec("sentiment_level",   "compute_sentiment_level",   "news_stories"),
    FeatureSpec("sentiment_delta",   "compute_sentiment_delta",   "derived"),
    FeatureSpec("entropy_sentiment", "compute_entropy_sentiment", "derived"),
    FeatureSpec("entropy_change",    "compute_entropy_change",    "derived"),
    FeatureSpec("feature_health",    "compute_feature_health",    "derived"),
```

- [ ] **Step 4: Update orchestrator.py**

1. Add `compute_reflexivity` to the imports:

```python
from . import compute_price, compute_regime, compute_news, compute_quality, compute_reflexivity
```

2. Replace the placeholder loop:

```python
    # Placeholders (reflexivity — #4 fills these)
    for name in PLACEHOLDER_NAMES:
        out[name] = {"value": None, "is_missing": True}
```

with the reflexivity block (note `feature_health` reads in-memory cells — no second DB hit):

```python
    # Reflexivity block (#4) — DB-backed first, then meta-signal
    sl_cell = compute_reflexivity.compute_sentiment_level(conn, **ctx)
    out["sentiment_level"] = sl_cell
    out["sentiment_delta"] = compute_reflexivity.compute_sentiment_delta(conn, **ctx)
    es_cell = compute_reflexivity.compute_entropy_sentiment(conn, **ctx)
    out["entropy_sentiment"] = es_cell
    out["entropy_change"]    = compute_reflexivity.compute_entropy_change(conn, **ctx)
    # feature_health: meta-signal over already-computed cells, no extra DB hit
    out["feature_health"] = compute_reflexivity.compute_feature_health(
        sentiment_level=sl_cell,
        entropy_sentiment=es_cell,
    )
```

3. Drop the unused `PLACEHOLDER_NAMES` import from the top of the file:

Change:
```python
from .registry import V1_FEATURES, PLACEHOLDER_NAMES
```
to:
```python
from .registry import V1_FEATURES
```

- [ ] **Step 5: Update the stale test name in test_orchestrator.py**

Find `test_compute_for_signal_returns_18_keys` and rename to `test_compute_for_signal_output_keys_match_registry`. Drop the `PLACEHOLDER_NAMES` import.

Replace the test body with:

```python
def test_compute_for_signal_output_keys_match_registry(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    _seed_full(conn)
    sig_id = str(uuid.uuid4())
    out = compute_for_signal(
        conn, signal_id=sig_id,
        signal_type=SignalType.CLUSTER_MOMENTUM, ticker="TCS",
        ts_emitted=datetime(2026, 4, 20, 10, 0),
        payload={"story_count_delta": 3.0, "cluster_id": "c1"},
    )
    assert set(out.keys()) == {f.name for f in V1_FEATURES}
```

Update the `from finterminal.features.registry import …` line in that test file: drop `PLACEHOLDER_NAMES`.

- [ ] **Step 6: Run all orchestrator tests**

```bash
python -m pytest tests/features/test_orchestrator.py -v
```

- [ ] **Step 7: Run the full test suite**

```bash
python -m pytest --tb=short -q 2>&1 | tail -15
```

Expected: all tests pass; new feature count is 20.

- [ ] **Step 8: Commit**

```bash
cd /Users/ajinkyawagh/Desktop/FINTERMINAL
git add finterminal/src/finterminal/features/registry.py \
        finterminal/src/finterminal/features/orchestrator.py \
        finterminal/tests/features/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(#4): promote 5 reflexivity FeatureSpecs + wire orchestrator (incl. feature_health)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

### Spec Coverage (input.md gap → fix)

| input.md gap | Covered by |
|---|---|
| 1. Hardcoded VADER | Task 3 `_sentiment_model()` wrapper |
| 2. No reproducible evolution | Task 1 column + Task 3 `FEATURE_VERSION` constant |
| 3. No feature lifecycle / freeze | Task 2 freeze-on-write upsert |
| 4. Z-norm activation undefined | Task 1 `normalized` flag (always False in v1; activator deferred to #5) |
| 5. Feature-centric, not signal-centric | Task 7 `compute_feature_health` (meta-signal over level + entropy) |
| 6. Snapshot+ingestion control | Task 3 `_fetch_articles` adds `fetched_at <= end`; Task 3 test `excludes_late_arriving_articles` |
| 7. No debug traceability | Task 3 `_debug_dict` returned in every cell (in-memory; not persisted in v1) |

### Build-Order Compliance

input.md prescribed: **versioning → snapshot enforcement → freeze → compute**.
This plan: Task 1 (versioning + columns) → Task 2 (freeze) → Task 3+ (compute with snapshot + ingestion fix). ✔

### Type / Contract Consistency

- `FeatureCell` is `total=False` so legacy callers (price/regime) keep working without code changes.
- `_make_cell` always emits `feature_version`, `normalized`, `debug` — uniform shape across all 5 reflexivity functions.
- `compute_feature_health` takes cells, not `conn` — orchestrator passes already-computed cells (no double DB hit).
- `upsert_features`'s `WHERE … IS DISTINCT FROM …` clause handles all four states: NULL→NULL (rewrite), NULL→version (rewrite), version→same (no-op), v1→v2 (overwrite, model evolution).

---

**Plan saved. Execution begins next via subagents — Haiku for mechanical edits, Sonnet for the freeze logic + compute layer.**
