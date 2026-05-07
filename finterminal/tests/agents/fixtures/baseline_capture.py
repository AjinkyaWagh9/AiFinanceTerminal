"""Captures a non-regression baseline of today's parse_analysis() output.

Run via:  uv run python tests/agents/fixtures/baseline_capture.py

This script is intentionally separate from pytest. It produces a deterministic
JSON snapshot — generated *once*, before the 4a refactor begins — that future
multi-agent flow tests assert against.

If the captured shape ever needs to change (e.g., analyst.md gains an 8th
section), regenerate by re-running this script and committing the new JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

from finterminal.agents.analyst import parse_analysis

# A representative LLM-style response. Mirrors analyst.md v2's seven-section format.
SAMPLE_RESPONSE = """## Variant Perception
Consensus is broadly bullish on capex pipeline; we are skeptical because new-energy capex has not yet shown unit-economics that justify the multiple. [src: news[2]]

## Bull Case
- Refining margins improving on lighter crude slate [src: news[0]]
- Jio + retail subscriber base provides predictable cashflow [src: fundamentals.revenue_ttm]
- Net debt has come down vs FY23 peak [src: fundamentals.debt_to_equity]

## Bear Case
- New-energy capex is binary and 5+ years to monetization [src: news[2]]
- Telecom ARPU growth slowing; Jio user adds decelerated [src: news[1]]
- Conglomerate discount likely persists with no demerger catalyst

## Conviction
Watch Long

## Confidence
0.55

## Assumptions
- Crude stays in $70-95 range
- No regulatory action on telecom tariff hikes
- Capex schedule holds within ±15% of stated plan

## What Would Change My Mind
- A 20%+ Jio ARPU step-up announcement (bullish)
- Promoter pledge increase >10% of holdings (bearish)
- Material delay (>12mo) on new-energy first-revenue date (bearish)
"""


def main() -> None:
    parsed = parse_analysis(SAMPLE_RESPONSE)
    out = {
        "ticker": "RELIANCE.NS",
        "raw_response": SAMPLE_RESPONSE,
        "parsed": parsed,
    }
    target = Path(__file__).parent / "analyst_baseline_RELIANCE.json"
    target.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
