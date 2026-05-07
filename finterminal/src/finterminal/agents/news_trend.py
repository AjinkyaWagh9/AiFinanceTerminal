"""News & Trend agent — Protocol wrapper around the pipeline.

B-2a: is_llm=False (pipeline is deterministic). ctx.ticker is ignored;
pipeline runs cross-ticker. B-2b will filter clusters by ctx.ticker.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

import duckdb

from ..news.pipeline import PipelineResult, run as _pipeline_run
from .base import AgentContext, AgentResult

logger = logging.getLogger(__name__)


class NewsTrendAgent:
    name = "news_trend"
    is_llm = False

    def __init__(
        self,
        pipeline: Callable[[duckdb.DuckDBPyConnection], PipelineResult] = _pipeline_run,
    ) -> None:
        self._pipeline = pipeline

    async def run(self, ctx: AgentContext) -> AgentResult:
        try:
            result = await asyncio.to_thread(self._pipeline, ctx.conn)
            return AgentResult(
                ok=True,
                payload={
                    "as_of": result.as_of.isoformat(),
                    "n_stories": result.n_stories,
                    "n_clusters": result.n_clusters,
                    "n_lineage_links": result.n_lineage_links,
                    "runtime_s": result.runtime_s,
                },
            )
        except Exception as exc:
            logger.warning("news_trend pipeline failed: %s", exc)
            return AgentResult(ok=False, error=str(exc))
