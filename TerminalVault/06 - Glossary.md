# Glossary

> Back to [[Index]] | See also [[07 - External References]]

Terms that recur across the FINTERMINAL codebase, ADRs, and PLAN.md sections. One line per term. Indian-finance terms first; tech terms second.

---

## Indian markets

| Term | Meaning |
|---|---|
| **NSE** | National Stock Exchange (Mumbai). Primary Indian equity exchange. Tickers suffixed `.NS` in our system. |
| **BSE** | Bombay Stock Exchange. Older Indian exchange. Tickers suffixed `.BO`. |
| **NIFTY 50** | NSE's flagship index — 50 largest free-float-weighted Indian stocks. |
| **Bank Nifty** | NSE banking-sector index. Critical: price index ≠ banking health (see [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] §6.5.F2). |
| **NIFTY 500** | Broader NSE index, used for screen scope (`/screen magic-formula NIFTY500`). |
| **Sensex** | BSE's flagship 30-stock index. Less liquid than NIFTY for derivatives. |
| **FII** | Foreign Institutional Investors. Their daily flows can drive short-term direction. |
| **DII** | Domestic Institutional Investors (Indian MFs, insurance). Often counter-balance FII flows. |
| **NSDL / CDSL** | The two Indian depositories. Source of free FII flow aggregates. |
| **AMFI** | Association of Mutual Funds in India. Publishes monthly portfolio disclosures (10-day lag). |
| **SEBI** | Securities and Exchange Board of India. Regulator. |
| **SAST** | Substantial Acquisition of Shares and Takeovers. SEBI disclosure regime — promoter buys/sells trigger filings. Real-time data, free. |
| **promoter** | Founder / controlling shareholder (Indian convention). Their buying/selling/pledging is forensic gold. |
| **pledge** | Promoter pledging shares as loan collateral. Rising pledge % is a red flag (Yes Bank, DHFL precedents). |
| **bulk deal** | Single trade > 0.5% of company equity, reported same-day by NSE/BSE. |
| **block deal** | Trade ≥ 5,00,000 shares OR ≥ ₹10 cr value, reported same-day. |
| **CASA** | Current Account + Savings Account ratio. Measures bank deposit franchise quality. Higher = lower funding cost. |
| **NIM** | Net Interest Margin. Bank profitability metric: yield on advances minus cost of funds. |
| **GNPA / NNPA** | Gross / Net Non-Performing Assets. Bank asset-quality metrics. |
| **CRR / SLR** | Cash Reserve / Statutory Liquidity Ratio. RBI-mandated bank reserves. |
| **repo rate** | RBI's policy rate. The lever for [[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]] Layer 2. |
| **OIS** | Overnight Index Swap. Curve implies market-priced future repo rates. |
| **FBIL** | Financial Benchmarks India Ltd. Publishes G-Sec yield benchmarks. |
| **MOSPI** | Ministry of Statistics and Programme Implementation. Source for IIP, CPI. |
| **IIP** | Index of Industrial Production. Monthly Indian growth proxy. |
| **PMI** | Purchasing Managers' Index (S&P Global publishes Indian Mfg + Services). High-frequency growth proxy. |
| **GST** | Goods and Services Tax. Monthly collections are a real-time consumption signal. |
| **CCIL** | Clearing Corporation of India Ltd. Source for OIS curves, bond yields. |
| **DBIE** | Database on Indian Economy (RBI). Authoritative source for India 10Y, FX reserves, repo. |
| **₹Cr** | One crore = 10,000,000 (₹1 cr = 10⁷). Indian convention; our `_parse_number` handles it (`×1e7`). |
| **₹L / ₹Lakh** | One lakh = 100,000 (₹1 L = 10⁵). |

## Forensic / quality scores ([[ADR-008 Phase 2.5 Analyst-Grade Layer]])

| Term | Meaning |
|---|---|
| **Piotroski F-Score** | 9-test accounting-quality score (0–9). ≥7 = high quality. |
| **Beneish M-Score** | 8-variable earnings-manipulation likelihood. M > -1.78 = elevated risk. |
| **Altman Z-Score** | Bankruptcy risk. Z < 1.81 distress, Z > 2.99 safe. Use Z'' for emerging-market non-mfg. |
| **Montier C-Score** | 6-binary "cooking the books" indicators. Score ≥4 = avoid. |
| **DSO / DSI** | Days Sales Outstanding / Inventory. Trends signal earnings quality. |
| **Cash Conversion Cycle** | DSO + DSI − Days Payable. Measures working-capital efficiency. |

## Valuation

| Term | Meaning |
|---|---|
| **PE / P/E (TTM)** | Price-to-Earnings ratio, trailing 12 months. Headline valuation multiple. |
| **EV/EBITDA** | Enterprise Value to EBITDA. Capital-structure-neutral valuation. |
| **P/B** | Price-to-Book. Bank/financials valuation primary. |
| **ROE** | Return on Equity. Net income ÷ shareholder equity. |
| **ROCE** | Return on Capital Employed. (EBIT) ÷ (Equity + Debt). Indian-investor favorite. |
| **D/E** | Debt to Equity ratio. Capital structure leverage. |
| **EY-vs-G10y spread** | Earnings yield (1/PE) minus India 10Y G-Sec yield. Higher = equities relatively cheap vs bonds. |
| **PEG** | PE divided by earnings growth rate. < 1 = GARP candidate. |

## Synthesis-layer concepts ([[ADR-011 3-Layer Macro Heatmap and Synthesis Layer]])

| Term | Meaning |
|---|---|
| **Regime** | Risk_on / risk_off / transition_* / neutral state classification from Layer 1+2 z-scores. |
| **Variant Perception** | Where your view differs from consensus. Lead with this in `/analyze`. |
| **Conviction tier** | Conviction Long / Watch Long / Avoid / Conviction Short. Replaces flat-confidence-only output. |
| **Brier score** | Mean squared error of probabilistic predictions vs realized outcomes. Lower = better calibration. |
| **Reliability diagram** | Plot of stated confidence vs realized hit-rate. Diagonal = perfectly calibrated. |
| **Bias auditor** | Meta-agent that surfaces drift in own output (direction bias, sector bias, confidence drift). |
| **Pair trade** | Long ticker A / short ticker B. Half of buy-side process. `/pair` command in Phase 3. |

## Tech / project-internal

| Term | Meaning |
|---|---|
| **CrewAI** | Role-based agent framework. Used Phase 2 → 2.5. |
| **LangGraph** | Graph-based agent framework with cyclical state. Used Phase 3+ for `/analyze` hot path. |
| **DuckDB** | Embedded analytical database. Our hot-path storage. |
| **ChromaDB** | Embedded vector store. Used for semantic news clustering. |
| **MLX** | Apple Silicon ML framework. Backs Ollama on M-series Macs. |
| **Ollama** | Local LLM runtime. Default for cheap-classifier agents (qwen3:8b, phi4-mini). |
| **NIM** | NVIDIA Inference Microservices. Free OpenAI-compatible cloud burst lane. |
| **Grok Live Search** | xAI feature: Grok models retrieve real-time X posts as part of completion. Used for Sentiment agent. |
| **`asof` (gotcha)** | Reserved keyword in DuckDB (`ASOF JOIN`). We use `as_of` everywhere. See [[Storage]]. |
| **OpenBB** | Open-source financial-data Python SDK. Wraps yfinance, FMP, Tiingo, etc. |
| **OpenBB MCP / API** | The Open Data Platform desktop app exposes both — port 8001 (MCP) and 6900 (REST). We don't use either; SDK is in-process. |
| **happy-eyeballs** | TCP connection algorithm that races IPv4 + IPv6. `httpx` does this; `curl` defaults don't. Cause of FRED + Business Standard timeouts on this Mac. |
| **`_is_indian_ticker`** | `data/openbb_client.py` helper. True iff ticker ends `.NS`/`.BO`. Gates India-first routing. |
| **`as_of`** | Standard column name across our DuckDB schema. Avoids the reserved-keyword trap. |
