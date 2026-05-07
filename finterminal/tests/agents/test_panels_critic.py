"""Verify analysis_panel renders critic block when provided + degrades cleanly."""
from __future__ import annotations

from rich.console import Console

from finterminal.ui.panels import analysis_panel


_ANALYSIS = {
    "ticker": "RELIANCE.NS",
    "variant_perception": "consensus too bullish",
    "bull_case": "- margins improving",
    "bear_case": "- new-energy capex risk",
    "conviction": "Watch Long",
    "confidence": 0.55,
    "assumptions": "- crude $70-95",
    "what_would_change": "- pledge increase",
}


def _render(panel) -> str:
    console = Console(record=True, width=120, file=open("/dev/null", "w"))
    console.print(panel)
    return console.export_text()


def test_panel_renders_without_critic_today_layout():
    panel = analysis_panel(_ANALYSIS)
    text = _render(panel)
    assert "RELIANCE.NS" in text
    assert "margins" in text
    assert "Watch Long" in text


def test_panel_renders_critic_block_when_present():
    critic = {
        "verdict": "REVISE",
        "issues_md": "- [HIGH] PE claim unsourced",
        "missing_md": "- pledge status",
        "confidence_adj": 0.45,
    }
    panel = analysis_panel(_ANALYSIS, critic=critic)
    text = _render(panel)
    assert "REVISE" in text
    assert "PE claim" in text
    assert "pledge" in text
    # Both numbers (raw + adjusted) visible:
    assert "0.55" in text
    assert "0.45" in text


def test_panel_renders_degraded_critic_badge():
    panel = analysis_panel(_ANALYSIS, critic_error="timeout after 30s")
    text = _render(panel)
    assert "Critic unavailable" in text
    assert "timeout" in text
    # Original confidence still rendered, no adjustment shown:
    assert "0.55" in text
