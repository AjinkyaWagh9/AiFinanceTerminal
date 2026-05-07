"""Analyst agent — runs analyst.md to produce the 7-section structured analysis.

This module is the LLM-bearing successor to today's `agents/supervisor.py`.
The fetching + persistence side of that file moves to `agents/data.py` and
`agents/analyze_flow.py` respectively.

`parse_analysis` is preserved verbatim from supervisor.py to guarantee
non-regression against the captured baseline (tests/agents/fixtures/).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from ..llm.base import LLMProvider, Message, ProviderError
from ..llm.budget import record
from .base import AgentContext, AgentResult

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "analyst.md"

_SECTIONS = (
    "Variant Perception",
    "Bull Case",
    "Bear Case",
    "Conviction",
    "Confidence",
    "Assumptions",
    "What Would Change My Mind",
)

_VALID_CONVICTION = {
    "Conviction Long",
    "Watch Long",
    "Avoid",
    "Conviction Short",
    "Pair-Short",
}


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def parse_analysis(text: str) -> dict:
    """Splits the analyst's structured response into fields.

    Lenient: missing sections become empty strings; missing confidence becomes None.
    Confidence parses the first float in the section and clamps to [0, 1].
    Conviction matches the first valid label as a case-insensitive substring.

    NOTE: this is identical to the previous supervisor.parse_analysis; preserved
    so the non-regression baseline test is meaningful.
    """
    pattern = re.compile(
        r"^##\s+(" + "|".join(re.escape(s) for s in _SECTIONS) + r")\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(1)] = text[start:end].strip()

    confidence: float | None = None
    raw_conf = sections.get("Confidence", "")
    if raw_conf:
        m = re.search(r"-?\d+(?:\.\d+)?", raw_conf)
        if m:
            try:
                v = float(m.group(0))
                confidence = max(0.0, min(1.0, v))
            except ValueError:
                confidence = None

    conviction: str | None = None
    raw_conv = sections.get("Conviction", "").strip()
    if raw_conv:
        for label in _VALID_CONVICTION:
            if label.lower() in raw_conv.lower():
                conviction = label
                break

    return {
        "variant_perception": sections.get("Variant Perception", ""),
        "bull_case": sections.get("Bull Case", ""),
        "bear_case": sections.get("Bear Case", ""),
        "conviction": conviction,
        "confidence": confidence,
        "assumptions": sections.get("Assumptions", ""),
        "what_would_change": sections.get("What Would Change My Mind", ""),
    }


class AnalystAgent:
    name = "analyst"
    is_llm = True

    def __init__(self, get_provider: Callable[[], LLMProvider]) -> None:
        self._get_provider = get_provider

    async def run(self, ctx: AgentContext) -> AgentResult:
        data = ctx.prior.get("data") or {}
        context_block = data.get("context_block", "")
        user_msg = (
            context_block
            + "\n\nProduce the analysis per your output format. "
            "Every numeric claim must trace to a [src: ...] tag from the context above."
        )
        try:
            provider = self._get_provider()
            completion = await provider.complete(
                system=_load_prompt(),
                messages=[Message(role="user", content=user_msg)],
                max_tokens=2000,
                temperature=0.3,
                cache_system=True,
            )
        except ProviderError as exc:
            return AgentResult(ok=False, error=str(exc))

        record("analyst", completion)

        parsed = parse_analysis(completion.text)
        parsed["ticker"] = ctx.ticker

        return AgentResult(
            ok=True,
            payload=parsed,
            model=completion.model,
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
        )
