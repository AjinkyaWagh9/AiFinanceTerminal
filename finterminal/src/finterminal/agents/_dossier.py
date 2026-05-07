"""Compact source dossier for the Critic.

The Analyst gets the full context block (`ui.panels.build_context_block`).
The Critic does NOT need full news bodies — it needs to verify
[src: ...] tags from the Analyst's output. The dossier is a compact
SUBSET of build_context_block's tag vocabulary: same tag names, same
conventions, news bodies trimmed to headlines only.

Tag scheme (must match build_context_block exactly):
  Quote:        quote.last_price | quote.change_pct | quote.volume |
                quote.market_cap | quote.as_of
  Fundamentals: fundamentals.pe_ttm | fundamentals.eps_ttm |
                fundamentals.roe | fundamentals.roce |
                fundamentals.debt_to_equity | fundamentals.revenue_ttm |
                fundamentals.net_income_ttm
  News:         news[0], news[1], ... news[N-1]   (0-indexed)

A tag whose value is "—" is still a valid tag — the analyst may cite it
to acknowledge "data unavailable", but must not fabricate the value.

Output is a stable, deterministic string — feed it directly to the
Critic LLM as the user message body.
"""
from __future__ import annotations

from typing import Any


def _fmt_or_dash(v: Any, decimals: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    return str(v)


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def _render_quote(q: dict) -> list[str]:
    last_price = _fmt_or_dash(q.get("last_price"))
    change = _fmt_pct(q.get("change_pct"))
    volume = _fmt_or_dash(q.get("volume"), decimals=0)
    market_cap = _fmt_or_dash(q.get("market_cap"), decimals=0)
    as_of = q.get("as_of") or "—"
    provider = q.get("provider", "?")
    return [
        f"# Quote ({q.get('ticker', '?')}, provider: {provider})",
        f"- last_price: {last_price} [src: quote.last_price]",
        f"- change_pct: {change} [src: quote.change_pct]",
        f"- volume: {volume} [src: quote.volume]",
        f"- market_cap: {market_cap} [src: quote.market_cap]",
        f"- as_of: {as_of} [src: quote.as_of]",
    ]


def _render_fundamentals(f: dict | None) -> list[str]:
    if not f:
        return ["# Fundamentals", "- fundamentals unavailable"]
    return [
        "# Fundamentals",
        f"- pe_ttm: {_fmt_or_dash(f.get('pe_ttm'))} [src: fundamentals.pe_ttm]",
        f"- eps_ttm: {_fmt_or_dash(f.get('eps_ttm'))} [src: fundamentals.eps_ttm]",
        f"- roe: {_fmt_or_dash(f.get('roe'), 3)} [src: fundamentals.roe]",
        f"- roce: {_fmt_or_dash(f.get('roce'), 3)} [src: fundamentals.roce]",
        f"- debt_to_equity: {_fmt_or_dash(f.get('debt_to_equity'))} [src: fundamentals.debt_to_equity]",
        f"- revenue_ttm: {_fmt_or_dash(f.get('revenue_ttm'))} [src: fundamentals.revenue_ttm]",
        f"- net_income_ttm: {_fmt_or_dash(f.get('net_income_ttm'))} [src: fundamentals.net_income_ttm]",
    ]


def _render_news(news: list[dict]) -> list[str]:
    if not news:
        return ["# News", "- no news returned"]
    lines = ["# News (0-indexed)"]
    for i, n in enumerate(news):
        published = n.get("published_at")
        date_str = (
            published.strftime("%Y-%m-%d") if hasattr(published, "strftime")
            else (str(published)[:10] if published else "—")
        )
        source = n.get("source") or "?"
        headline = (n.get("headline") or "—").strip()
        if len(headline) > 140:
            headline = headline[:137] + "…"
        lines.append(f'- "{headline}" ({source}, {date_str}) [src: news[{i}]]')
    return lines


def build_source_dossier(
    ticker: str,
    quote: dict,
    fundamentals: dict | None,
    news: list[dict],
) -> str:
    """Returns the compact source dossier string for Critic input."""
    parts: list[str] = [f"SOURCES AVAILABLE TO THE ANALYST ({ticker}):", ""]
    parts.extend(_render_quote(quote))
    parts.append("")
    parts.extend(_render_fundamentals(fundamentals))
    parts.append("")
    parts.extend(_render_news(news))
    parts.append("")
    parts.append(
        "VERIFY: every numeric or qualitative claim in the analyst's "
        "output should map to one of the source tags listed above. A tag "
        "whose value is \"—\" is still valid — the analyst may cite it "
        "to acknowledge data unavailable, but must not fabricate the "
        "value. Flag any tag that is not in the list above as a fabrication."
    )
    return "\n".join(parts)
