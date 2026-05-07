from __future__ import annotations
import statistics

def rolling_zscore(value: float, history: list[float], *,
                   min_obs: int = 30) -> tuple[float | None, bool]:
    """Compute z-score of `value` against `history`. History MUST exclude
    the value being z'd (caller's responsibility — see spec D5).

    Returns (z, is_missing). is_missing=True when:
      - len(history) < min_obs, OR
      - stdev(history) == 0 (degenerate distribution)
    """
    if len(history) < min_obs:
        return None, True
    sd = statistics.stdev(history)
    if sd == 0.0:
        return None, True
    mu = statistics.mean(history)
    return (value - mu) / sd, False
