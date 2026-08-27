import json

import pytest

from watchlist_schema import WatchlistSchemaError, validate_watchlist


def candidate(**overrides):
    value = {
        "code": "600519",
        "name": "贵州茅台",
        "sector": "消费",
        "buy_type": "A 平台突破",
        "score": 66,
        "price": 123.45,
        "chg": 2.1,
        "trigger": 120.0,
        "support": 118.0,
        "stop": 115.0,
        "target": 130.0,
        "rr": 2.0,
        "stop_dist": 4.2,
        "vol_ratio": 1.8,
        "turnover": 3.0,
        "float_mv": 1000.0,
        "target_type": "压力位",
        "risk": "-",
    }
    value.update(overrides)
    return value


def payload(**overrides):
    value = {
        "date": "2026-08-20",
        "mode": "close",
        "market_env": {"level": "B", "score": 5, "detail": {}},
        "sectors": [],
        "candidates": [candidate()],
    }
    value.update(overrides)
    return value


def test_canonical_schema_derives_stable_signal_id_and_setup():
    normalized = validate_watchlist(payload())
    item = normalized["candidates"][0]

    assert item["setup"] == "A 平台突破"
    assert item["strategy_version"] == "watchlist-v1"
    assert "2026-08-20" in item["signal_id"]
    assert "600519" in item["signal_id"]


def test_legacy_top_level_items_is_rejected_without_silent_compatibility():
    value = payload()
    value["items"] = value.pop("candidates")

    with pytest.raises(WatchlistSchemaError, match="candidates"):
        validate_watchlist(value)


def test_legacy_candidate_trig_is_rejected():
    value = payload()
    item = value["candidates"][0]
    item["trig"] = item.pop("trigger")

    with pytest.raises(WatchlistSchemaError, match="trigger"):
        validate_watchlist(value)

