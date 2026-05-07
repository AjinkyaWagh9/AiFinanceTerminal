"""DuckDB connection + CRUD helpers."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import duckdb

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _db_path() -> Path:
    raw = os.environ.get("DUCKDB_PATH", "./data/finterminal.duckdb")
    p = Path(raw).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect(path: str) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection at *path* and run migrations. Suitable for tests."""
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(p))
    try:
        conn.execute("LOAD vss")
    except Exception:
        pass  # vss not installed yet — migration 003 will INSTALL it
    _run_migrations(conn)
    return conn


def get_conn() -> duckdb.DuckDBPyConnection:
    """Returns a DuckDB connection. Runs migrations on first open."""
    return connect(str(_db_path()))


def _run_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations (id VARCHAR PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    applied = {row[0] for row in conn.execute("SELECT id FROM _migrations").fetchall()}
    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if sql_file.stem in applied:
            continue
        conn.execute(sql_file.read_text())
        conn.execute("INSERT INTO _migrations (id) VALUES (?)", [sql_file.stem])


# ---------- quotes ----------

def upsert_quote(conn: duckdb.DuckDBPyConnection, q: dict) -> None:
    """Insert or replace by (ticker, as_of)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO quotes
            (ticker, as_of, last_price, change_pct, volume, market_cap)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            q["ticker"],
            q["as_of"],
            q.get("last_price"),
            q.get("change_pct"),
            q.get("volume"),
            q.get("market_cap"),
        ],
    )


def latest_quote(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT ticker, as_of, last_price, change_pct, volume, market_cap "
        "FROM quotes WHERE ticker = ? ORDER BY as_of DESC LIMIT 1",
        [ticker],
    ).fetchone()
    if not row:
        return None
    return dict(zip(
        ["ticker", "as_of", "last_price", "change_pct", "volume", "market_cap"],
        row,
    ))


# ---------- fundamentals ----------

def upsert_fundamentals(conn: duckdb.DuckDBPyConnection, f: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO fundamentals
            (ticker, as_of, pe_ttm, eps_ttm, roe, roce, debt_to_equity, revenue_ttm, net_income_ttm)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            f["ticker"],
            f["as_of"],
            f.get("pe_ttm"),
            f.get("eps_ttm"),
            f.get("roe"),
            f.get("roce"),
            f.get("debt_to_equity"),
            f.get("revenue_ttm"),
            f.get("net_income_ttm"),
        ],
    )


def latest_fundamentals(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT ticker, as_of, pe_ttm, eps_ttm, roe, roce, debt_to_equity, revenue_ttm, net_income_ttm "
        "FROM fundamentals WHERE ticker = ? ORDER BY as_of DESC LIMIT 1",
        [ticker],
    ).fetchone()
    if not row:
        return None
    return dict(zip(
        ["ticker", "as_of", "pe_ttm", "eps_ttm", "roe", "roce", "debt_to_equity",
         "revenue_ttm", "net_income_ttm"],
        row,
    ))


# ---------- news ----------

def upsert_news(conn: duckdb.DuckDBPyConnection, items: list[dict]) -> int:
    inserted = 0
    for n in items:
        if not n.get("id"):
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO news
                (id, ticker, source, headline, url, published_at, body)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(n["id"]),
                n.get("ticker"),
                n.get("source"),
                n.get("headline"),
                n.get("url"),
                n.get("published_at"),
                n.get("body"),
            ],
        )
        inserted += 1
    return inserted


def recent_news(conn: duckdb.DuckDBPyConnection, ticker: str, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT id, ticker, source, headline, url, published_at, body "
        "FROM news WHERE ticker = ? ORDER BY published_at DESC NULLS LAST LIMIT ?",
        [ticker, limit],
    ).fetchall()
    cols = ["id", "ticker", "source", "headline", "url", "published_at", "body"]
    return [dict(zip(cols, r)) for r in rows]


# ---------- watchlist ----------

def add_to_watchlist(conn: duckdb.DuckDBPyConnection, ticker: str, notes: str | None = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO watchlist (ticker, notes) VALUES (?, ?)",
        [ticker, notes],
    )


def remove_from_watchlist(conn: duckdb.DuckDBPyConnection, ticker: str) -> None:
    conn.execute("DELETE FROM watchlist WHERE ticker = ?", [ticker])


def list_watchlist(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = conn.execute(
        "SELECT ticker, added_at, notes FROM watchlist ORDER BY added_at"
    ).fetchall()
    return [dict(zip(["ticker", "added_at", "notes"], r)) for r in rows]


# ---------- analyses (Day 5) ----------

def record_analysis(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    bull_case: str,
    bear_case: str,
    confidence: float,
    sources: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Returns the inserted row's id (uuid4).

    `payload` is the full Analyst parsed dict (variant/conviction/assumptions/
    what_would_change in addition to bull/bear/confidence). Stored as JSON in
    the additive `payload_json` column for use by the result-cache rehydration.
    """
    aid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO analyses (id, ticker, bull_case, bear_case, confidence, sources_json, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            aid, ticker, bull_case, bear_case, confidence,
            json.dumps(sources or {}),
            json.dumps(payload) if payload is not None else None,
        ],
    )
    return aid


def latest_analysis(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT id, ticker, created_at, bull_case, bear_case, confidence, sources_json "
        "FROM analyses WHERE ticker = ? ORDER BY created_at DESC LIMIT 1",
        [ticker],
    ).fetchone()
    if not row:
        return None
    cols = ["id", "ticker", "created_at", "bull_case", "bear_case", "confidence", "sources_json"]
    out = dict(zip(cols, row))
    out["sources"] = json.loads(out.pop("sources_json") or "{}")
    return out


# ---------- critiques (Phase 2 / 4a) ----------

def record_critique(
    conn: duckdb.DuckDBPyConnection,
    *,
    analysis_id: str,
    verdict: str | None,
    issues_md: str,
    missing_md: str,
    confidence_adj: float | None,
    raw_text: str,
    model: str | None,
    tokens_in: int,
    tokens_out: int,
    degraded: bool,
    error: str | None,
) -> str:
    """Returns the inserted critique row's id (uuid4)."""
    cid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO critiques (
            id, analysis_id, verdict, issues_md, missing_md,
            confidence_adj, raw_text, model, tokens_in, tokens_out,
            degraded, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            cid, analysis_id, verdict, issues_md, missing_md,
            confidence_adj, raw_text, model, tokens_in, tokens_out,
            degraded, error,
        ],
    )
    return cid


def recent_analysis(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    ttl_s: int,
) -> dict | None:
    """Return the most recent analysis (joined with its latest critique) for `ticker`
    if its created_at is within `ttl_s` seconds of now. Otherwise None.

    Result shape (matches the orchestrator's AnalysisResult contract):
      {
        "analysis_id": str,
        "ticker": str,
        "created_at": datetime,
        "analyst_payload": dict,        # rehydrated from payload_json (or {} if NULL)
        "critic_payload": dict | None,  # None when no critique row OR degraded=True
        "degraded": bool,
        "critic_error": str | None,
      }
    """
    if ttl_s < 0:
        return None
    from datetime import datetime as _dt, timedelta as _td
    cutoff = _dt.now() - _td(seconds=ttl_s)
    row = conn.execute(
        """
        SELECT id, ticker, created_at, bull_case, bear_case, confidence,
               sources_json, payload_json
        FROM analyses
        WHERE ticker = ? AND created_at > ?
        ORDER BY created_at DESC LIMIT 1
        """,
        [ticker, cutoff],
    ).fetchone()
    if not row:
        return None
    aid, t, created, bull, bear, conf, sources_json, payload_json = row

    analyst_payload: dict = json.loads(payload_json) if payload_json else {}
    # Always include the columns the panel needs even if payload_json is empty
    # (e.g. for analyses written before 4a):
    analyst_payload.setdefault("ticker", t)
    analyst_payload.setdefault("bull_case", bull)
    analyst_payload.setdefault("bear_case", bear)
    analyst_payload.setdefault("confidence", conf)

    crit_row = conn.execute(
        """
        SELECT verdict, issues_md, missing_md, confidence_adj, raw_text,
               degraded, error
        FROM critiques
        WHERE analysis_id = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        [aid],
    ).fetchone()

    critic_payload: dict | None = None
    degraded = False
    critic_error: str | None = None
    if crit_row:
        verdict, issues_md, missing_md, conf_adj, raw_text, degraded_flag, err = crit_row
        degraded = bool(degraded_flag)
        critic_error = err
        if not degraded:
            critic_payload = {
                "verdict": verdict,
                "issues_md": issues_md,
                "missing_md": missing_md,
                "confidence_adj": conf_adj,
                "raw_text": raw_text,
            }

    return {
        "analysis_id": aid,
        "ticker": t,
        "created_at": created,
        "analyst_payload": analyst_payload,
        "critic_payload": critic_payload,
        "degraded": degraded,
        "critic_error": critic_error,
    }


# ---------- mgmt_claims ----------

def insert_mgmt_claim(conn: duckdb.DuckDBPyConnection, c: dict) -> str:
    """Insert a management claim record. Returns the new claim_id (uuid4)."""
    claim_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mgmt_claims
            (claim_id, ticker, claimed_at, claim_text, horizon_days,
             outcome_date, outcome_verified, source_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            claim_id,
            c["ticker"],
            c["claimed_at"],
            c["claim_text"],
            c["horizon_days"],
            c.get("outcome_date"),
            c.get("outcome_verified"),
            c.get("source_ref"),
        ],
    )
    return claim_id


def list_mgmt_claims(conn: duckdb.DuckDBPyConnection, ticker: str) -> list[dict]:
    """Return all claims for `ticker`, most recent first."""
    rows = conn.execute(
        "SELECT claim_id, ticker, claimed_at, claim_text, horizon_days, "
        "       outcome_date, outcome_verified, source_ref "
        "FROM mgmt_claims WHERE ticker = ? ORDER BY claimed_at DESC",
        [ticker],
    ).fetchall()
    cols = ["claim_id", "ticker", "claimed_at", "claim_text", "horizon_days",
            "outcome_date", "outcome_verified", "source_ref"]
    return [dict(zip(cols, r)) for r in rows]
