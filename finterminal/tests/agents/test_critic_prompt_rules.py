"""Sanity checks that critic.md contains the rubric we rely on (Q-1).

The Critic's behavior depends on these phrases being in the system
prompt; this guards against accidental deletion or refactor regression.
"""
from __future__ import annotations

from finterminal.agents.critic import _load_prompt


def test_prompt_loads():
    prompt = _load_prompt()
    assert len(prompt) > 500


def test_prompt_has_severity_rubric():
    prompt = _load_prompt()
    assert "Severity rubric" in prompt
    # Each level must have explicit criteria:
    assert "fabricated tag" in prompt.lower()
    assert "contradicts a value" in prompt.lower()
    assert "material to the bull/bear conclusion" in prompt.lower()
    assert "stylistic" in prompt.lower()


def test_prompt_caps_severity_inflation():
    """Q-1: the prompt should explicitly tell the model that
    over-flagging is a calibration failure, not extra rigor."""
    prompt = _load_prompt()
    assert "≤2 high-severity issues" in prompt
    assert "mis-calibrated" in prompt or "miscalibrated" in prompt


def test_prompt_uses_collegial_framing_not_adversarial():
    prompt = _load_prompt()
    # Tone fix: the rewrite drops "adversarial reviewer" framing.
    assert "adversarial" not in prompt.lower()
    assert "peer-reviewer" in prompt.lower() or "peer reviewer" in prompt.lower()


def test_prompt_defines_verdict_thresholds():
    prompt = _load_prompt()
    for verdict in ["ACCEPT", "REVISE", "REJECT"]:
        assert verdict in prompt
    # The verdicts must have semantic definitions, not just be listed:
    assert "no high-severity issues" in prompt.lower()
    assert "fundamental sourcing failure" in prompt.lower()


def test_prompt_outputs_use_bracketed_severity_format():
    """Output format must specify [HIGH]/[MEDIUM]/[LOW] prefix so the
    panel renderer can parse severities."""
    prompt = _load_prompt()
    assert "[HIGH]" in prompt
    assert "[MEDIUM]" in prompt
    assert "[LOW]" in prompt
