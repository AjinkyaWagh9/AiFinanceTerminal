import pytest
from finterminal.features.zscore import rolling_zscore

def test_below_min_obs_returns_none_and_missing():
    z, missing = rolling_zscore(0.5, [0.1, 0.2, 0.3], min_obs=30)
    assert z is None and missing is True

def test_zero_variance_returns_none_and_missing():
    z, missing = rolling_zscore(0.5, [0.5] * 30, min_obs=30)
    assert z is None and missing is True

def test_happy_path():
    history = [float(i) for i in range(30)]   # mean=14.5, std≈8.803
    z, missing = rolling_zscore(20.0, history, min_obs=30)
    assert missing is False
    assert z == pytest.approx((20.0 - 14.5) / 8.803, rel=1e-3)

def test_value_excluded_from_history():
    # Caller is responsible for not passing the value being z'd.
    # Helper trusts history; no self-inclusion check here.
    history = [1.0] * 50
    z, missing = rolling_zscore(2.0, history, min_obs=30)
    assert missing is True   # zero variance
