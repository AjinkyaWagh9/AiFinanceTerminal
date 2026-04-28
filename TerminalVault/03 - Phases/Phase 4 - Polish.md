# Phase 4 — Polish, Reports, and Optimization

> Back to [[Index]] | See also [[03 - Phases/Phase 3 - US + Routing]]

**Status:** Planned (ongoing after Phase 3)
**Source:** [PLAN.md §6 Phase 4](../docs/PLAN.md)

---

## Scope

- **Confidence calibration tracking:** every `/analyze` output writes its call + confidence to DuckDB; after 3 months, compute Brier score and reliability diagram.
- **Export to Markdown reports:** `/report TICKER` produces analyst-style note with citations; optional Pandoc → PDF.
- **Caching layer:** DiskCache or Redis in front of OpenBB and scrapers (TTL: quotes 60s, fundamentals 24h, ownership weekly).
- **Alert scheduler:** daemon watching watchlist; triggers on price moves, sentiment flips, pledge changes, consensus revisions. Channels: macOS notifications, Telegram bot, optional email.
- **Documentation + public README** if open-sourcing (open question Q6 in BACKLOG.md).
- **Auto-tier-up:** Critic-driven escalation from Sonnet to Opus when confidence falls below threshold.
- **matplotlib charts** via Textual's `pyplot` widget.

---

## Key commands added

| Command | Notes |
|---|---|
| `/report TICKER` | Markdown analyst note with citations; Pandoc → PDF optional |
| Calibration dashboard | Brier score, reliability diagram on past analyses |

---

## Deferred items from BACKLOG.md promoted here

| Item | Trigger |
|---|---|
| §1.6 Background alert scheduler | Missing ≥1 actionable event/week because not at the terminal |
| §1.7 Confidence calibration | 3 months of analyses in DuckDB |
| §1.8 Export reports | First time you want to send analysis to someone |
| §1.9 Caching layer | Rate-limited by OpenBB / Trendlyne / SEBI |

---

## What stays in BACKLOG permanently

DCF, alternative data, order execution, mobile/web clients, multi-user. See [[ADR-007 Non-Goals — No DCF, No Alt-Data, No Backtesting]].
