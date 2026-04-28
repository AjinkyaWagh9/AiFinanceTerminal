# External References

> Back to [[Index]] | See also [[06 - Glossary]] · [[01 - Architecture/Data Sources]]

URLs we reference. Verify any link before relying on it — `/analyze` would catch invented URLs but planning docs won't.

---

## LLM providers

| Resource | URL | Used for |
|---|---|---|
| Anthropic API docs | https://docs.anthropic.com | Claude Sonnet 4.6 / Opus 4.7; supervisor + critic |
| OpenAI API pricing | https://platform.openai.com/docs/pricing | gpt-5 / gpt-5-mini / gpt-5-nano (current supervisor) |
| OpenAI API console | https://platform.openai.com/account | Manage `OPENAI_API_KEY`, model access |
| xAI docs | https://docs.x.ai/docs | grok-3-mini + Live Search (Phase 2.5 sentiment) |
| xAI console | https://console.x.ai | `GROK_API_KEY` provisioning, billing |
| NVIDIA NIM | https://build.nvidia.com | Free OpenAI-compat cloud-burst (Llama, DeepSeek, etc.) |
| Ollama | https://ollama.com | Local LLM runtime (qwen3:8b, phi4-mini) |
| MLX (Apple) | https://github.com/ml-explore/mlx | Apple Silicon ML backend; Ollama uses where available |
| exo (distributed) | https://github.com/exo-explore/exo | [[BACKLOG §1.10]] — multi-Mac inference cluster |

## OpenBB ecosystem

| Resource | URL | Used for |
|---|---|---|
| OpenBB SDK docs | https://docs.openbb.co | The Python SDK we import in `openbb_client.py` |
| OpenBB Hub (PAT) | https://my.openbb.co | Free PAT for paid-tier provider routing |
| OpenBB MCP server | https://docs.openbb.co/platform/getting_started/mcp | Phase 4 nice-to-have; we use SDK in-process |
| OpenBB GitHub | https://github.com/OpenBB-finance/OpenBB | Source; check release notes before upgrading |

## US data providers (Phase 3)

| Resource | URL | Status |
|---|---|---|
| Finnhub | https://finnhub.io | Key live in `.env`; used as quote/news fallback |
| FMP (Financial Modeling Prep) | https://financialmodelingprep.com/developer/docs | Free key live; .NS = 402 paid endpoint; defer to Phase 3 |
| Tiingo | https://www.tiingo.com | Key live; news API is paid tier |
| Alpha Vantage | https://www.alphavantage.co/documentation | Key live; not wired into OpenBB equity endpoints |
| FRED (St. Louis Fed) | https://fred.stlouisfed.org/docs/api/fred | Key live; HTTPS times out from this Mac (network issue) |
| Benzinga | https://www.benzinga.com | Wired live for US news (`provider:benzinga`) |
| SEC EDGAR | https://www.sec.gov/edgar | Phase 3 — 13F, 10-K, 8-K filings |
| EODHD | https://eodhd.com | Paid; ~$20/mo; best India coverage if free layer plateaus |

## Indian data sources (Phase 2.5)

| Resource | URL | Used for |
|---|---|---|
| **NSE India** | https://www.nseindia.com | Quotes, corporate filings, shareholding patterns, bulk/block deals |
| **NSE bhavcopy** | https://www.nseindia.com/all-reports | Daily OHLCV + close-to-close for breadth/A-D |
| **NSE EQUITY_L.csv** | https://archives.nseindia.com/content/equities/EQUITY_L.csv | Phase 2 — autoload ticker→name table |
| **BSE India** | https://www.bseindia.com | Same as NSE for BSE-listed names |
| **SEBI SAST disclosures** | https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doListing=yes&sid=3 | Real-time substantial acquisitions / promoter txns |
| **AMFI portfolio disclosures** | https://www.amfiindia.com/research-information/aum-data | Monthly MF holdings (10-day lag) |
| **NSDL FII data** | https://www.nsdl.co.in/master/fii_FAQ.php | Daily FII gross/net flow |
| **Screener.in** | https://www.screener.in | Live: scraped for fundamentals (commit `1232297`) |
| **Trendlyne** | https://trendlyne.com | Phase 2.5.B — consensus, ownership, broker reports |
| **Moneycontrol** | https://www.moneycontrol.com | RSS live; fundamentals fallback if needed |
| **Livemint** | https://www.livemint.com | RSS live |
| **Economic Times Markets** | https://economictimes.indiatimes.com/markets | RSS live; high-volume single-stock coverage |
| **Business Standard Markets** | https://www.business-standard.com/markets | RSS feed disabled (SSL handshake timeout from this network) |
| **RBI DBIE** | https://dbie.rbi.org.in | Authoritative India 10Y, repo, FX reserves |
| **MOSPI** | https://www.mospi.gov.in | IIP, CPI |
| **GST collections** | https://gst.gov.in | Monthly GST collections |
| **S&P Global PMI India** | https://www.pmi.spglobal.com/Public/Release/PressReleases?language=en-US | Manufacturing + Services PMI press releases |
| **CCIL OIS** | https://www.ccilindia.com | Bond yields, OIS-implied repo expectations |
| **FBIL** | https://www.fbil.org.in | Benchmark G-Sec yields |

## CEO / leader sources ([[ADR-008 Phase 2.5 Analyst-Grade Layer]])

| Resource | URL | Used for |
|---|---|---|
| YouTube Data API | https://developers.google.com/youtube/v3 | Earnings call audio + conference appearances |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper | Local audio → transcript (M4-friendly) |
| Trendlyne concall | https://trendlyne.com/research-reports/all-concall-transcripts | Concall PDF transcripts |

## Tooling docs

| Resource | URL | Used for |
|---|---|---|
| DuckDB docs | https://duckdb.org/docs | Embedded analytical DB (warehouse + Phase 1 store) |
| ChromaDB | https://www.trychroma.com | Embedded vector store (semantic news clustering Phase 2) |
| Rich (Python) | https://rich.readthedocs.io | TUI panels (current REPL) |
| Textual | https://textual.textualize.io | Phase 2+ full-screen TUI app |
| Plotext | https://github.com/piccolomo/plotext | Terminal charts (Phase 2.5 polish) |
| CrewAI | https://docs.crewai.com | Phase 2–2.5 agent orchestration |
| LangGraph | https://langchain-ai.github.io/langgraph | Phase 3+ cyclical agent graphs |
| BeautifulSoup | https://www.crummy.com/software/BeautifulSoup/bs4/doc | HTML parsing (Screener.in, future Trendlyne) |
| httpx | https://www.python-hub.com/package/httpx | HTTP client; happy-eyeballs handles IPv6 issues that break curl |
| pytest | https://docs.pytest.org | Test runner (`uv run pytest tests/`) |
| uv | https://docs.astral.sh/uv | Python package + venv manager |

## Intra-project / GitHub

| Resource | URL |
|---|---|
| GitHub repo | https://github.com/AjinkyaWagh9/Finance-Terminal |
| Latest commit | `1232297` (Indian data layer shipped) |
