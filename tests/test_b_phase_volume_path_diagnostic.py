from __future__ import annotations

import math
import warnings

import numpy as np

from b_breakout_retest import _b_match
from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256
from b_phase_volume_path_diagnostic import _breakout_mask, _first_breakout_trace, _safe_ratio


EXPECTED_SPEC_SHA = "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd"


def _fixture(*, breakout_index: int = 62, signal_volume: float = 80.0):
    close = np.full(70, 10.0)
    high = np.full(70, 10.2)
    low = np.full(70, 9.8)
    volume = np.full(70, 100.0)
    close[breakout_index] = 10.5
    high[breakout_index] = 10.6
    volume[breakout_index] = 200.0
    close[breakout_index + 1 :] = 10.1
    high[breakout_index + 1 :] = 10.3
    low[breakout_index + 1 :] = 9.9
    volume[breakout_index + 1 : -1] = 60.0
    volume[-1] = signal_volume
    dates = [f"d{index:03d}" for index in range(70)]
    return close, volume, high, low, dates


def test_exact_first_breakout_and_unconditional_break_parity():
    close, volume, high, low, dates = _fixture(signal_volume=180.0)
    volume[63:69] = 160.0
    close[65] = 10.8
    volume[65] = 250.0
    trace = _first_breakout_trace(close, volume, high, low, dates)
    assert trace is not None
    assert trace["breakout_index"] == 62
    assert trace["pullback_stage"] == "PULLBACK_VOLUME_FAIL_ONLY"
    base_hi, _matched, failed = _b_match(close, volume, float(np.mean(close[-5:])))
    assert base_hi is None
    assert "PULLBACK_VOLUME_LT_70_PCT_BREAKOUT" in failed


def test_volume_ratios_decompose_existing_b_without_rewriting_it():
    close, volume, high, low, dates = _fixture(signal_volume=80.0)
    trace = _first_breakout_trace(close, volume, high, low, dates)
    assert trace is not None
    assert trace["breakout_volume_ratio"] == 2.0
    assert trace["b_existing_pull_volume_ratio"] == np.mean(volume[63:70]) / 200.0
    assert trace["pre_t_retest_volume_ratio"] == np.mean(volume[63:69]) / 200.0
    assert trace["reactivation_vs_retest_ratio"] == 80.0 / np.mean(volume[63:69])
    assert trace["reactivation_vs_breakout_ratio"] == 80.0 / 200.0
    base_hi, _matched, failed = _b_match(close, volume, float(np.mean(close[-5:])))
    assert base_hi == 10.0
    assert not failed


def test_pre_t_interval_excludes_signal_t_and_reactivation_is_signal_t_only():
    first = _first_breakout_trace(*_fixture(signal_volume=80.0)[:4])
    second = _first_breakout_trace(*_fixture(signal_volume=160.0)[:4])
    assert first is not None and second is not None
    assert first["pre_t_retest_volume_ratio"] == second["pre_t_retest_volume_ratio"]
    assert second["reactivation_vs_retest_ratio"] == 2 * first["reactivation_vs_retest_ratio"]


def test_t_minus_one_breakout_has_no_pre_t_retest_interval():
    close, volume, high, low, dates = _fixture(breakout_index=68, signal_volume=80.0)
    trace = _first_breakout_trace(close, volume, high, low, dates)
    assert trace is not None
    assert trace["breakout_index"] == 68
    assert trace["pre_t_retest_volume_ratio"] is None
    assert trace["reactivation_vs_retest_ratio"] is None
    assert trace["feature_unavailable"]["pre_t_retest_volume_ratio"] == "NO_PRE_T_RETEST_INTERVAL"
    assert trace["feature_unavailable"]["reactivation_vs_retest_ratio"] == "NO_PRE_T_RETEST_INTERVAL"


def test_zero_denominator_is_unavailable_not_infinite():
    value, reason = _safe_ratio(1.0, 0.0)
    assert value is None
    assert reason == "ZERO_DENOMINATOR"
    value, reason = _safe_ratio(math.inf, 1.0)
    assert value is None
    assert reason == "NON_FINITE_DENOMINATOR_OR_NUMERATOR"


def test_trace_is_deterministic_and_uses_only_passed_t_window():
    close, volume, high, low, dates = _fixture(signal_volume=80.0)
    first = _first_breakout_trace(close.copy(), volume.copy(), high.copy(), low.copy(), list(dates))
    second = _first_breakout_trace(close.copy(), volume.copy(), high.copy(), low.copy(), list(dates))
    assert first == second
    assert first["breakout_date"] == dates[62]
    assert first["signal_day_return_pct"] == (close[-1] / close[-2] - 1.0) * 100.0


def test_research_module_does_not_change_corrected_b_spec_identity():
    assert STRATEGY_SPEC_SHA256 == EXPECTED_SPEC_SHA


def test_vectorized_breakout_prefilter_matches_exact_trace():
    close, volume, high, low, dates = _fixture(signal_volume=80.0)
    mask = _breakout_mask(close, volume)
    assert np.flatnonzero(mask[61:69]).tolist() == [1]
    trace = _first_breakout_trace(close, volume, high, low, dates)
    assert trace is not None
    assert trace["breakout_index"] == int(np.flatnonzero(mask[61:69])[0] + 61)


def test_vectorized_breakout_prefilter_preserves_zero_predecessor_behavior_without_warning():
    close, volume, _high, _low, _dates = _fixture(signal_volume=80.0)
    close[61] = 0.0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mask = _breakout_mask(close, volume)
    assert not [item for item in caught if issubclass(item.category, RuntimeWarning)]
    assert mask[62]
