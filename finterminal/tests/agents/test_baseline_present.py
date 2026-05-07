"""Sanity check: the non-regression baseline JSON exists and contains all 7 analyst fields."""
from __future__ import annotations

import json
from pathlib import Path


_BASELINE = Path(__file__).parent / "fixtures" / "analyst_baseline_RELIANCE.json"

_REQUIRED_PARSED_KEYS = {
    "variant_perception",
    "bull_case",
    "bear_case",
    "conviction",
    "confidence",
    "assumptions",
    "what_would_change",
}


def test_baseline_file_exists():
    assert _BASELINE.exists(), (
        f"Baseline missing: {_BASELINE}. "
        "Run: uv run python tests/agents/fixtures/baseline_capture.py"
    )


def test_baseline_has_all_parsed_fields():
    data = json.loads(_BASELINE.read_text())
    parsed = data["parsed"]
    missing = _REQUIRED_PARSED_KEYS - set(parsed.keys())
    assert not missing, f"baseline missing parsed keys: {missing}"


def test_baseline_confidence_is_in_range():
    data = json.loads(_BASELINE.read_text())
    conf = data["parsed"]["confidence"]
    assert conf is None or 0.0 <= conf <= 1.0
