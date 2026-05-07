"""Project-wide configuration flags loaded from environment variables."""
from __future__ import annotations

import os

OUTCOMES_LEDGER_ENABLED: bool = os.getenv("OUTCOMES_LEDGER_ENABLED", "0") == "1"
