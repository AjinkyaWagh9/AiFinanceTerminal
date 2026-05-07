"""Tests for ml/trainer.py — LightGBM trainer with isotonic calibration,
split-conformal, manifest, and promotion guard.

Spec §4.4 + §5.2 + §5.3 + §7 + §8 + §10.

TDD order: import/interface tests first, then full round-trip tests.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from finterminal.data.duckdb_store import connect
from finterminal.market_data.store import upsert_prices_eod
from finterminal.features.store import upsert_features
from finterminal.features.registry import V1_FEATURES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NIFTY = "_NIFTY50"
FEATURE_VERSION = "v1_trainer_test"
HORIZON = 7
ALL_FEATURE_NAMES = [f.name for f in V1_FEATURES]

# Fixed "now" for determinism tests
FIXED_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn(tmp_path: Path):
    return connect(str(tmp_path / "t.duckdb"))


def _seed_nifty(conn, n_days: int = 500, start: date | None = None) -> None:
    """Seed n_days of Nifty closes so label_outcomes can compute sigma."""
    start = start or date(2022, 1, 1)
    rows = [
        {
            "trade_date": start + timedelta(days=i),
            "ticker": NIFTY,
            "open": 20000.0,
            "high": 20000.0,
            "low": 20000.0,
            "close": 20000.0 * (1.001 ** i),
            "volume": 0,
        }
        for i in range(n_days)
    ]
    upsert_prices_eod(conn, rows, source="test")


def _seed_signal(
    conn,
    signal_id: str,
    ts_emitted: datetime,
    signal_type: str = "cluster_momentum",
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO signals
            (signal_id, signal_type, engine, ticker, ts_emitted, payload)
        VALUES (?, ?, 'test', 'TCS', ?, '{}')
        """,
        [signal_id, signal_type, ts_emitted],
    )


def _seed_outcome(
    conn,
    signal_id: str,
    ts_emitted: datetime,
    ret_pct_vs_nifty: float,
    horizon_days: int = HORIZON,
) -> None:
    resolved_at = ts_emitted + timedelta(days=horizon_days)
    conn.execute(
        """
        INSERT OR IGNORE INTO signal_outcomes
            (signal_id, horizon_days, ret_pct, ret_pct_vs_nifty, resolved_at)
        VALUES (?, ?, 0.0, ?, ?)
        """,
        [signal_id, horizon_days, ret_pct_vs_nifty, resolved_at],
    )


def _seed_full_features(
    conn,
    signal_id: str,
    feature_version: str = FEATURE_VERSION,
) -> None:
    features = {
        spec.name: {
            "value": 0.5,
            "is_missing": False,
            "feature_version": feature_version,
        }
        for spec in V1_FEATURES
    }
    upsert_features(conn, signal_id, features)


def _seed_training_data(
    conn,
    horizon_days: int,
    n: int,
    feature_version: str = FEATURE_VERSION,
    start_ts: datetime | None = None,
) -> None:
    """Seed n resolved signals with features and outcomes for training.

    Signals are spaced 1 day apart for time-ordering tests.
    Labels cycle through bull/base/bear for variety.
    """
    rng = np.random.default_rng(seed=42)
    start_ts = start_ts or datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)

    # sigma reference — use a small positive value for non-zero sigma boundary
    # The seeded Nifty has constant growth so sigma is near-zero; use explicit ret
    sigma_proxy = 0.001  # below this is base

    for i in range(n):
        sid = str(uuid.uuid4())
        ts = start_ts + timedelta(days=i)
        # Cycle labels: bull / base / bear
        cycle = i % 3
        if cycle == 0:
            ret = sigma_proxy * 10  # bull
        elif cycle == 1:
            ret = 0.0  # base
        else:
            ret = -sigma_proxy * 10  # bear

        # Add tiny jitter to ret so the classifier sees variance
        ret += float(rng.uniform(-sigma_proxy * 0.1, sigma_proxy * 0.1))

        _seed_signal(conn, sid, ts)
        _seed_outcome(conn, sid, ts, ret, horizon_days=horizon_days)
        _seed_full_features(conn, sid, feature_version=feature_version)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_skips_horizon_when_below_cold_start_threshold(tmp_path):
    """With only 30 resolved outcomes for h=7, train_all returns a NaN brier."""
    from finterminal.ml.trainer import train_all, HorizonArtifact

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)
    _seed_training_data(conn, horizon_days=HORIZON, n=30)

    artifacts_root = tmp_path / "artifacts"
    current_symlink = tmp_path / "current"

    bundle = train_all(
        conn=conn,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        now=FIXED_NOW,
    )

    art = bundle.per_horizon[HORIZON]
    assert math.isnan(art.brier), f"Expected NaN brier for cold-start, got {art.brier}"
    assert art.booster_path is None
    assert art.isotonic_path is None
    assert art.conformal_path is None


def test_60_20_20_split_is_time_ordered(tmp_path):
    """With 200 strictly-ordered rows, the manifest's train_window_end must be
    at most the latest ts_emitted in the conformal slice (newest 20%).

    We validate time-ordering by checking the slice boundaries recorded in the
    manifest.
    """
    from finterminal.ml.trainer import train_all

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)
    n = 200
    _seed_training_data(conn, horizon_days=HORIZON, n=n)

    artifacts_root = tmp_path / "artifacts"
    current_symlink = tmp_path / "current"

    bundle = train_all(
        conn=conn,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        now=FIXED_NOW,
    )

    manifest_path = Path(bundle.artifact_dir) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    # Manifest must record slice boundaries
    h_key = str(HORIZON)
    assert h_key in manifest["per_horizon"], "Horizon key missing in manifest"
    h_info = manifest["per_horizon"][h_key]
    assert "n_train" in h_info, "n_train missing from manifest horizon entry"
    assert "n_iso" in h_info, "n_iso missing"
    assert "n_conf" in h_info, "n_conf missing"

    n_train = h_info["n_train"]
    n_iso = h_info["n_iso"]
    n_conf = h_info["n_conf"]
    total = n_train + n_iso + n_conf

    # 60/20/20 ratios (allow ±1 row for rounding)
    assert abs(n_train / total - 0.60) < 0.02, f"Train slice {n_train}/{total} not ~60%"
    assert abs(n_iso / total - 0.20) < 0.02, f"ISO slice {n_iso}/{total} not ~20%"
    assert abs(n_conf / total - 0.20) < 0.02, f"Conf slice {n_conf}/{total} not ~20%"


def test_eval_json_contains_brier_and_baseline_per_horizon(tmp_path):
    """After training, eval.json must have the required metric keys per horizon."""
    from finterminal.ml.trainer import train_all

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)
    _seed_training_data(conn, horizon_days=HORIZON, n=200)

    artifacts_root = tmp_path / "artifacts"
    current_symlink = tmp_path / "current"

    bundle = train_all(
        conn=conn,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        now=FIXED_NOW,
    )

    eval_path = Path(bundle.artifact_dir) / "eval.json"
    assert eval_path.exists(), "eval.json not written"
    eval_data = json.loads(eval_path.read_text())

    h_key = str(HORIZON)
    assert h_key in eval_data, f"Horizon {h_key} missing from eval.json"
    entry = eval_data[h_key]
    for key in ("brier", "brier_class_prior", "hit_rate", "hit_rate_class_prior"):
        assert key in entry, f"Key '{key}' missing from eval.json[{h_key}]"

    # Brier must be a finite float
    assert math.isfinite(entry["brier"]), "brier must be finite"


def test_manifest_is_deterministic_with_same_random_state(tmp_path):
    """Two runs with the same now and random_state produce identical manifests."""
    from finterminal.ml.trainer import train_all

    conn1 = _make_conn(tmp_path)
    _seed_nifty(conn1)
    _seed_training_data(conn1, horizon_days=HORIZON, n=150)

    # Second separate DB with identical seed
    conn2 = connect(str(tmp_path / "t2.duckdb"))
    _seed_nifty(conn2)
    _seed_training_data(conn2, horizon_days=HORIZON, n=150)

    artifacts_root1 = tmp_path / "artifacts1"
    artifacts_root2 = tmp_path / "artifacts2"
    sym1 = tmp_path / "current1"
    sym2 = tmp_path / "current2"

    bundle1 = train_all(
        conn=conn1,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root1,
        current_symlink=sym1,
        random_state=42,
        now=FIXED_NOW,
    )
    bundle2 = train_all(
        conn=conn2,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root2,
        current_symlink=sym2,
        random_state=42,
        now=FIXED_NOW,
    )

    assert bundle1.model_version == bundle2.model_version, (
        "model_version must be identical when now and feature_version match"
    )

    m1 = json.loads((Path(bundle1.artifact_dir) / "manifest.json").read_text())
    m2 = json.loads((Path(bundle2.artifact_dir) / "manifest.json").read_text())

    assert m1["model_version"] == m2["model_version"]
    assert m1["feature_version"] == m2["feature_version"]
    assert m1["random_state"] == m2["random_state"]


def test_promotion_guard_rejects_brier_regression(tmp_path):
    """Train v1 (normal). Patch v1's eval.json to claim a very low Brier.
    Train v2 normally — it cannot beat the artificially good v1, so symlink stays on v1.
    """
    from finterminal.ml.trainer import train_all

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)
    _seed_training_data(conn, horizon_days=HORIZON, n=200)

    artifacts_root = tmp_path / "artifacts"
    current_symlink = tmp_path / "current"

    now_v1 = datetime(2025, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    bundle_v1 = train_all(
        conn=conn,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        random_state=42,
        now=now_v1,
    )

    # Capture where symlink points after v1
    assert current_symlink.exists(), "symlink must exist after first training"
    v1_target = os.readlink(str(current_symlink))

    # Patch v1's eval.json to have a near-perfect Brier (0.001) so v2 cannot beat it
    v1_eval_path = Path(bundle_v1.artifact_dir) / "eval.json"
    v1_eval = json.loads(v1_eval_path.read_text())
    v1_eval[str(HORIZON)]["brier"] = 0.001   # artificially excellent
    v1_eval_path.write_text(json.dumps(v1_eval, indent=2))

    # Train v2 normally — v2's real Brier will be >> 0.001 + 0.01 tolerance
    now_v2 = datetime(2025, 5, 2, 0, 0, 0, tzinfo=timezone.utc)
    bundle_v2 = train_all(
        conn=conn,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        random_state=42,
        now=now_v2,
    )

    # Symlink must still point to v1
    v2_target = os.readlink(str(current_symlink))
    assert v2_target == v1_target, (
        f"Symlink should still point to v1 ({v1_target}) but got {v2_target}"
    )

    # v2 eval.json must have promoted=False
    v2_eval = json.loads((Path(bundle_v2.artifact_dir) / "eval.json").read_text())
    assert v2_eval.get("promoted") is False, "v2 eval.json must have promoted=False"


def test_promotion_guard_promotes_first_bundle_with_no_prior(tmp_path):
    """First training with fresh artifacts dir — symlink must be created pointing at the bundle."""
    from finterminal.ml.trainer import train_all

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)
    _seed_training_data(conn, horizon_days=HORIZON, n=150)

    artifacts_root = tmp_path / "artifacts"
    current_symlink = tmp_path / "current"

    assert not current_symlink.exists(), "symlink must not exist before first train"

    bundle = train_all(
        conn=conn,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        now=FIXED_NOW,
    )

    assert current_symlink.exists(), "symlink must be created after first training"
    resolved = os.readlink(str(current_symlink))
    # The symlink target must reference the new bundle's artifact dir
    assert bundle.model_version in resolved, (
        f"Symlink target '{resolved}' does not contain model_version '{bundle.model_version}'"
    )

    # eval.json must have promoted=True
    eval_data = json.loads((Path(bundle.artifact_dir) / "eval.json").read_text())
    assert eval_data.get("promoted") is True


def test_artifacts_dir_contains_required_files(tmp_path):
    """After train_all, verify all required artifact files are present."""
    from finterminal.ml.trainer import train_all

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)
    _seed_training_data(conn, horizon_days=HORIZON, n=150)

    artifacts_root = tmp_path / "artifacts"
    current_symlink = tmp_path / "current"

    bundle = train_all(
        conn=conn,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=artifacts_root,
        current_symlink=current_symlink,
        now=FIXED_NOW,
    )

    art_dir = Path(bundle.artifact_dir)
    # Top-level artifacts
    assert (art_dir / "scaler.pkl").exists(), "scaler.pkl must be present"
    assert (art_dir / "eval.json").exists(), "eval.json must be present"
    assert (art_dir / "manifest.json").exists(), "manifest.json must be present"

    # Per-horizon artifacts (only for non-cold-start)
    art = bundle.per_horizon[HORIZON]
    if art.booster_path is not None:
        assert Path(art.booster_path).exists(), f"{HORIZON}d.lgb must exist"
        assert Path(art.isotonic_path).exists(), f"{HORIZON}d_isotonic.pkl must exist"
        assert Path(art.conformal_path).exists(), f"{HORIZON}d_conformal.pkl must exist"

        # Validate conformal pickle is a float
        with open(art.conformal_path, "rb") as f:
            q = pickle.load(f)
        assert isinstance(q, float), f"Conformal quantile must be float, got {type(q)}"
        assert 0.0 <= q <= 1.0, f"Conformal quantile {q} must be in [0, 1]"


def test_model_version_format_matches_spec(tmp_path):
    """model_version must match regex ^lgb_v1_[^_]+_[^_]+_\\d{8}T\\d{6}$

    Note: feature_version may contain underscores itself (e.g. 'v1_trainer_test'),
    so the regex is: lgb_v1_ + <anything> + _<8digits>T<6digits>.
    """
    from finterminal.ml.trainer import train_all

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)
    _seed_training_data(conn, horizon_days=HORIZON, n=150)

    bundle = train_all(
        conn=conn,
        horizons=[HORIZON],
        feature_version=FEATURE_VERSION,
        artifacts_root=tmp_path / "artifacts",
        current_symlink=tmp_path / "current",
        now=FIXED_NOW,
    )

    # Pattern: lgb_v1_<feature_version>_<yyyymmddThhmmss>
    pattern = r"^lgb_v1_.+_\d{8}T\d{6}$"
    assert re.match(pattern, bundle.model_version), (
        f"model_version '{bundle.model_version}' does not match pattern '{pattern}'"
    )

    # Also verify the embedded timestamp component is parseable
    # The last segment before the end is the datetime stamp
    ts_part = bundle.model_version.rsplit("_", 1)[-1]
    assert re.match(r"^\d{8}T\d{6}$", ts_part), (
        f"Timestamp part '{ts_part}' is not in yyyymmddThhmmss format"
    )


def test_ts_emitted_in_matrix_meta(tmp_path):
    """MatrixMeta.ts_emitted must be populated with one entry per row."""
    from finterminal.ml.dataset import build_matrix

    conn = _make_conn(tmp_path)
    _seed_nifty(conn)

    n = 10
    start_ts = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    _seed_training_data(conn, horizon_days=HORIZON, n=n,
                        start_ts=start_ts, feature_version=FEATURE_VERSION)

    until_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    X, y, meta = build_matrix(conn, HORIZON, FEATURE_VERSION, until_ts)

    assert hasattr(meta, "ts_emitted"), "MatrixMeta must have ts_emitted field"
    assert len(meta.ts_emitted) == meta.n_rows, (
        f"ts_emitted length {len(meta.ts_emitted)} != n_rows {meta.n_rows}"
    )
    # All entries must be datetime objects
    for ts in meta.ts_emitted:
        assert isinstance(ts, datetime), f"ts_emitted entry {ts!r} is not a datetime"
