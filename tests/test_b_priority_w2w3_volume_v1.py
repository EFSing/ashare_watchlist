"""Causality, identity and real-parity boundaries for the research input audit."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

import b_priority_w2w3_volume_v1 as study
from test_b_breakout_retest_v1_1 import _b_bars


def structure_arrays():
    close = np.full(70, 10.0)
    high = np.full(70, 10.2)
    low = np.full(70, 9.0)
    high[62] = 12.0
    low[63:69] = 10.0
    close[-1] = 11.0
    return close, high, low


@pytest.mark.parametrize("signal_close,state", [
    (10.99, "EARLY_PULLBACK"), (11.0, "W2_TO_W3_TRANSITION_PROXY"),
    (12.0, "W2_TO_W3_TRANSITION_PROXY"), (12.01, "POST_H1_CONTINUATION_PROXY"),
])
def test_exact_structure_boundaries(signal_close, state):
    c, h, l = structure_arrays()
    c[-1] = signal_close
    assert study.structure_proxy(c, h, l, 62)["state"] == state


def test_equal_high_uses_first_index_and_h1_l2_exclude_signal_day():
    c, h, l = structure_arrays()
    h[65] = 12.0
    l[63] = 9.5
    h[-1], l[-1] = 9999, 0.01
    result = study.structure_proxy(c, h, l, 62)
    assert result["h1_index"] == 62
    assert (result["H1"], result["L2"]) == (12.0, 9.5)
    assert result["L0"] == 9.0
    assert result["h1_index"] < len(c) - 1


@pytest.mark.parametrize("scenario", ["last_day_high", "no_pullback", "zero_denominator", "below_base", "nonfinite"])
def test_invalid_structure_remains_an_explicit_state(scenario):
    c, h, l = structure_arrays()
    i = 62
    if scenario == "last_day_high":
        h[-2] = 20
    elif scenario == "no_pullback":
        i = 68
    elif scenario == "zero_denominator":
        l[63:69] = 12
    elif scenario == "below_base":
        l[63] = 8
    else:
        l[63] = np.nan
    result = study.structure_proxy(c, h, l, i)
    assert result["state"] == study.INVALID
    assert result["recovery_ratio"] is None


def test_real_entry_point_preserves_identity_and_does_not_read_future_prices():
    bars = _b_bars()
    identity = ("600001.sh", str(bars[-1]["date"]), "B_BREAKOUT_RETEST")
    expected = study.reconstruct(identity, bars)
    class FutureBar(dict):
        def __getitem__(self, key):
            if key != "date":
                pytest.fail("T+1 OHLCV accessed")
            return "2099-01-01"
    assert study.reconstruct(identity, bars + [FutureBar()]) == expected
    assert study.reconstruct(identity, copy.deepcopy(bars)) == expected
    assert tuple(expected[f] for f in ("symbol", "signal_date", "setup_id")) == identity


@pytest.mark.parametrize("scenario", ["missing_T", "missing_value", "nan", "duplicate"])
def test_missing_or_invalid_bars_fail_closed(scenario):
    bars = _b_bars()
    day = str(bars[-1]["date"])
    if scenario == "missing_T":
        bars.pop()
    elif scenario == "missing_value":
        del bars[-2]["low"]
    elif scenario == "nan":
        bars[-2]["close"] = float("nan")
    else:
        bars[-2]["date"] = bars[-3]["date"]
    with pytest.raises((ValueError, KeyError)):
        study.reconstruct(("600001.sh", day, "B_BREAKOUT_RETEST"), bars)


def test_signal_day_high_low_and_volume_do_not_enter_frozen_observables():
    bars = _b_bars()
    identity = ("600001.sh", str(bars[-1]["date"]), "B_BREAKOUT_RETEST")
    expected = study.reconstruct(identity, bars)
    bars[-1].update(high=10000.0, low=0.01, volume=1.0)
    actual = study.reconstruct(identity, bars)
    assert actual["structure"] == expected["structure"]
    assert actual["volume"] == expected["volume"]


def test_volume_parity_checks_values_window_and_missing_reason():
    expected = {"down_volume_share": 0.3, "up_down_volume_ratio": 1.2,
                "pullback_volume_decay_ratio": None, "window_days": 2,
                "missing_reason": {"pullback_volume_decay_ratio": "PULLBACK_WINDOW_LT_4"}}
    assert study.parity_difference(copy.deepcopy(expected), expected) == []
    actual = copy.deepcopy(expected)
    actual.update(down_volume_share=0.4, window_days=3, missing_reason={})
    assert study.parity_difference(actual, expected) == ["down_volume_share", "window_days", "missing_reason"]


def test_delivered_gap_is_not_a_negative_result_or_synthetic_parity_pass():
    root = Path(__file__).resolve().parents[1]
    result = json.loads((root / study.OUTPUT / "summary.json").read_text(encoding="utf-8"))
    assert result["status"] == study.BLOCKER
    assert result["real_observation_parity"]["parity_status"] == "NOT_RUN_INPUTS_UNAVAILABLE"
    assert result["real_observation_parity"]["real_rows_reconstructed"] == 0
    assert result["real_observation_parity"]["parity_mismatches"] is None
    assert sum(b["rows"] for b in result["boards"].values()) == result["cohort"]["rows"] == 17714
    assert result["boards"]["Main"]["rows"] == 10779
    assert result["boards"]["OUT_OF_SCOPE_PREFIX"]["rows"] == 706
    assert all(m["5D"] is None and m["Top1_uplift_pp"] is None for m in result["methods"].values())
    assert result["boundaries"]["outcome_values_accessed"] is False
    assert result["boundaries"]["final_oos"] == "SEALED / UNREAD"
    assert all(d.endswith("NEEDS_MORE_EVIDENCE") for d in result["decisions"])
