"""Critic agent — adversarial review of Analyst output.

Sees: Analyst payload + compact source dossier (NOT the full context block).
Produces: {issues_md, missing_md, confidence_adj, verdict, raw_text}.

LLM provider injected via `get_provider` so tests can stub. Production wiring
in analyze_flow._build_default_registry resolves via router.for_agent('critic').
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from ..llm.base import LLMProvider, Message, ProviderError
from ..llm.budget import record
from .base import AgentContext, AgentResult

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "critic.md"

_SECTIONS = ("Issues", "Missing Data", "Confidence Adjustment", "Verdict")
_VALID_VERDICTS = {"ACCEPT", "REVISE", "REJECT"}


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def parse_critique(text: str) -> dict:
    """Parse Critic output into structured dict.

    Lenient: missing sections become empty strings. Confidence parses the first
    float and clamps to [0, 1]. Verdict matches ACCEPT/REVISE/REJECT as a
    case-insensitive substring; unparseable → None (tells the orchestrator to
    degrade).
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

    verdict: str | None = None
    raw_v = sections.get("Verdict", "").upper()
    for label in _VALID_VERDICTS:
        if label in raw_v:
            verdict = label
            break

    conf_adj: float | None = None
    raw_conf = sections.get("Confidence Adjustment", "")
    if raw_conf:
        m = re.search(r"-?\d+(?:\.\d+)?", raw_conf)
        if m:
            try:
                v = float(m.group(0))
                conf_adj = max(0.0, min(1.0, v))
            except ValueError:
                conf_adj = None

    return {
        "verdict": verdict,
        "issues_md": sections.get("Issues", ""),
        "missing_md": sections.get("Missing Data", ""),
        "confidence_adj": conf_adj,
        "raw_text": text,
    }


def _format_user_message(analyst_payload: dict, source_dossier: str) -> str:
    """Serialize the inputs the Critic needs into a single user message."""
    parts = [
        "ANALYST OUTPUT TO REVIEW",
        "========================",
        f"## Variant Perception\n{analyst_payload.get('variant_perception', '')}",
        f"## Bull Case\n{analyst_payload.get('bull_case', '')}",
        f"## Bear Case\n{analyst_payload.get('bear_case', '')}",
        f"## Conviction\n{analyst_payload.get('conviction', '')}",
        f"## Confidence\n{analyst_payload.get('confidence', '')}",
        f"## Assumptions\n{analyst_payload.get('assumptions', '')}",
        f"## What Would Change My Mind\n{analyst_payload.get('what_would_change', '')}",
        "",
        source_dossier,
    ]
    return "\n\n".join(parts)


class CriticAgent:
    name = "critic"
    is_llm = True

    def __init__(self, get_provider: Callable[[], LLMProvider]) -> None:
        self._get_provider = get_provider

    async def run(self, ctx: AgentContext) -> AgentResult:
        analyst = ctx.prior.get("analyst") or {}
        data = ctx.prior.get("data") or {}
        dossier = data.get("source_dossier", "")
        user_msg = _format_user_message(analyst, dossier)

        try:
            provider = self._get_provider()
            completion = await provider.complete(
                system=_load_prompt(),
                messages=[Message(role="user", content=user_msg)],
                max_tokens=500,
                temperature=0.2,
                cache_system=True,
            )
        except ProviderError as exc:
            return AgentResult(ok=False, error=str(exc))

        record("critic", completion)

        parsed = parse_critique(completion.text)
        if parsed["verdict"] is None:
            return AgentResult(
                ok=False,
                error=f"parse failed: no verdict in critic output ({len(completion.text)} chars)",
                model=completion.model,
                tokens_in=completion.tokens_in,
                tokens_out=completion.tokens_out,
                payload=parsed,
            )

        return AgentResult(
            ok=True,
            payload=parsed,
            model=completion.model,
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
        )
