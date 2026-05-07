"""Command dispatcher for the REPL.

Each handler takes (args: list[str], console: Console) and renders to the console.
Keeping this sync; LLM-using handlers wrap their async call with asyncio.run().
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from rich.console import Console

from .data import duckdb_store, news_store, openbb_client
from .news.pipeline import run as _pipeline_run
from .data.nse import normalize_ticker
from .ui import panels
from .market_data.ingestion import refresh_prices
from .outcomes.backfill import resolve_pending as _resolve_pending
from .commands_features import features_inspect

logger = logging.getLogger(__name__)


def dispatch(line: str, console: Console) -> None:
    parts = line.split()
    if not parts:
        return
    cmd = parts[0]
    args = parts[1:]

    handler = _COMMANDS.get(cmd)
    if handler is None:
        console.print(panels.error_panel(f"unknown command: {cmd}. type /help"))
        return
    try:
        handler(args, console)
    except _UsageError as exc:
        console.print(panels.error_panel(str(exc), title="usage"))
    except Exception as exc:  # noqa: BLE001 — last-resort REPL guard
        logger.exception("command %s failed", cmd)
        console.print(panels.error_panel(f"{type(exc).__name__}: {exc}"))


class _UsageError(Exception):
    pass


def _require_one(args: list[str], usage: str) -> str:
    if len(args) != 1:
        raise _UsageError(usage)
    return args[0]


# ---------- /help ----------


def _cmd_help(args: list[str], console: Console) -> None:
    console.print(panels.help_panel())


# ---------- /ticker ----------


def _cmd_ticker(args: list[str], console: Console) -> None:
    raw = _require_one(args, "/ticker SYMBOL  (e.g. /ticker RELIANCE)")
    ticker = normalize_ticker(raw)

    with console.status(f"fetching {ticker}…", spinner="dots"):
        quote = openbb_client.fetch_quote(ticker)
        try:
            fundamentals = openbb_client.fetch_fundamentals(ticker)
        except Exception as exc:  # noqa: BLE001 — fundamentals are best-effort
            logger.warning("fundamentals unavailable for %s: %s", ticker, exc)
            fundamentals = None

    conn = duckdb_store.get_conn()
    try:
        duckdb_store.upsert_quote(conn, quote)
        if fundamentals:
            duckdb_store.upsert_fundamentals(conn, fundamentals)
    finally:
        conn.close()

    console.print(panels.ticker_panel(quote, fundamentals))


# ---------- /news ----------


def _cmd_news(args: list[str], console: Console) -> None:
    raw = _require_one(args, "/news SYMBOL  (e.g. /news INFY)")
    ticker = normalize_ticker(raw)

    with console.status(f"fetching news for {ticker}…", spinner="dots"):
        try:
            items = openbb_client.fetch_news(ticker, limit=20)
        except RuntimeError as exc:
            # yfinance returns Empty for many Indian tickers; render as empty rather than error.
            # Phase 2 adds an RSS aggregator (Mint, MoneyControl, ET) per PLAN.md §4.4.
            logger.info("news empty for %s: %s", ticker, exc)
            items = []

    if items:
        conn = duckdb_store.get_conn()
        try:
            duckdb_store.upsert_news(conn, items)
        finally:
            conn.close()

    console.print(panels.news_table(items, ticker))


# ---------- /watch ----------


def _cmd_watch(args: list[str], console: Console) -> None:
    if not args:
        raise _UsageError("/watch add SYMBOL | /watch list | /watch remove SYMBOL")
    sub = args[0]
    rest = args[1:]
    conn = duckdb_store.get_conn()
    try:
        if sub == "list":
            if rest:
                raise _UsageError("/watch list  (no args)")
            console.print(panels.watchlist_table(duckdb_store.list_watchlist(conn)))
            return
        if sub == "add":
            if not rest:
                raise _UsageError("/watch add SYMBOL [notes...]")
            ticker = normalize_ticker(rest[0])
            notes = " ".join(rest[1:]) if len(rest) > 1 else None
            duckdb_store.add_to_watchlist(conn, ticker, notes)
            console.print(panels.info_panel(f"added [bold]{ticker}[/]"))
            return
        if sub == "remove":
            if len(rest) != 1:
                raise _UsageError("/watch remove SYMBOL")
            ticker = normalize_ticker(rest[0])
            duckdb_store.remove_from_watchlist(conn, ticker)
            console.print(panels.info_panel(f"removed [bold]{ticker}[/]"))
            return
        raise _UsageError(f"unknown subcommand: {sub}")
    finally:
        conn.close()


# ---------- /analyze ----------


def _parse_analyze_args(args: list[str]) -> tuple[str, bool]:
    """Returns (ticker, fresh). Raises _UsageError on invalid input."""
    fresh = False
    positionals: list[str] = []
    for a in args:
        if a == "--fresh":
            fresh = True
        elif a.startswith("--"):
            raise _UsageError(f"unknown flag: {a}")
        else:
            positionals.append(a)
    if len(positionals) != 1:
        raise _UsageError("/analyze SYMBOL [--fresh]  (e.g. /analyze RELIANCE)")
    return positionals[0], fresh


def _cmd_analyze(args: list[str], console: Console) -> None:
    raw, fresh = _parse_analyze_args(args)
    ticker = normalize_ticker(raw)

    from .agents.analyze_flow import AnalysisError, run_analyze

    conn = duckdb_store.get_conn()
    try:
        with console.status(
            f"analyzing {ticker} (Analyst + Critic)…", spinner="dots"
        ):
            try:
                result = asyncio.run(run_analyze(ticker, conn, fresh=fresh))
            except AnalysisError as exc:
                console.print(panels.error_panel(str(exc), title="/analyze failed"))
                return
    finally:
        conn.close()

    panel_kwargs: dict = {}
    if result.degraded:
        panel_kwargs["critic_error"] = result.critic_error or "unknown"
    elif result.critic_payload is not None:
        panel_kwargs["critic"] = result.critic_payload

    console.print(panels.analysis_panel(result.analyst_payload, **panel_kwargs))


# ---------- /refresh-news ----------


def _cmd_refresh_news(args: list[str], console: Console) -> None:
    conn = duckdb_store.get_conn()
    try:
        with console.status("refreshing news pipeline…", spinner="dots"):
            result = _pipeline_run(conn)
    finally:
        conn.close()
    console.print(
        f"Refreshed [bold]{result.n_stories}[/bold] stories → "
        f"[bold]{result.n_clusters}[/bold] clusters in [bold]{result.runtime_s:.1f}s[/bold]. "
        f"[dim]{result.n_lineage_links} lineage links from yesterday.[/dim]"
    )


# ---------- /trends ----------


def _cmd_trends(args: list[str], console: Console) -> None:
    sector = args[0] if args else None
    conn = duckdb_store.get_conn()
    try:
        clusters = news_store.latest_clusters(conn)
    finally:
        conn.close()
    console.print(panels.render_trends_table(clusters, sector_filter=sector))


# ---------- /refresh-prices ----------


def _cmd_refresh_prices(args: list[str], console: Console) -> None:
    """Pull NSE bhavcopy + indices for the last 30 calendar days (idempotent)."""
    end = date.today() - timedelta(days=1)  # NSE doesn't publish today's bhav until late evening
    start = end - timedelta(days=30)
    conn = duckdb_store.get_conn()
    try:
        with console.status("refreshing prices…", spinner="dots"):
            result = refresh_prices(conn, start=start, end=end)
    finally:
        conn.close()
    console.print(
        f"Attempted [bold]{len(result['dates_attempted'])}[/bold] trading days; "
        f"skipped [bold]{len(result['dates_skipped_holiday'])}[/bold] non-trading days."
    )


# ---------- /backfill-outcomes ----------


def _cmd_backfill_outcomes(args: list[str], console: Console) -> None:
    """Resolve forward returns for every signal whose horizon has matured."""
    conn = duckdb_store.get_conn()
    try:
        with console.status("resolving pending signal outcomes…", spinner="dots"):
            n = _resolve_pending(conn)
    finally:
        conn.close()
    console.print(f"Resolved [bold]{n}[/bold] signal/horizon pairs.")


# ---------- /features ----------


def _cmd_features(args: list[str], console: Console) -> None:
    """Inspect features for a signal."""
    signal_id = _require_one(args, "/features SIGNAL_ID  (e.g. /features sig-20250101-001)")
    conn = duckdb_store.get_conn()
    try:
        features_inspect(conn, signal_id)
    finally:
        conn.close()


_COMMANDS = {
    "/help": _cmd_help,
    "/ticker": _cmd_ticker,
    "/news": _cmd_news,
    "/watch": _cmd_watch,
    "/analyze": _cmd_analyze,
    "/refresh-news": _cmd_refresh_news,
    "/refresh-prices": _cmd_refresh_prices,
    "/trends": _cmd_trends,
    "/backfill-outcomes": _cmd_backfill_outcomes,
    "/features": _cmd_features,
}
