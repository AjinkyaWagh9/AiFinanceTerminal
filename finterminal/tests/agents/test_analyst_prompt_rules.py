"""Sanity checks that analyst.md contains the prompt rules we rely on.

These guard against accidental deletion / refactor regressions of the
hard-constraint sections (FU-2 tag whitelist, Q-2 conglomerate guard).
The Analyst's behavior depends on these phrases being in the system
prompt; the parser doesn't enforce them.
"""
from __future__ import annotations

from finterminal.agents.analyst import _load_prompt


def test_prompt_loads():
    prompt = _load_prompt()
    assert len(prompt) > 500


def test_prompt_has_src_tag_whitelist():
    prompt = _load_prompt()
    assert "Source tags (HARD CONSTRAINT)" in prompt
    # All seven fundamentals tags must be enumerated:
    for tag in [
        "fundamentals.pe_ttm",
        "fundamentals.eps_ttm",
        "fundamentals.roe",
        "fundamentals.roce",
        "fundamentals.debt_to_equity",
        "fundamentals.revenue_ttm",
        "fundamentals.net_income_ttm",
    ]:
        assert tag in prompt, f"missing tag in whitelist: {tag}"
    # Quote tags:
    for tag in [
        "quote.last_price",
        "quote.change_pct",
        "quote.volume",
        "quote.market_cap",
        "quote.as_of",
    ]:
        assert tag in prompt, f"missing tag in whitelist: {tag}"
    # News convention:
    assert "news[0]" in prompt
    assert "zero-indexed" in prompt.lower()


def test_prompt_forbids_inventing_tags():
    prompt = _load_prompt()
    # Critical anti-hallucination clauses:
    assert "never invent new ones" in prompt.lower()
    assert "fabrication" in prompt.lower()


def test_prompt_has_conglomerate_guard():
    prompt = _load_prompt()
    assert "Conglomerate guard" in prompt
    assert "≥3 distinct revenue segments" in prompt
    # Confidence cap is a hard rule:
    assert "0.55" in prompt
    # By-name list (per spec §3 decision):
    for name in ["Reliance", "ITC", "Larsen & Toubro", "Adani Enterprises", "Bajaj Finserv"]:
        assert name in prompt, f"missing from conglomerate by-name list: {name}"


def test_prompt_keeps_factor_hierarchy_and_munger_inversion():
    """Pre-existing principles must survive the rewrite."""
    prompt = _load_prompt()
    assert "Factor weighting hierarchy" in prompt
    assert "Munger inversion" in prompt
    assert "Variant perception" in prompt
