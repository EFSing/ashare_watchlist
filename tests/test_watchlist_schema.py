import json

import pytest

from watchlist_schema import WatchlistSchemaError, validate_input_coverage, validate_watchlist


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


def test_degraded_coverage_accepts_multiple_exclusions_without_a_fixed_cap():
    records = []
    for index in range(3):
        symbol = f"60000{index}"
        records.append(
            {
                "symbol": symbol,
                "provider_symbol": f"{symbol}.SH",
                "target_date": "2026-08-20",
                "provider": "HiThink Financial-API",
                "status": "EXCLUDED_INPUT_ANOMALY",
                "reason": "SNAPSHOT_MISSING",
                "latest_historical_date": None,
                "quote_trade_state": "UNAVAILABLE",
                "evidence": {"quote": {}, "historical": {}},
                "policy_version": "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
            }
        )

    coverage = validate_input_coverage(
        {
            "schema_version": "INPUT_COVERAGE_V1",
            "coverage_status": "DEGRADED",
            "evaluated_symbol_count": 2,
            "excluded_symbol_count": 3,
            "excluded_symbols": records,
            "excluded_reason_counts": {"SNAPSHOT_MISSING": 3},
            "policy_version": "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
        }
    )

    assert coverage["excluded_symbol_count"] == 3


def test_no_valid_input_coverage_is_diagnostic_only_not_a_formal_watchlist():
    diagnostic = {
        "schema_version": "INPUT_COVERAGE_V1",
        "coverage_status": "NO_VALID_INPUT",
        "evaluated_symbol_count": 0,
        "excluded_symbol_count": 0,
        "excluded_symbols": [],
        "formal_result_valid": False,
        "policy_version": "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
    }
    validate_input_coverage(diagnostic, allow_no_valid=True)

    with pytest.raises(WatchlistSchemaError, match="unsupported"):
        validate_watchlist({**payload(candidates=[]), "input_coverage": diagnostic})
