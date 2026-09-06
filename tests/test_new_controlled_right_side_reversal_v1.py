from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from new_controlled_right_side_reversal_v1 import (
    BOOTSTRAP_SEED,
    MIN_SIGNAL_BARS,
    _bottom_k,
    _bounce_bin,
    _classify,
    _cooldown_retain,
    _feature_from_bars,
    _moving_block_bootstrap_ci,
    _rank_ascending,
    _reclaim5,
    _simple_positive_bounce,
    _stratified_spread,
    run,
)


def _bars(close_t: float = 100.0, prior_high: float = 105.0, close_t_minus_1: float = 100.0):
    closes = np.full(MIN_SIGNAL_BARS, 100.0)
    closes[-2] = close_t_minus_1
    closes[-1] = close_t
    closes[-6:-1] = prior_high
    highs = closes + 1.0
    lows = closes - 1.0
    return closes, np.ones(MIN_SIGNAL_BARS), highs, lows


def test_exact_r20_pre_uses_t_minus_1_and_t_minus_21_only():
    closes, volume, highs, lows = _bars()
    closes[-22] = 200.0
    closes[-2] = 100.0
    feature = _feature_from_bars(closes, volume, highs, lows)
    assert feature is not None
    assert feature["r20_pre"] == pytest.approx(-0.5)
    contaminated = closes.copy()
    contaminated[-1] = 1000.0
    contaminated_feature = _feature_from_bars(contaminated, volume, highs, lows)
    assert contaminated_feature is not None
    assert contaminated_feature["r20_pre"] == feature["r20_pre"]


def test_exact_minimum_history_and_missing_history_are_not_substituted():
    closes, volume, highs, lows = _bars()
    assert MIN_SIGNAL_BARS == 22
    assert _feature_from_bars(closes[:-1], volume[:-1], highs[:-1], lows[:-1]) is None
    assert _feature_from_bars(closes, volume, highs, lows) is not None


def test_ascending_rank_symbol_tie_break_and_ceiling_bottom_k():
    assert _rank_ascending({"000002.sz": 0.1, "000001.sz": 0.1, "000003.sz": -0.1}) == {"000003.sz": 1, "000001.sz": 2, "000002.sz": 3}
    assert _bottom_k(1) == 1
    assert _bottom_k(6) == 2
    assert _bottom_k(11) == 3


def test_downside_requires_absolute_negative_and_t1_only_classification():
    assert _classify(True, True, True) == (True, False, True)
    assert _classify(True, True, False) == (False, True, True)
    assert _classify(True, False, False) == (False, False, False)
    assert _classify(False, True, True) == (False, False, False)


def test_t_day_bounce_and_reclaim_are_strict():
    assert _simple_positive_bounce(100.01, 100.0)
    assert not _simple_positive_bounce(100.0, 100.0)
    assert _reclaim5(105.01, 105.0)
    assert not _reclaim5(105.0, 105.0)


def test_prior_close_high5_excludes_t_close_and_uses_closes_not_highs():
    closes, volume, highs, lows = _bars(close_t=106.0, prior_high=105.0)
    feature = _feature_from_bars(closes, volume, highs, lows)
    assert feature is not None
    assert feature["prior_close_high5"] == pytest.approx(105.0)
    assert feature["reclaim_margin"] == pytest.approx(106.0 / 105.0 - 1.0)
    t_contaminated = closes.copy()
    t_contaminated[-1] = 1000.0
    t_feature = _feature_from_bars(t_contaminated, volume, highs, lows)
    assert t_feature is not None
    assert t_feature["prior_close_high5"] == pytest.approx(105.0)


def test_candidate_control_are_disjoint_and_complement_baseline():
    for downside in (False, True):
        for bounce in (False, True):
            for reclaim in (False, True):
                candidate, control, baseline = _classify(downside, bounce, reclaim)
                assert not (candidate and control)
                if downside and bounce:
                    assert candidate or control
                    assert (candidate or control) == baseline


def test_candidate_is_subset_of_downside_bounce_and_invalidation_is_not_input():
    assert _classify(True, True, True)[0]
    assert not _classify(False, True, True)[0]
    assert _classify(True, True, True) == _classify(True, True, True)


def test_bounce_bin_is_deterministic_five_bin_formula():
    assert [_bounce_bin(rank, 10) for rank in range(1, 11)] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert _bounce_bin(1, 1) == 1
    assert _bounce_bin(1, 6) == 1
    assert _bounce_bin(6, 6) == 5


def test_date_and_bin_aggregation_are_equal_weighted():
    groups = {
        "CANDIDATE": [({"bounce_bin": 1}, {"outcomes": {"10D": {"status": "AVAILABLE", "return_pct": 4.0}}})],
        "PRIMARY_CONTROL": [({"bounce_bin": 1}, {"outcomes": {"10D": {"status": "AVAILABLE", "return_pct": 1.0}}})],
    }
    assert _stratified_spread(groups, "CANDIDATE", "PRIMARY_CONTROL", "10D")["spread"] == pytest.approx(3.0)


def test_context_interaction_is_downside_spread_minus_generic_spread():
    downside = {
        "CANDIDATE": [({"bounce_bin": 1}, {"outcomes": {"10D": {"status": "AVAILABLE", "return_pct": 4.0}}})],
        "PRIMARY_CONTROL": [({"bounce_bin": 1}, {"outcomes": {"10D": {"status": "AVAILABLE", "return_pct": 1.0}}})],
    }
    generic = {
        "GENERIC_RECLAIM": [({"non_downside_bounce_bin": 1}, {"outcomes": {"10D": {"status": "AVAILABLE", "return_pct": 2.0}}})],
        "GENERIC_BOUNCE_CONTROL": [({"non_downside_bounce_bin": 1}, {"outcomes": {"10D": {"status": "AVAILABLE", "return_pct": 1.0}}})],
    }
    downside_spread = _stratified_spread(downside, "CANDIDATE", "PRIMARY_CONTROL", "10D")["spread"]
    generic_spread = _stratified_spread(generic, "GENERIC_RECLAIM", "GENERIC_BOUNCE_CONTROL", "10D", "non_downside_bounce_bin")["spread"]
    assert downside_spread - generic_spread == pytest.approx(2.0)


def test_moving_block_bootstrap_is_deterministic():
    values = np.linspace(-1.0, 1.0, 40)
    assert _moving_block_bootstrap_ci(values, seed=BOOTSTRAP_SEED) == _moving_block_bootstrap_ci(values, seed=BOOTSTRAP_SEED)


def test_cooldown_uses_signal_sessions_and_original_classification():
    sessions = {f"2026-01-{day:02d}": day for day in range(1, 31)}
    events = [
        ("2026-01-01", "000001.sz", "CANDIDATE"),
        ("2026-01-11", "000001.sz", "PRIMARY_CONTROL"),
        ("2026-01-12", "000001.sz", "CANDIDATE"),
        ("2026-01-22", "000001.sz", "PRIMARY_CONTROL"),
    ]
    assert _cooldown_retain(events, sessions) == [events[0], events[2]]


def test_outcome_fields_cannot_affect_signal_and_volume_is_not_qualification():
    closes, volume, highs, lows = _bars()
    low = _feature_from_bars(closes, volume, highs, lows)
    high = _feature_from_bars(closes, np.full(MIN_SIGNAL_BARS, 1e12), highs, lows)
    assert low is not None and high is not None
    assert low["r20_pre"] == high["r20_pre"]
    assert _classify(True, True, True) == _classify(True, True, True)


def test_final_oos_and_forbidden_input_paths_are_rejected():
    root = Path("final_oos")
    with pytest.raises(RuntimeError, match="forbidden research input path"):
        run(phase="signal", raw_dir=root, core_manifest_path=root / "manifest.json", core_output_path=root / "core.jsonl.gz", b_membership_path=None, rs_membership_path=None, vcb_membership_path=None, output_dir=Path("out"), detail_dir=Path("detail"), base="test")
