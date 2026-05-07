"""Rich panel renderers for the FINTERMINAL REPL."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _escape_markup(s: str | None) -> str:
    """Escape Rich markup brackets in LLM-generated content.

    The Analyst emits [src: quote.last_price]-style citations and the
    Critic emits [HIGH]/[MEDIUM]/[LOW] severity prefixes. Rich's Panel
    and Text constructors interpret bracketed text as style markup and
    silently strip unknown styles. Escaping `[` to `\\[` makes Rich
    render the brackets literally while preserving our own intentional
    markup (which we pass via Text.from_markup or styled Text.append).
    """
    if s is None:
        return ""
    return s.replace("[", r"\[")


def banner() -> Panel:
    return Panel(
        "[bold cyan]FINTERMINAL[/] v0.1 — Phase 1\n"
        "Type [bold]/help[/] for commands, [bold]/quit[/] to exit.",
        border_style="cyan",
    )


def help_panel() -> Panel:
    body = (
        "[bold]Commands[/]\n"
        "  [cyan]/ticker[/] SYMBOL          quote + fundamentals\n"
        "  [cyan]/news[/] SYMBOL            recent headlines\n"
        "  [cyan]/watch add[/] SYMBOL       add to watchlist\n"
        "  [cyan]/watch list[/]             show watchlist\n"
        "  [cyan]/watch remove[/] SYMBOL    drop from watchlist\n"
        "  [cyan]/analyze[/] SYMBOL         supervised bull/bear (model per agents.yaml)\n"
        "  [cyan]/refresh-news[/]             pull + cluster today's market news\n"
        "  [cyan]/trends[/] [SECTOR]          show story clusters (optional sector filter)\n"
        "  [cyan]/help[/]                   this message\n"
        "  [cyan]/quit[/]                   exit\n\n"
        "[bold]Symbol forms[/]\n"
        "  [dim]Bare symbols default to NSE (Indian-first).[/]\n"
        "  [cyan]RELIANCE[/]                  → RELIANCE.NS  (NSE)\n"
        "  [cyan]NSE:HDFC[/]                  → HDFC.NS\n"
        "  [cyan]BSE:RELIANCE[/]              → RELIANCE.BO\n"
        "  [cyan]US:AAPL[/]  [cyan]US:TSLA[/]          → bare US ticker (yfinance / FMP / Benzinga)"
    )
    return Panel(body, title="help", border_style="cyan")


def error_panel(message: str, *, title: str = "error") -> Panel:
    return Panel(f"[red]{message}[/]", title=title, border_style="red")


def info_panel(message: str, *, title: str = "info") -> Panel:
    return Panel(message, title=title, border_style="yellow")


# ---------- /ticker ----------


def _color_change(change_pct: float | None) -> str:
    if change_pct is None:
        return "white"
    abs_pct = abs(change_pct)
    if abs_pct > 5:
        return "yellow"
    return "green" if change_pct > 0 else "red" if change_pct < 0 else "white"


def _fmt_money(v: float | int | None, suffix: str = "") -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e7:
        return f"{v/1e7:,.2f} cr{suffix}"
    if abs(v) >= 1e5:
        return f"{v/1e5:,.2f} L{suffix}"
    return f"{v:,.2f}{suffix}"


def _fmt_num(v: float | int | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:,.{decimals}f}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def ticker_panel(quote: dict, fundamentals: dict | None) -> Panel:
    ticker = quote["ticker"]
    last_price = quote.get("last_price")
    change_pct = quote.get("change_pct")
    color = _color_change(change_pct)

    header = Text()
    header.append(f"{ticker}  ", style="bold cyan")
    header.append(f"{_fmt_num(last_price)}", style=f"bold {color}")
    header.append(f"   {_fmt_pct(change_pct)}", style=color)

    table = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
    table.add_column("k", style="dim")
    table.add_column("v")
    table.add_row("Volume", _fmt_money(quote.get("volume")))
    table.add_row("Market cap", _fmt_money(quote.get("market_cap")))

    if fundamentals:
        table.add_row("", "")
        table.add_row("[bold]Fundamentals[/]", "")
        table.add_row("P/E (TTM)", _fmt_num(fundamentals.get("pe_ttm")))
        table.add_row("EPS (TTM)", _fmt_num(fundamentals.get("eps_ttm")))
        table.add_row("ROE", _fmt_num(fundamentals.get("roe"), 3))
        table.add_row("ROCE", _fmt_num(fundamentals.get("roce"), 3))
        table.add_row("D/E", _fmt_num(fundamentals.get("debt_to_equity")))
        table.add_row("Revenue (TTM)", _fmt_money(fundamentals.get("revenue_ttm")))
        table.add_row("Net income (TTM)", _fmt_money(fundamentals.get("net_income_ttm")))

    as_of = quote.get("as_of")
    footer = f"[dim]as of {as_of.isoformat() if hasattr(as_of, 'isoformat') else as_of} · src: {quote.get('provider', '?')}[/]"
    return Panel(
        Columns([header, table], padding=(0, 4), expand=False),
        title=ticker,
        subtitle=footer,
        border_style=color,
    )


# ---------- /news ----------


def news_table(items: list[dict], ticker: str) -> Table:
    table = Table(title=f"{ticker} — recent news", border_style="cyan", expand=True)
    table.add_column("date", style="dim", no_wrap=True)
    table.add_column("source", style="cyan", no_wrap=True)
    table.add_column("headline")
    if not items:
        table.add_row("—", "—", "[dim]no news returned[/]")
        return table
    for n in items:
        published = n.get("published_at")
        if hasattr(published, "strftime"):
            date_str = published.strftime("%Y-%m-%d")
        elif published:
            date_str = str(published)[:10]
        else:
            date_str = "—"
        table.add_row(date_str, n.get("source") or "—", n.get("headline") or "—")
    return table


# ---------- /watch ----------


def watchlist_table(rows: list[dict]) -> Table:
    table = Table(title="watchlist", border_style="cyan")
    table.add_column("ticker", style="bold cyan")
    table.add_column("added", style="dim")
    table.add_column("notes")
    if not rows:
        table.add_row("—", "—", "[dim]empty — add with /watch add SYMBOL[/]")
        return table
    for r in rows:
        added = r.get("added_at")
        added_str = added.strftime("%Y-%m-%d") if hasattr(added, "strftime") else str(added or "—")
        table.add_row(r["ticker"], added_str, r.get("notes") or "")
    return table


# ---------- /analyze ----------


def _confidence_gauge(conf: float) -> Text:
    """Renders confidence as a 20-cell bar with color thresholds."""
    cells = max(0, min(20, int(round(conf * 20))))
    if conf >= 0.7:
        color = "green"
    elif conf >= 0.4:
        color = "yellow"
    else:
        color = "red"
    bar = Text()
    bar.append("█" * cells, style=color)
    bar.append("░" * (20 - cells), style="dim")
    bar.append(f"  {conf:.2f}", style=f"bold {color}")
    return bar


_CONVICTION_STYLE = {
    "Conviction Long": ("bold green", "▲▲"),
    "Watch Long": ("yellow", "▲"),
    "Avoid": ("dim white", "—"),
    "Conviction Short": ("bold red", "▼▼"),
    "Pair-Short": ("red", "▼"),
}


def analysis_panel(
    analysis: dict,
    critic: dict | None = None,
    critic_error: str | None = None,
) -> Panel:
    """analysis = {ticker, variant_perception, bull_case, bear_case, conviction,
                  confidence, assumptions, what_would_change}.

    critic (optional) = {verdict, issues_md, missing_md, confidence_adj}.
    critic_error (optional) = string explaining why Critic was unavailable.
    Pass at most one of (critic, critic_error). When both are None, the panel
    renders today's pre-4a layout — no behavioral regression for callers.
    """
    variant = (analysis.get("variant_perception") or "").strip()
    variant_panel = (
        Panel(_escape_markup(variant), title="variant perception", border_style="magenta")
        if variant and "no consensus" not in variant.lower()
        else None
    )

    bull_text = analysis.get("bull_case")
    bear_text = analysis.get("bear_case")
    bull = Panel(
        _escape_markup(bull_text) if bull_text else "[dim]—[/]",
        title="bull",
        border_style="green",
    )
    bear = Panel(
        _escape_markup(bear_text) if bear_text else "[dim]—[/]",
        title="bear",
        border_style="red",
    )

    body = Table.grid(expand=True)
    body.add_column(ratio=1)
    body.add_column(ratio=1)
    body.add_row(bull, bear)

    # Conviction + confidence (with optional critic adjustment) on a single line
    conv = analysis.get("conviction")
    confidence = analysis.get("confidence")
    summary = Text()
    if conv and conv in _CONVICTION_STYLE:
        style, glyph = _CONVICTION_STYLE[conv]
        summary.append(f"{glyph} {conv}", style=style)
        summary.append("    ")
    elif conv:
        summary.append(f"conviction: {conv}    ", style="dim")
    if confidence is None:
        summary.append("confidence: —", style="dim")
    else:
        summary.append("confidence  ")
        summary.append(_confidence_gauge(float(confidence)))
        if critic and critic.get("confidence_adj") is not None:
            summary.append(f"  →  {critic['confidence_adj']:.2f} (critic)",
                           style="bold yellow")

    raw_assumptions = analysis.get("assumptions")
    raw_wwcm = analysis.get("what_would_change")
    assumptions = _escape_markup(raw_assumptions) if raw_assumptions else "[dim]—[/]"
    wwcm = _escape_markup(raw_wwcm) if raw_wwcm else "[dim]—[/]"

    footer = Table.grid(expand=True)
    footer.add_column(ratio=1)
    footer.add_column(ratio=1)
    footer.add_row(
        Panel(assumptions, title="assumptions", border_style="cyan"),
        Panel(wwcm, title="what would change my mind", border_style="cyan"),
    )

    stack = Table.grid(expand=True)
    stack.add_column()
    if variant_panel is not None:
        stack.add_row(variant_panel)
    stack.add_row(body)
    stack.add_row(summary)
    stack.add_row(footer)

    if critic is not None:
        verdict = critic.get("verdict") or "?"
        verdict_color = {
            "ACCEPT": "green", "REVISE": "yellow", "REJECT": "red",
        }.get(verdict, "white")
        crit_body = Text()
        crit_body.append(f"verdict: {verdict}\n", style=f"bold {verdict_color}")
        if critic.get("issues_md"):
            crit_body.append("\nIssues:\n", style="bold")
            crit_body.append(critic["issues_md"] + "\n")
        if critic.get("missing_md"):
            crit_body.append("\nMissing:\n", style="bold")
            crit_body.append(critic["missing_md"] + "\n")
        stack.add_row(Panel(crit_body, title="critic", border_style=verdict_color))
    elif critic_error is not None:
        stack.add_row(Panel(
            Text(f"Critic unavailable: {critic_error}", style="dim italic"),
            title="critic", border_style="dim",
        ))

    ts = analysis.get("created_at") or datetime.now(timezone.utc)
    subtitle = f"[dim]{ts.isoformat() if hasattr(ts, 'isoformat') else ts}[/]"
    return Panel(
        stack,
        title=f"/analyze {analysis.get('ticker', '?')}",
        subtitle=subtitle,
        border_style="cyan",
    )


# ---------- helpers exposed for tests ----------


def format_quote_for_context(quote: dict) -> str:
    return (
        "## Quote\n"
        f"- last_price: {_fmt_num(quote.get('last_price'))} [src: quote.last_price]\n"
        f"- change_pct: {_fmt_pct(quote.get('change_pct'))} [src: quote.change_pct]\n"
        f"- volume: {_fmt_money(quote.get('volume'))} [src: quote.volume]\n"
        f"- market_cap: {_fmt_money(quote.get('market_cap'))} [src: quote.market_cap]\n"
        f"- as_of: {quote.get('as_of')} [src: quote.as_of]\n"
    )


def format_fundamentals_for_context(f: dict | None) -> str:
    if not f:
        return "## Fundamentals\n- data unavailable\n"
    return (
        "## Fundamentals\n"
        f"- pe_ttm: {_fmt_num(f.get('pe_ttm'))} [src: fundamentals.pe_ttm]\n"
        f"- eps_ttm: {_fmt_num(f.get('eps_ttm'))} [src: fundamentals.eps_ttm]\n"
        f"- roe: {_fmt_num(f.get('roe'), 3)} [src: fundamentals.roe]\n"
        f"- roce: {_fmt_num(f.get('roce'), 3)} [src: fundamentals.roce]\n"
        f"- debt_to_equity: {_fmt_num(f.get('debt_to_equity'))} [src: fundamentals.debt_to_equity]\n"
        f"- revenue_ttm: {_fmt_money(f.get('revenue_ttm'))} [src: fundamentals.revenue_ttm]\n"
        f"- net_income_ttm: {_fmt_money(f.get('net_income_ttm'))} [src: fundamentals.net_income_ttm]\n"
    )


def format_news_for_context(items: list[dict]) -> str:
    if not items:
        return "## Recent News\n- data unavailable\n"
    out = ["## Recent News"]
    for i, n in enumerate(items[:10]):
        published = n.get("published_at")
        date_str = (
            published.strftime("%Y-%m-%d")
            if hasattr(published, "strftime")
            else (str(published)[:10] if published else "—")
        )
        out.append(
            f"- [{date_str}] {n.get('source') or '?'}: "
            f"{n.get('headline') or '—'} [src: news[{i}]]"
        )
    return "\n".join(out) + "\n"


def build_context_block(
    ticker: str,
    quote: dict,
    fundamentals: dict | None,
    news: list[dict],
) -> str:
    return (
        f"# {ticker}\n\n"
        + format_quote_for_context(quote)
        + "\n"
        + format_fundamentals_for_context(fundamentals)
        + "\n"
        + format_news_for_context(news)
    )


# ---------- /trends ----------


def render_trends_table(clusters: list[dict], sector_filter: str | None = None) -> Table | Panel:
    """Render /trends output. clusters is from news_store.latest_clusters().

    Each cluster dict has: id, as_of, story_count, source_count, top_tickers,
    dominant_sector, headline, first_seen, story_count_delta, day_n.
    """
    if not clusters:
        return Panel(
            "[dim]No trend data. Run [bold]/refresh-news[/bold] first.[/dim]",
            title="Trends",
            border_style="dim",
        )

    if sector_filter:
        clusters = [c for c in clusters if (c.get("dominant_sector") or "").lower() == sector_filter.lower()]

    if not clusters:
        return Panel(
            f"[dim]No clusters for sector [bold]{sector_filter}[/bold].[/dim]",
            title=f"Trends — {sector_filter}",
            border_style="dim",
        )

    table = Table(
        title=f"Trends — {sector_filter or 'All sectors'}",
        border_style="cyan",
        show_lines=False,
        expand=True,
    )
    table.add_column("Cluster", style="dim", width=8)
    table.add_column("Stories", justify="right", width=7)
    table.add_column("Sources", justify="right", width=7)
    table.add_column("Top Tickers", width=22)
    table.add_column("Headline", ratio=1)
    table.add_column("First Seen", width=11)
    table.add_column("Momentum", width=12)

    for c in clusters:
        cluster_id = (c.get("id") or "")[:6]
        story_count = str(c.get("story_count", ""))
        source_count = str(c.get("source_count", ""))
        tickers = ", ".join((c.get("top_tickers") or [])[:3])
        rep_headline = c.get("headline") or ""
        headline = _escape_markup(rep_headline[:80] if rep_headline else "")
        first_seen = ""
        fs = c.get("first_seen")
        if fs:
            try:
                first_seen = str(fs)[:10]
            except Exception:
                pass

        # Momentum badge
        delta = c.get("story_count_delta", 0) or 0
        day_n = (c.get("day_n") or 0) + 1  # day_n from lineage = parent count; +1 = today
        if day_n <= 1:
            momentum = ""
        elif delta > 0:
            momentum = f"[green]▲{delta} (Day {day_n})[/green]"
        elif delta < 0:
            momentum = f"[red]▼{abs(delta)} (Day {day_n})[/red]"
        else:
            momentum = f"[dim]· (Day {day_n})[/dim]"

        table.add_row(cluster_id, story_count, source_count, tickers, headline, first_seen, momentum)

    as_of = (clusters[0].get("as_of") or "") if clusters else ""
    table.caption = f"as_of {as_of} · run [bold]/refresh-news[/bold] for fresh data"
    return table
