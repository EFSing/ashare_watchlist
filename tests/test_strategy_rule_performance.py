from __future__ import annotations

import copy
from datetime import date

import pytest

from track_perf import (
    CURRENT_PROSPECTIVE_STRATEGY,
    EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION,
    EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION_ENV,
    EXIT_REASON_AMBIGUOUS,
    EXIT_REASON_STOP,
    EXIT_REASON_TARGET,
    PERFORMANCE_DATA_INCOMPLETE,
    RULE_STATUS_NOT_YET_ELIGIBLE,
    RULE_STATUS_OPEN,
    STRATEGY_RULE_CONFIG_ERROR,
    STRATEGY_RULE_PERFORMANCE_MODEL,
    build_strategy_rule_performance,
    load_strategy_rule_historical_ohlc,
    stable_signal_id,
)
from data_paths import DataPaths
from trading_calendar import TradingCalendar


CALENDAR = TradingCalendar(holidays=set())


def signal(
    *,
    code: str = "600519",
    signal_date: str = "2026-09-03",
    trigger: float = 100.0,
    stop: float = 95.0,
    target: float = 110.0,
    observations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    setup = "B_BREAKOUT_RETEST"
    return {
        "signal_id": stable_signal_id(CURRENT_PROSPECTIVE_STRATEGY, signal_date, code, setup),
        "strategy_version": CURRENT_PROSPECTIVE_STRATEGY,
        "date": signal_date,
        "code": code,
        "setup": setup,
        "name": f"测试{code}",
        "score": 60,
        "trigger": trigger,
        "stop": stop,
        "target": target,
        "rr": (target - trigger) / (trigger - stop) if trigger != stop else None,
        # Deliberately present only to prove the rule evaluator does not use
        # prospective observations as its source of truth.
        "observations": observations or [],
    }


def bar(day: str, *, opening: float, high: float, low: float, close: float | None = None) -> dict[str, object]:
    return {
        "date": day,
        "open": opening,
        "high": high,
        "low": low,
        "close": opening if close is None else close,
    }


def evaluate(
    item: dict[str, object],
    bars: list[dict[str, object]],
    *,
    as_of: str = "2026-09-11",
) -> dict[str, object]:
    result = build_strategy_rule_performance(
        [item],
        {str(item["code"]): bars},
        date.fromisoformat(as_of),
        calendar=CALENDAR,
        historical_provenance={"__meta__": {"provider_calls": 0}},
    )
    assert result["performance_model"] == STRATEGY_RULE_PERFORMANCE_MODEL
    return result


def test_entry_uses_canonical_trigger_even_when_open_is_above_trigger():
    item = signal()
    result = evaluate(item, [
        bar("2026-09-04", opening=108, high=109, low=99, close=105),
        bar("2026-09-07", opening=105, high=106, low=101, close=104),
    ], as_of="2026-09-07")

    row = result["all_rows"][0]
    assert row["entry_date"] == "2026-09-04"
    assert row["entry_price"] == 100.0
    assert row["status"] == RULE_STATUS_OPEN


def test_entry_day_stop_touch_cannot_exit_under_t1():
    result = evaluate(signal(), [
        bar("2026-09-04", opening=100, high=105, low=94, close=96),
    ], as_of="2026-09-04")

    row = result["all_rows"][0]
    assert row["status"] == RULE_STATUS_OPEN
    assert row["entry_day_stop_touched"] is True
    assert row["exit_date"] is None
    assert result["resolved_closed_trades"] == 0


def test_entry_day_target_touch_cannot_exit_under_t1():
    result = evaluate(signal(), [
        bar("2026-09-04", opening=100, high=111, low=99, close=108),
    ], as_of="2026-09-04")

    row = result["all_rows"][0]
    assert row["status"] == RULE_STATUS_OPEN
    assert row["entry_day_target_touched"] is True
    assert row["exit_date"] is None


def test_next_session_stop_uses_stop_price_even_when_open_gaps_below_it():
    result = evaluate(signal(), [
        bar("2026-09-04", opening=100, high=101, low=99, close=100),
        bar("2026-09-07", opening=90, high=96, low=89, close=91),
    ])

    row = result["closed_trades"][0]
    assert row["exit_reason"] == EXIT_REASON_STOP
    assert row["exit_price"] == 95.0
    assert row["realized_return_pct"] == -5.0
    assert row["realized_r"] == -1.0


def test_next_session_target_uses_target_price_even_when_open_gaps_above_it():
    result = evaluate(signal(), [
        bar("2026-09-04", opening=100, high=101, low=99, close=100),
        bar("2026-09-07", opening=120, high=121, low=109, close=119),
    ])

    row = result["closed_trades"][0]
    assert row["exit_reason"] == EXIT_REASON_TARGET
    assert row["exit_price"] == 110.0
    assert row["realized_return_pct"] == 10.0
    assert row["realized_r"] == 2.0


def test_same_sellable_bar_stop_and_target_is_ambiguous_and_excluded_from_stats():
    result = evaluate(signal(), [
        bar("2026-09-04", opening=100, high=101, low=99, close=100),
        bar("2026-09-07", opening=100, high=111, low=94, close=101),
    ])

    row = result["ambiguous_rows"][0]
    assert row["status"] == EXIT_REASON_AMBIGUOUS
    assert row["exit_price"] is None
    assert result["ambiguous"] == 1
    assert result["resolved_closed_trades"] == 0
    assert result["win_rate"] is None
    assert result["avg_return_pct"] is None
    assert result["profit_factor"] is None


def test_t10_is_not_a_forced_exit_and_trade_remains_open():
    days = [
        "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10",
        "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17",
    ]
    result = evaluate(
        signal(),
        [bar(day, opening=100, high=104, low=97, close=103) for day in days],
        as_of="2026-09-17",
    )

    row = result["open_position_rows"][0]
    assert row["status"] == RULE_STATUS_OPEN
    assert row["exit_reason"] is None
    assert result["time_exit"] is False
    assert result["time_exit_count"] == 0


def test_missing_prospective_observation_does_not_block_rule_performance():
    result = evaluate(
        signal(observations=[]),
        [
            bar("2026-09-04", opening=100, high=101, low=99, close=100),
            bar("2026-09-07", opening=100, high=111, low=109, close=110),
        ],
    )

    assert result["resolved_target"] == 1
    assert result["performance_data_incomplete"] == 0


def test_rule_reconstruction_does_not_backfill_or_mutate_canonical_signal():
    item = signal(observations=[])
    before = copy.deepcopy(item)

    evaluate(item, [
        bar("2026-09-04", opening=100, high=101, low=99, close=100),
        bar("2026-09-07", opening=100, high=111, low=109, close=110),
    ])

    assert item == before
    assert item["observations"] == []


def test_missing_historical_ohlc_is_incomplete_and_not_guessed():
    item = signal()
    result = build_strategy_rule_performance(
        [item],
        {},
        "2026-09-11",
        calendar=CALENDAR,
    )

    row = result["performance_data_incomplete_rows"][0]
    assert row["status"] == PERFORMANCE_DATA_INCOMPLETE
    assert row["exit_price"] is None
    assert result["resolved_closed_trades"] == 0


def test_future_bar_is_ignored_by_report_as_of_cutoff():
    result = evaluate(
        signal(),
        [
            bar("2026-09-04", opening=100, high=101, low=99, close=100),
            bar("2026-09-07", opening=100, high=106, low=99, close=104),
            bar("2026-09-08", opening=100, high=111, low=109, close=110),
        ],
        as_of="2026-09-07",
    )

    row = result["open_position_rows"][0]
    assert row["status"] == RULE_STATUS_OPEN
    assert row["exit_date"] is None
    assert result["resolved_closed_trades"] == 0


def test_signal_on_report_date_has_no_t1_opportunity_or_entry():
    result = evaluate(
        signal(signal_date="2026-09-11"),
        [bar("2026-09-11", opening=100, high=111, low=94, close=105)],
        as_of="2026-09-11",
    )

    row = result["all_rows"][0]
    assert row["status"] == RULE_STATUS_NOT_YET_ELIGIBLE
    assert row["entry_date"] is None
    assert result["signals_with_t1_opportunity"] == 0
    assert result["triggered"] == 0


def test_invalid_long_rule_is_configuration_error():
    result = evaluate(signal(trigger=100, stop=100, target=110), [
        bar("2026-09-04", opening=100, high=101, low=99, close=100),
    ], as_of="2026-09-04")

    row = result["config_error_rows"][0]
    assert row["status"] == STRATEGY_RULE_CONFIG_ERROR
    assert result["resolved_closed_trades"] == 0


def test_theoretical_main_metrics_include_only_resolved_target_and_stop():
    result = build_strategy_rule_performance(
        [signal(code="600519"), signal(code="000001")],
        {
            "600519": [
                bar("2026-09-04", opening=100, high=101, low=99, close=100),
                bar("2026-09-07", opening=100, high=111, low=109, close=110),
            ],
            "000001": [
                bar("2026-09-04", opening=100, high=101, low=99, close=100),
                bar("2026-09-07", opening=90, high=96, low=89, close=91),
            ],
        },
        "2026-09-11",
        calendar=CALENDAR,
    )

    assert result["resolved_target"] == 1
    assert result["resolved_stop"] == 1
    assert result["resolved_closed_trades"] == 2
    assert result["win_rate"] == 50.0
    assert result["avg_return_pct"] == 2.5
    assert result["avg_r"] == 0.5
    assert result["ambiguous"] == 0


def test_cloud_rule_performance_reconstructs_missing_history_in_memory_only(monkeypatch, tmp_path):
    import live_acquisition as live

    item = signal(signal_date="2026-09-03")
    before = copy.deepcopy(item)
    calls: list[str] = []

    class FakeHiThink:
        def __init__(self, *, capture_store=None):
            assert capture_store is None
            self.read_attempts = []

    def fake_resolve(client, code, **kwargs):
        calls.append(code)
        assert kwargs["as_of_date"] == "2026-09-07"
        return [
            bar("2026-09-04", opening=100, high=101, low=99, close=100),
            bar("2026-09-07", opening=100, high=111, low=109, close=110),
        ], {
            "provider": "HiThink Financial-API",
            "source": "provider historical endpoint",
            "adjustment_mode": "PROVIDER_QFQ_SNAPSHOT",
            "selection": "PRIMARY",
        }

    monkeypatch.setenv(EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION_ENV, "1")
    monkeypatch.setattr(live, "HiThinkClient", FakeHiThink)
    monkeypatch.setattr(live, "_resolve_market_bars", fake_resolve)

    history, provenance = load_strategy_rule_historical_ohlc(
        [item],
        "2026-09-07",
        paths=DataPaths(tmp_path / "data"),
        calendar=CALENDAR,
    )

    assert calls == ["600519"]
    assert history["600519"][1]["close"] == 110
    assert provenance["by_code"]["600519"]["source"] == EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION
    assert provenance["by_code"]["600519"]["persisted"] is False
    assert provenance["by_code"]["600519"]["bars_persisted"] is False
    assert provenance["__meta__"]["provider_calls"] == 1
    assert list((tmp_path / "data").rglob("*")) == []
    assert item == before


def test_cloud_rule_performance_provider_failure_is_not_silently_downgraded(monkeypatch, tmp_path):
    import live_acquisition as live

    class FakeHiThink:
        def __init__(self, *, capture_store=None):
            self.read_attempts = []

    def fail_resolve(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setenv(EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION_ENV, "1")
    monkeypatch.setattr(live, "HiThinkClient", FakeHiThink)
    monkeypatch.setattr(live, "_resolve_market_bars", fail_resolve)

    with pytest.raises(ValueError, match=EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION):
        load_strategy_rule_historical_ohlc(
            [signal(signal_date="2026-09-03")],
            "2026-09-07",
            paths=DataPaths(tmp_path / "data"),
            calendar=CALENDAR,
        )
