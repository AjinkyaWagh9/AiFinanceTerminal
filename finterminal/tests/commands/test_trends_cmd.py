"""Tests for /refresh-news and /trends commands."""
from unittest.mock import patch
from io import StringIO

import pytest
from rich.console import Console

from finterminal.commands import dispatch


def _console() -> Console:
    return Console(file=StringIO(), highlight=False)


@pytest.fixture
def mock_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from finterminal.data.duckdb_store import get_conn
    conn = get_conn()
    yield conn
    conn.close()


def test_refresh_news_calls_pipeline(mock_conn):
    from finterminal.news.pipeline import PipelineResult
    from datetime import date
    fake_result = PipelineResult(as_of=date.today(), n_stories=30, n_clusters=5, n_lineage_links=3, runtime_s=2.1)
    with patch("finterminal.commands._pipeline_run", return_value=fake_result), \
         patch("finterminal.commands.duckdb_store.get_conn", return_value=mock_conn):
        c = _console()
        dispatch("/refresh-news", c)
        output = c.file.getvalue()
    assert "30" in output or "stories" in output.lower()


def test_trends_no_data_shows_error(mock_conn):
    with patch("finterminal.commands.duckdb_store.get_conn", return_value=mock_conn), \
         patch("finterminal.data.news_store.latest_clusters", return_value=[]):
        c = _console()
        dispatch("/trends", c)
        output = c.file.getvalue()
    assert "refresh-news" in output.lower() or "no trend" in output.lower()


def test_trends_with_sector_arg(mock_conn):
    fake_clusters = [
        {"id": "abc123", "as_of": "2026-04-29", "story_count": 8, "source_count": 3,
         "top_tickers": ["HDFCBANK"], "dominant_sector": "Banking",
         "representative_id": "HDFC stress headline", "first_seen": "2026-04-29",
         "story_count_delta": 2, "day_n": 1},
    ]
    with patch("finterminal.commands.duckdb_store.get_conn", return_value=mock_conn), \
         patch("finterminal.data.news_store.latest_clusters", return_value=fake_clusters):
        c = _console()
        dispatch("/trends Banking", c)
        output = c.file.getvalue()
    assert "HDFCBANK" in output or "Banking" in output
