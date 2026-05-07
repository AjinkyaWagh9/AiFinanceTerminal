"""Test that migration 003 applies cleanly and creates all expected tables + index."""
import duckdb
import pytest
from finterminal.data.duckdb_store import get_conn


def test_migration_creates_news_stories(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    conn = get_conn()
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    assert "news_stories" in tables
    assert "news_clusters" in tables
    assert "cluster_lineage" in tables
    conn.close()


def test_news_stories_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    conn = get_conn()
    cols = {r[0] for r in conn.execute("DESCRIBE news_stories").fetchall()}
    for expected in ["id", "url", "source", "headline", "body", "published_at",
                     "fetched_at", "tickers", "sectors", "embedding", "cluster_id"]:
        assert expected in cols, f"missing column: {expected}"
    conn.close()


def test_cluster_lineage_has_story_count_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    conn = get_conn()
    cols = {r[0] for r in conn.execute("DESCRIBE cluster_lineage").fetchall()}
    assert "story_count_delta" in cols
    conn.close()


def test_vss_extension_loads(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    conn = get_conn()
    result = conn.execute(
        "SELECT loaded FROM duckdb_extensions() WHERE extension_name = 'vss'"
    ).fetchone()
    assert result is not None and result[0] is True
    conn.close()
