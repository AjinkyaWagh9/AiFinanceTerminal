"""Panel markup-escape regression test (Q-6).

The Analyst emits [src: quote.last_price] tags. Rich's Text/Panel
constructors interpret bracketed text as style markup and silently
strip unknown styles. This test renders an analysis_panel with a
bullet containing a src tag, exports it as plain text, and asserts
the tag survives literally.
"""
from __future__ import annotations

from io import StringIO

from rich.console import Console

from finterminal.ui import panels


_ANALYST_PAYLOAD = {
    "ticker": "ITC.NS",
    "variant_perception": "no consensus in context",
    "bull_case": "- Strong returns: ROCE 0.368 [src: fundamentals.roce] and PE 19.10 [src: fundamentals.pe_ttm].",
    "bear_case": "- PE 19.10 [src: fundamentals.pe_ttm] limits upside if multiples contract.",
    "conviction": "Watch Long",
    "confidence": 0.50,
    "assumptions": "- Consolidated metrics obscure segment economics [src: fundamentals.revenue_ttm].",
    "what_would_change": "- Segmental P&L disclosure for FMCG, Hotels [src: news[0]].",
}

_CRITIC_PAYLOAD = {
    "verdict": "REVISE",
    "issues_md": "- [MEDIUM] Peer claim without peer data — no fundamentals.peer_* tags cited.",
    "missing_md": "- Forward EPS estimates and analyst consensus.",
    "confidence_adj": 0.40,
    "raw_text": "...",
}


def _render_to_text(panel_obj) -> str:
    """Render a Rich panel to plain text for assertion."""
    buf = StringIO()
    console = Console(file=buf, width=200, force_terminal=False, record=False)
    console.print(panel_obj)
    return buf.getvalue()


def test_panel_preserves_src_tags_in_bull_case():
    p = panels.analysis_panel(_ANALYST_PAYLOAD)
    out = _render_to_text(p)
    assert "[src: fundamentals.roce]" in out
    assert "[src: fundamentals.pe_ttm]" in out


def test_panel_preserves_src_tags_in_bear_case():
    p = panels.analysis_panel(_ANALYST_PAYLOAD)
    out = _render_to_text(p)
    # bear case also has a tag
    bear_section = out[out.find("bear"):] if "bear" in out else out
    assert "[src: fundamentals.pe_ttm]" in bear_section


def test_panel_preserves_src_tags_in_assumptions_and_what_would_change():
    p = panels.analysis_panel(_ANALYST_PAYLOAD)
    out = _render_to_text(p)
    assert "[src: fundamentals.revenue_ttm]" in out
    assert "[src: news[0]]" in out


def test_panel_preserves_src_tags_in_critic_block():
    p = panels.analysis_panel(_ANALYST_PAYLOAD, critic=_CRITIC_PAYLOAD)
    out = _render_to_text(p)
    # The critic prompt's [MEDIUM] severity prefix is bracketed too — must survive.
    assert "[MEDIUM]" in out
    # And the analyst tags from upstream:
    assert "[src: fundamentals.roce]" in out


def test_panel_keeps_intentional_styling_alongside_escaped_brackets():
    """The escape must NOT kill our own panel borders / colors. Verify
    that section headers ('bull', 'bear', 'critic') still appear.
    Rich strips ANSI in non-terminal mode but section labels are plain text."""
    p = panels.analysis_panel(_ANALYST_PAYLOAD, critic=_CRITIC_PAYLOAD)
    out = _render_to_text(p)
    assert "bull" in out.lower()
    assert "bear" in out.lower()
    assert "critic" in out.lower()
