# src/finterminal/outcomes/engines/base.py
"""Engine class hook. Empty placeholder — per-engine modules
(mispricing.py, quality.py, ...) are added when >=2 signal types per engine ship.
This file exists so the import path is stable from day 1."""
from __future__ import annotations


class EngineBase:
    """Marker base class. Concrete engines override `signals_for_card(ticker)` later."""
    name: str = ""
