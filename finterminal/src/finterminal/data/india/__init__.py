"""India-specific data sources.

Free sources for Indian markets (NSE/BSE) where global APIs (FMP, Tiingo,
Alpha Vantage) have weak / paid-only coverage. Built per the input.md feedback
that prioritized building a custom Indian data layer over chasing global APIs.

Modules:
- screener_in: fundamentals (PE, ROCE, ROE, debt/equity, revenue, net income)
  scraped from screener.in's stable HTML.

Phase 2.5 will add:
- moneycontrol_rss: Indian financial news RSS aggregation
- trendlyne_consensus: broker consensus + revisions
- nse_filings: corporate announcements, SAST disclosures
- amfi_holdings: mutual fund portfolio disclosures
"""
