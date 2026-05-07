"""Tag-discipline regression tests (FU-2).

Guarantees: the Critic's source dossier and the Analyst's context block
emit the SAME [src: ...] tags so the Critic can verify analyst citations
against an authoritative reference. Drift between these two builders was
the root cause of the 4a smoke critique noise.
"""
from __future__ import annotations

import re

from finterminal.agents._dossier import build_source_dossier
from finterminal.ui.panels import build_context_block


_TAG_RE = re.compile(r"\[src:\s*([^\]]+)\]")


def _extract_src_tags(text: str) -> set[str]:
    return {m.strip() for m in _TAG_RE.findall(text)}


_QUOTE_FULL = {
    "ticker": "RELIANCE.NS",
    "last_price": 1413.20,
    "change_pct": 2.31,
    "volume": 8090000,
    "market_cap": None,  # often missing — must still surface as a tag
    "as_of": "2026-04-29T10:19:54+00:00",
    "provider": "yfinance",
}
_FUND_FULL = {
    "pe_ttm": 43.6,
    "eps_ttm": 32.4,
    "roe": 0.079,
    "roce": 0.079,
    "debt_to_equity": 0.41,
    "revenue_ttm": 505649.0,
    "net_income_ttm": 43851.0,
}
_NEWS = [
    {"source": "Mint", "headline": "Government proposes higher ethanol blending",
     "published_at": "2026-04-28"},
    {"source": "Moneycontrol", "headline": "Reliance Jio adds 4.2M subscribers",
     "published_at": "2026-04-27"},
]


def test_dossier_tags_are_subset_of_context_block_tags():
    """Every [src: ...] tag emitted by the dossier must also exist in
    build_context_block. The Critic uses the dossier to verify analyst
    tags drawn from the context block — the dossier must be a faithful
    subset of the same vocabulary."""
    context_tags = _extract_src_tags(
        build_context_block("RELIANCE.NS", _QUOTE_FULL, _FUND_FULL, _NEWS)
    )
    dossier_tags = _extract_src_tags(
        build_source_dossier("RELIANCE.NS", _QUOTE_FULL, _FUND_FULL, _NEWS)
    )
    assert dossier_tags, "dossier emitted no [src: ...] tags at all"
    extra = dossier_tags - context_tags
    assert not extra, f"dossier emitted tags not in context block: {extra}"


def test_dossier_emits_dotted_path_tags():
    out = build_source_dossier("RELIANCE.NS", _QUOTE_FULL, _FUND_FULL, _NEWS)
    assert "[src: quote.last_price]" in out
    assert "[src: fundamentals.pe_ttm]" in out
    assert "[src: news[0]]" in out


def test_dossier_does_not_emit_short_codes():
    out = build_source_dossier("RELIANCE.NS", _QUOTE_FULL, _FUND_FULL, _NEWS)
    assert "[QUOTE]" not in out
    assert "[FUND-PE]" not in out
    assert "[FUND-ROE]" not in out
    assert "[NEWS-1]" not in out


def test_dossier_surfaces_unavailable_quote_fields():
    """volume and market_cap are often missing from quote dicts; the
    dossier must still list the tag so the analyst can cite 'data
    unavailable' rather than fabricating a value."""
    quote_thin = {
        "ticker": "X",
        "last_price": 100.0,
        "change_pct": 0.0,
        "as_of": "2026-04-29",
        "provider": "stub",
        # volume + market_cap absent
    }
    out = build_source_dossier("X", quote_thin, None, [])
    assert "[src: quote.volume]" in out
    assert "[src: quote.market_cap]" in out


def test_dossier_news_tags_are_zero_indexed():
    out = build_source_dossier("RELIANCE.NS", _QUOTE_FULL, _FUND_FULL, _NEWS)
    assert "[src: news[0]]" in out
    assert "[src: news[1]]" in out
    # 1-indexed form must NOT appear
    assert "[src: news[2]]" not in out  # only 2 news items, indices 0..1
