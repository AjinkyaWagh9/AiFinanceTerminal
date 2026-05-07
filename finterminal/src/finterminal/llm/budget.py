"""Cost tracking — every LLM call writes a JSONL row.

Phase 1: append-only JSONL at LLM_CALLS_PATH.
Phase 3: migrate to DuckDB `llm_calls` table for `/llm-cost` queries.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .base import Completion


def _log_path() -> Path:
    raw = os.environ.get("LLM_CALLS_PATH", "./logs/llm_calls.jsonl")
    p = Path(raw)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(agent: str, completion: Completion, error: str | None = None) -> None:
    cost = (
        completion.tokens_in / 1_000_000 * _cost_in(completion.model)
        + completion.tokens_out / 1_000_000 * _cost_out(completion.model)
    )
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "model": completion.model,
        "provider": completion.provider,
        "tokens_in": completion.tokens_in,
        "tokens_out": completion.tokens_out,
        "cost_usd": round(cost, 6),
        "latency_ms": completion.latency_ms,
        "cache_hit": completion.cache_hit,
        "error": error,
    }
    with _log_path().open("a") as fh:
        fh.write(json.dumps(row) + "\n")


# These are looked up from the registry at call time — but to keep budget.py
# decoupled from registry, we accept that completion.model is a name in
# models.yaml and the per-token costs are the registry's truth.
# For Phase 1, the AnthropicProvider passes its metadata's costs directly via
# Completion. Until then we hardcode a fallback table; replaced in Phase 2.
_FALLBACK_COSTS = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (15.0, 75.0),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5": (1.25, 10.0),
    "qwen3:8b": (0.0, 0.0),
    "phi4-mini": (0.0, 0.0),
    "grok-3-mini": (0.30, 0.50),
}


def _cost_in(model: str) -> float:
    return _FALLBACK_COSTS.get(model, (0.0, 0.0))[0]


def _cost_out(model: str) -> float:
    return _FALLBACK_COSTS.get(model, (0.0, 0.0))[1]
