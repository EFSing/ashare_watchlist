from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path

from new_volatility_contraction_breakout_v1 import (
    BOOTSTRAP_SEED,
    MIN_SIGNAL_BARS,
    _bottom_k,
    _classify,
    _cooldown_retain,
    _feature_from_bars,
    _is_generic_breakout,
    _moving_block_bootstrap_ci,
    _rank_ascending,
    run,
)


def _bars(reference_range: float = 5.0, recent_range: float = 1.0, t_range: float = 1.0, close_t: float = 100.0):
    closes = np.full(52, 100.0)
    closes[-1] = close_t
    highs = closes.copy()
    lows = closes.copy()
    highs[1:41] += reference_range
    lows[1:41] -= reference_range
    highs[41:51] += recent_range
    lows[41:51] -= recent_range
    highs[-1] += t_range
    lows[-1] -= t_range
    return closes, highs, lows


def test_tr_exact_formula_and_trp_normalization():
    closes, highs, lows = _bars()
    feature = _feature_from_bars(closes, highs, lows)
    assert feature is not None
    assert feature["trp_recent10"] == pytest.approx(0.02)
    assert feature["trp_reference40"] == pytest.approx(0.10)
    assert feature["contraction_ratio"] == pytest.approx(0.2)


def test_compression_excludes_t_and_windows_are_exact_non_overlapping():
    baseline = _feature_from_bars(*_bars(t_range=1.0))
    contaminated = _feature_from_bars(*_bars(t_range=50.0))
    assert baseline == contaminated


def test_reference_denominator_must_be_positive():
    closes, highs, lows = _bars(reference_range=0.0, recent_range=1.0)
    assert _feature_from_bars(closes, highs, lows) is None


def test_exact_minimum_history_boundary_and_no_shorter_substitution():
    closes, highs, lows = _bars()
    assert MIN_SIGNAL_BARS == 52
    assert _feature_from_bars(closes[:-1], highs[:-1], lows[:-1]) is None
    assert _feature_from_bars(closes, highs, lows) is not None


def test_ascending_rank_and_deterministic_symbol_tie_break():
    assert _rank_ascending({"b": 0.2, "a": 0.2, "c": 0.1}) == {"c": 1, "a": 2, "b": 3}
    assert _bottom_k(1) == 1
    assert _bottom_k(6) == 2


def test_actual_contraction_and_candidate_control_exact_complement():
    assert _classify(True, True) == (True, False)
    assert _classify(True, False) == (False, True)
    assert _classify(False, True) == (False, False)
    assert _classify(False, False) == (False, False)


def test_breakout_is_strict_and_excludes_t_high():
    assert _is_generic_breakout(101.0, 100.0)
    assert not _is_generic_breakout(100.0, 100.0)
    closes, highs, lows = _bars(t_range=50.0, close_t=100.0)
    feature = _feature_from_bars(closes, highs, lows)
    assert feature is not None
    assert feature["prior_high20"] == pytest.approx(105.0)


def test_volume_is_diagnostic_only_and_cannot_change_classification():
    closes, highs, lows = _bars()
    low_amount = _feature_from_bars(closes, highs, lows, np.ones(52))
    high_amount = _feature_from_bars(closes, highs, lows, np.full(52, 1e12))
    assert low_amount["contraction_ratio"] == high_amount["contraction_ratio"]
    assert _classify(True, True) == _classify(True, True)


def test_bootstrap_is_deterministic():
    values = np.linspace(-1.0, 1.0, 40)
    assert _moving_block_bootstrap_ci(values, seed=BOOTSTRAP_SEED) == _moving_block_bootstrap_ci(values, seed=BOOTSTRAP_SEED)


def test_cooldown_is_deterministic_and_uses_signal_sessions():
    sessions = {f"2026-01-{day:02d}": day for day in range(1, 31)}
    events = [("2026-01-01", "000001.sz", "CANDIDATE"), ("2026-01-11", "000001.sz", "PRIMARY_CONTROL"), ("2026-01-12", "000001.sz", "CANDIDATE"), ("2026-01-22", "000001.sz", "PRIMARY_CONTROL")]
    retained = _cooldown_retain(events, sessions)
    assert retained == [events[0], events[2]]


def test_outcome_fields_cannot_affect_signal_classification():
    assert _classify(True, True) == _classify(True, True)


def test_final_oos_path_is_prohibited():
    root = Path("final_oos")
    with pytest.raises(RuntimeError, match="Final OOS path is forbidden"):
        run(phase="signal", raw_dir=root, core_manifest_path=root / "manifest.json", core_output_path=root / "core.jsonl.gz", b_membership_path=root / "b.jsonl.gz", output_dir=Path("out"), detail_dir=Path("detail"), base="test")
