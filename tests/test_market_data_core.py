from __future__ import annotations

from market_data_core import (
    TRADE_STATE_NO_TRADE,
    TRADE_STATE_TRADED,
    TRADE_STATE_UNKNOWN,
    classify_trade_state,
)


def test_null_snapshot_is_unknown_and_never_no_trade():
    assert classify_trade_state({"price": None, "prev_close": None}) == TRADE_STATE_UNKNOWN


def test_partial_snapshot_is_unknown_and_never_no_trade():
    assert classify_trade_state(
        {
            "price": 10.0,
            "prev_close": 10.0,
            "open": None,
            "high": None,
            "low": None,
            "volume": None,
        }
    ) == TRADE_STATE_UNKNOWN


def test_explicit_zero_volume_shape_is_no_trade_without_turnover_rate():
    assert classify_trade_state(
        {
            "price": 10.0,
            "prev_close": 10.0,
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "volume": 0.0,
        }
    ) == TRADE_STATE_NO_TRADE


def test_valid_traded_shape_is_traded_without_turnover_rate():
    assert classify_trade_state(
        {
            "price": 10.2,
            "prev_close": 10.0,
            "open": 10.0,
            "high": 10.3,
            "low": 9.9,
            "volume": 100.0,
        }
    ) == TRADE_STATE_TRADED
