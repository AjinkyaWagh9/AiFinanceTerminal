"""End-to-end pipeline test with stubbed feeds."""
import time
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from finterminal.news.collector import Story
from finterminal.news.pipeline import PipelineResult, run as run_pipeline


_FAKE_STORIES = [
    Story(
        id="s1", source="MC", headline="Reliance Industries Q4 net profit rises on Jio growth",
        url="https://example.com/s1",
        published_at=datetime(2026, 4, 29, 6, 0, tzinfo=timezone.utc),
    ),
    Story(
        id="s2", source="ET", headline="Reliance Q4 results beat analyst estimates strongly",
        url="https://example.com/s2",
        published_at=datetime(2026, 4, 29, 6, 30, tzinfo=timezone.utc),
    ),
    Story(
        id="s3", source="Livemint", headline="HDFC Bank management flags microfinance stress",
        url="https://example.com/s3",
        published_at=datetime(2026, 4, 29, 7, 0, tzinfo=timezone.utc),
    ),
    Story(
        id="s4", source="Reuters", headline="HDFC Bank Q4 margin pressure from MFI portfolio",
        url="https://example.com/s4",
        published_at=datetime(2026, 4, 29, 7, 30, tzinfo=timezone.utc),
    ),
]


@pytest.fixture
def mem_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from finterminal.data.duckdb_store import get_conn
    conn = get_conn()
    yield conn
    conn.close()


def test_pipeline_returns_result(mem_conn):
    with patch("finterminal.news.pipeline.fetch_all", return_value=_FAKE_STORIES):
        result = run_pipeline(mem_conn)
    assert isinstance(result, PipelineResult)
    assert result.n_stories >= 1
    assert result.n_clusters >= 1
    assert result.runtime_s > 0


def test_pipeline_persists_stories(mem_conn):
    with patch("finterminal.news.pipeline.fetch_all", return_value=_FAKE_STORIES):
        run_pipeline(mem_conn)
    count = mem_conn.execute("SELECT COUNT(*) FROM news_stories").fetchone()[0]
    assert count >= 1


def test_pipeline_persists_clusters(mem_conn):
    with patch("finterminal.news.pipeline.fetch_all", return_value=_FAKE_STORIES):
        run_pipeline(mem_conn)
    count = mem_conn.execute("SELECT COUNT(*) FROM news_clusters").fetchone()[0]
    assert count >= 1


def test_pipeline_empty_feeds(mem_conn):
    with patch("finterminal.news.pipeline.fetch_all", return_value=[]):
        result = run_pipeline(mem_conn)
    assert result.n_stories == 0
    assert result.n_clusters == 0
