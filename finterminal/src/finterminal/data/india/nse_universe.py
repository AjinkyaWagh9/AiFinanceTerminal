"""NSE equity universe loader.

Loads EQUITY_L.csv (bundled snapshot) to build:
- ticker alias map: ticker → {name, aliases}
- sector map: ticker → sector bucket (from sector_map.yaml)

Both are loaded once at import time and cached as module-level dicts.
"""
from __future__ import annotations

import csv
import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SECTOR_MAP_PATH = Path(__file__).parent / "sector_map.yaml"

_STRIP_SUFFIXES = re.compile(
    r"\b(limited|ltd\.?|corporation|corp\.?)\b",
    re.IGNORECASE,
)


def _generate_aliases(full_name: str) -> list[str]:
    """Generate alias variants from a company's full legal name."""
    aliases = [full_name]
    # Strip common corporate suffixes
    stripped = _STRIP_SUFFIXES.sub("", full_name).strip(" ,-")
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped and stripped.lower() != full_name.lower():
        aliases.append(stripped)
    # Acronym from capital letters (e.g. "HCL Technologies" → "HCL")
    caps = "".join(c for c in full_name if c.isupper())
    if len(caps) >= 2 and caps not in aliases:
        aliases.append(caps)
    return [a for a in aliases if a]


@lru_cache(maxsize=1)
def load_equity_list(path: str | None = None) -> dict[str, dict]:
    """Return {ticker: {"name": str, "aliases": list[str]}}.

    Reads bundled fixture at data/india/fixtures/EQUITY_L.csv.
    Pass a custom path (str) to override (used in tests).
    """
    csv_path = Path(path) if path else _FIXTURES_DIR / "EQUITY_L.csv"
    universe: dict[str, dict] = {}
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get("SYMBOL", "").strip().upper()
                name = row.get("NAME OF COMPANY", "").strip()
                if not ticker or not name:
                    continue
                universe[ticker] = {
                    "name": name,
                    "aliases": _generate_aliases(name),
                }
    except FileNotFoundError:
        logger.error("EQUITY_L.csv not found at %s", csv_path)
    return universe


@lru_cache(maxsize=1)
def load_sector_map(path: str | None = None) -> dict[str, str]:
    """Return {ticker: sector_bucket}. Reads sector_map.yaml."""
    yaml_path = Path(path) if path else _SECTOR_MAP_PATH
    try:
        with yaml_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return {k: v for k, v in raw.items() if isinstance(v, str)}
    except FileNotFoundError:
        logger.error("sector_map.yaml not found at %s", yaml_path)
        return {}
