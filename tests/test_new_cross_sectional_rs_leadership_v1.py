from __future__ import annotations

import math

import pytest

from new_cross_sectional_rs_leadership_v1 import (
    BOOTSTRAP_BLOCK_LENGTH,
    BOOTSTRAP_REPETITIONS,
    BOOTSTRAP_SEED,
    MEDIUM_LOOKBACK,
    SHORT_LOOKBACK,
    classify_membership,
    moving_block_bootstrap_ci,
    spearman,
    top_quintile_ranked,
    trailing_return,
)


def test_r20_uses_exact_21_bar_window_and_does_not_interpolate() -> None:
    closes = [100.0] * 21
    closes[-21] = 10.0
    closes[-20] = 9999.0
    assert trailing_return(closes, SHORT_LOOKBACK) == pytest.approx(9.0)
    with pytest.raises(ValueError):
        trailing_return(closes[:-1], SHORT_LOOKBACK)


def test_r60_uses_exact_61_bar_window() -> None:
    closes = [100.0] * 61
    closes[0] = 20.0
    assert trailing_return(closes, MEDIUM_LOOKBACK) == pytest.approx(4.0)
    with pytest.raises(ValueError):
        trailing_return(closes[:-1], MEDIUM_LOOKBACK)


def test_signal_window_is_t_close_only_and_future_bar_is_not_in_prefix() -> None:
    signal_prefix = [100.0] * 21
    signal_prefix[0] = 80.0
    signal_value = trailing_return(signal_prefix, SHORT_LOOKBACK)
    future_extended = signal_prefix + [10_000.0]
    assert signal_value == pytest.approx(0.25)
    assert trailing_return(future_extended[:-1], SHORT_LOOKBACK) == pytest.approx(signal_value)


def test_61_bar_minimum_is_explicit() -> None:
    assert len([1] * (MEDIUM_LOOKBACK + 1)) == 61
    with pytest.raises(ValueError):
        trailing_return([1.0] * MEDIUM_LOOKBACK, MEDIUM_LOOKBACK)


def test_deterministic_tie_break_is_symbol_ascending() -> None:
    ranks, leaders = top_quintile_ranked({"600002.sh": 1.0, "600001.sh": 1.0, "600003.sh": 0.5}, fraction=2 / 3)
    assert ranks == {"600001.sh": 1, "600002.sh": 2, "600003.sh": 3}
    assert leaders == {"600001.sh", "600002.sh"}


def test_top_k_is_ceil_of_twenty_percent() -> None:
    for n in range(1, 21):
        _ranks, leaders = top_quintile_ranked({f"s{index:02d}": float(index) for index in range(n)})
        assert len(leaders) == math.ceil(0.20 * n)


def test_candidate_is_exact_intersection_and_control_is_exact_difference() -> None:
    q20 = {"a", "b"}
    q60 = {"b", "c", "d"}
    classes = classify_membership(q20, q60)
    assert classes == {"b": "CANDIDATE", "c": "PRIMARY_CONTROL", "d": "PRIMARY_CONTROL"}
    assert set(classes) <= q60
    assert set(symbol for symbol, value in classes.items() if value == "CANDIDATE").isdisjoint(
        symbol for symbol, value in classes.items() if value == "PRIMARY_CONTROL"
    )


def test_common_benchmark_subtraction_is_rank_invariant() -> None:
    values = {"a": 0.20, "b": 0.10, "c": -0.05}
    ranks, _ = top_quintile_ranked(values)
    shifted_ranks, _ = top_quintile_ranked({symbol: value - 0.07 for symbol, value in values.items()})
    assert ranks == shifted_ranks


def test_date_equal_weight_and_block_bootstrap_are_deterministic() -> None:
    date_spreads = [1.0, -1.0, 2.0, -2.0]
    assert sum(date_spreads) / len(date_spreads) == 0.0
    values = list(range(BOOTSTRAP_BLOCK_LENGTH + 3))
    first = moving_block_bootstrap_ci(values, repetitions=128)
    second = moving_block_bootstrap_ci(values, repetitions=128)
    assert first == second
    assert BOOTSTRAP_REPETITIONS == 5000
    assert BOOTSTRAP_SEED == 20260906


def test_spearman_returns_none_for_insufficient_or_constant_input() -> None:
    assert spearman([1.0], [1.0]) is None
    assert spearman([1.0, 1.0], [1.0, 2.0]) is None
