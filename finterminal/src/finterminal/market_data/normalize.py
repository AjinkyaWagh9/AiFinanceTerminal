from __future__ import annotations
import logging
from typing import Iterable, Sequence

from finterminal.data.india.nse_universe import load_equity_list

log = logging.getLogger(__name__)

def normalize_symbol(raw: str) -> str:
    return raw.strip().upper()

def apply(rows: Sequence[dict]) -> list[dict]:
    universe = load_equity_list()
    known = {sym.upper() for sym in universe.keys()}
    out: list[dict] = []
    for row in rows:
        sym = normalize_symbol(row["ticker"])
        if sym not in known and not sym.startswith("_"):
            log.warning("unmapped NSE symbol %s — passing through", sym)
        out.append({**row, "ticker": sym})
    return out
