# Phase 2.5 — Analyst-Grade Layer

> Back to [[Index]] | See also [[ADR-008 Phase 2.5 Analyst-Grade Layer]] · [[01 - Architecture/Agent System]] · [[01 - Architecture/Data Sources]]

**Status:** Planned (after Phase 2 exit criteria pass)
**Target weeks:** 5–7
**Source:** [PLAN.md §6.5](../docs/PLAN.md)

---

## Why this phase exists

After Phase 2, the terminal handles the daily check-in. Phase 2.5 is what turns it from "smart watchlist" into "analyst desk." Every capability answers a specific recurring question a real research process asks every morning.

See [[ADR-008 Phase 2.5 Analyst-Grade Layer]] for the full decision matrix (14 capabilities scored).

---

## Scope summary

8 new agents, ~15 new commands, ~14 new DuckDB tables, optional Sentiment activated.

---

## New commands

| Command | Agent | Data source |
|---|---|---|
| `/transcript TICKER Q3` | Transcript | NSE/BSE, Trendlyne, YouTube+Whisper |
| `/transcript-diff TICKER` | Transcript | Historical transcript store |
| `/consensus TICKER` | Data (extended) | Trendlyne, screener.in |
| `/revisions TICKER 30d` | Data (extended) | Consensus snapshots |
| `/ownership TICKER` | Ownership | NSE/BSE shareholding, SEBI SAST |
| `/flows NIFTY` | Ownership | NSDL/CDSL FII flows |
| `/quality TICKER` | Quality/Forensic | DuckDB (formula-based) |
| `/quality-cohort banking` | Quality/Forensic | DuckDB |
| `/comps TICKER` | Comps | DuckDB, OpenBB |
| `/sector-screen IT value` | Comps | DuckDB, OpenBB |
| `/ceo jensen` | CEO Tracker | YouTube, NSE/BSE filings |
| `/sentiment NIFTY50` | Sentiment (optional) | Grok Live Search |
| `/macro` | Macro | OpenBB, FRED, RBI |
| `/macro-impact TICKER` | Macro | DuckDB macro_series |
| `/events week` | Calendar | NSE/BSE corp actions, RBI/Fed |
| `/screen magic-formula NIFTY500` | (screens library) | DuckDB, OpenBB |

---

## Exit criteria

Tested on a 25-name Indian watchlist (banking, IT, pharma, auto, FMCG):

1. `/transcript TICKER Q3` within 30s (cached) or ≤4 min (audio transcription via Whisper).
2. `/consensus TICKER` shows 90-day revision trend; ≥8 weeks historical snapshots.
3. `/ownership TICKER` shows ≥4 quarter deltas + 30 days of SAST/bulk/block.
4. `/quality TICKER` returns Piotroski + Beneish + Altman + Montier with plain-English breakdown.
5. `/comps TICKER` shows ≥6 peers with 6 multiples each, color-coded.
6. ≥3 non-obvious flags/week across the 25-name watchlist.

---

## Key risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Trendlyne/screener HTML changes break consensus scraping | High | Dual-source (Trendlyne + Screener); `ConsensusSource` interface isolates fragility |
| Small companies don't post concall transcripts | Medium | Fall back to YouTube → faster-whisper; mark `transcript_quality = whisper` |
| Whisper accuracy on Indian-accented English + Hindi | Medium | Use `large-v3`; accept ~5% WER; topic extraction is robust to it |
| Forensic score false positives | Medium | Always show *which components* drive the score; user judges |
| AMFI data is monthly + 10-day lag | High (known) | Display `as_of_date` on every ownership panel |

---

## Open decision before kickoff

**Q4:** Final 10-name CEO list for CEO Tracker (suggested: Jensen Huang, Jamie Dimon, Larry Fink, Satya Nadella, Sundar Pichai, Mukesh Ambani, N. Chandrasekaran, Uday Kotak, Nithin Kamath, Sanjiv Bajaj). Resolve before Phase 2.5 kickoff.
