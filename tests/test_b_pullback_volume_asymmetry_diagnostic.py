import pytest

from b_pullback_volume_asymmetry_diagnostic import _feature_result_from_path, pullback_volume_features
from test_b_phase_volume_path_diagnostic import _fixture


def test_up_down_classification_excludes_signal_day_and_reuses_reactivation_alias():
    close, volume, high, low, dates = _fixture(signal_volume=80.0)
    close[63:69] = [10.0, 10.2, 10.0, 10.1, 10.1, 10.0]
    volume[63:69] = [80.0, 40.0, 20.0, 60.0, 30.0, 10.0]
    first = pullback_volume_features(close, volume, high, low, dates)

    volume[-1] = 999.0
    second = pullback_volume_features(close, volume, high, low, dates)

    assert first["down_volume_share"] == pytest.approx(110.0 / 240.0)
    assert first["up_down_volume_ratio"] == pytest.approx(50.0 / (110.0 / 3.0))
    assert first["descriptive_counts"] == {"A": 3, "B": 2, "C": 1, "D": 0, "OTHER": 0}
    assert first["down_volume_share"] == second["down_volume_share"]
    assert first["up_down_volume_ratio"] == second["up_down_volume_ratio"]
    assert first["pullback_volume_decay_ratio"] == second["pullback_volume_decay_ratio"]
    assert first["reactivation_vs_pullback_volume"] == first["path"]["reactivation_vs_retest_ratio"]
    assert first["reactivation_vs_pullback_volume"] != second["reactivation_vs_pullback_volume"]


def test_zero_pullback_volume_is_missing_not_zero_filled():
    close, volume, high, low, dates = _fixture()
    close[63:69] = [10.0, 10.2, 10.0, 10.1, 10.0, 10.1]
    volume[63:69] = 0.0
    result = pullback_volume_features(close, volume, high, low, dates)

    assert result["down_volume_share"] is None
    assert result["up_down_volume_ratio"] is None
    assert result["pullback_volume_decay_ratio"] is None
    assert result["feature_unavailable"]["down_volume_share"] == "INVALID_PULLBACK_VOLUME_SUM"
    assert result["feature_unavailable"]["pullback_volume_decay_ratio"] == "INVALID_PULLBACK_HALF_VOLUME"


def test_nonpositive_breakout_volume_makes_worst_price_ratio_missing():
    close, volume, high, low, dates = _fixture()
    result = pullback_volume_features(close, volume, high, low, dates)
    volume[62] = 0.0
    rebuilt = _feature_result_from_path(result["path"], close, volume, high, low, dates)

    assert rebuilt["worst_price_day_volume_ratio"] is None
    assert rebuilt["feature_unavailable"]["worst_price_day_volume_ratio"] == "INVALID_BREAKOUT_VOLUME"


def test_worst_price_tie_uses_earliest_day():
    close, volume, high, low, dates = _fixture()
    low[63] = 9.5
    low[64] = 9.5
    volume[63] = 30.0
    volume[64] = 60.0
    result = pullback_volume_features(close, volume, high, low, dates)

    assert result["worst_price_day"] == dates[63]
    assert result["worst_price_day_volume_ratio"] == pytest.approx(30.0 / 200.0)


@pytest.mark.parametrize(
    ("breakout_index", "pullback_volumes"),
    [
        (62, [100.0, 100.0, 100.0, 50.0, 50.0, 50.0]),
        (63, [100.0, 100.0, 50.0, 50.0, 50.0]),
    ],
)
def test_pullback_volume_decay_uses_even_and_odd_half_split(breakout_index, pullback_volumes):
    close, volume, high, low, dates = _fixture(breakout_index=breakout_index)
    volume[breakout_index + 1 : -1] = pullback_volumes
    result = pullback_volume_features(close, volume, high, low, dates)

    assert result["pullback_volume_decay_ratio"] == pytest.approx(0.5)


def test_no_up_or_down_day_is_missing():
    close, volume, high, low, dates = _fixture()
    close[63:69] = close[62]
    result = pullback_volume_features(close, volume, high, low, dates)

    assert result["up_down_volume_ratio"] is None
    assert result["feature_unavailable"]["up_down_volume_ratio"] == "NO_UP_OR_DOWN_DAY"
