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


def test_cloud_rule_performance_provider_gap_is_explicit_and_other_rows_continue(monkeypatch, tmp_path):
    import live_acquisition as live

    class FakeHiThink:
        def __init__(self, *, capture_store=None):
            self.read_attempts = []

    def resolve(_client, code, **_kwargs):
        if code == "600519":
            raise live.LiveAcquisitionError(live.PROVIDER_FAILURE, "provider unavailable for 600519")
        return [
            bar("2026-09-04", opening=100, high=101, low=99, close=100),
            bar("2026-09-07", opening=110, high=111, low=109, close=110),
        ], {"provider": "HiThink Financial-API", "source": "historical endpoint"}

    monkeypatch.setenv(EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION_ENV, "1")
    monkeypatch.setattr(live, "HiThinkClient", FakeHiThink)
    monkeypatch.setattr(live, "_resolve_market_bars", resolve)

    signals = [signal(code="600519"), signal(code="000001")]
    before = copy.deepcopy(signals)
    history, provenance = load_strategy_rule_historical_ohlc(
        signals, "2026-09-07", paths=DataPaths(tmp_path / "data"), calendar=CALENDAR,
    )
    assert set(history) == {"000001"}
    missing = provenance["by_code"]["600519"]
    assert missing["status"] == "MISSING_OR_INVALID"
    assert missing["source"] == EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION
    assert "provider unavailable" in missing["reason"]
    assert "600519" in provenance["__meta__"]["errors"][0]
    assert provenance["__meta__"]["provider_calls"] == 2
    result = build_strategy_rule_performance(
        signals, history, "2026-09-07", calendar=CALENDAR, historical_provenance=provenance,
    )
    row = result["performance_data_incomplete_rows"][0]
    assert row["code"] == "600519" and row["status"] == PERFORMANCE_DATA_INCOMPLETE
    assert row["entry_price"] is None and row["realized_return_pct"] is None
    assert row["historical_provenance"] == missing
    assert result["confirmed_closed_count"] == result["resolved_target"] == 1
    assert result["avg_return_pct"] == 10 and result["win_rate"] == 100
    assert result["closed_trades"][0]["code"] == "000001"
    assert signals == before and list((tmp_path / "data").rglob("*")) == []


@pytest.mark.parametrize("status", ["INPUT_CONFLICT", "INPUT_DATE_MISMATCH", "FUTURE_DATA_DETECTED", "UNKNOWN"])
def test_cloud_rule_performance_integrity_failure_still_raises(monkeypatch, tmp_path, status):
    import live_acquisition as live

    def fail(*args, **kwargs):
        raise live.LiveAcquisitionError(status, "structural historical error")

    monkeypatch.setenv(EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION_ENV, "1")
    monkeypatch.setattr(live, "HiThinkClient", lambda **kwargs: object())
    monkeypatch.setattr(live, "_resolve_market_bars", fail)
    with pytest.raises(live.LiveAcquisitionError, match=status):
        load_strategy_rule_historical_ohlc(
            [signal()], "2026-09-07", paths=DataPaths(tmp_path / "data"), calendar=CALENDAR,
        )


@pytest.mark.parametrize("status", ["FUTURE_DATA_DETECTED", "PERSISTENCE_CONFLICT"])
def test_rule_history_cache_integrity_error_cannot_be_repaired_by_refetch(monkeypatch, tmp_path, status):
    import live_acquisition as live

    def fail(*args, **kwargs):
        raise live.LiveAcquisitionError(status, "invalid cached evidence")

    def forbidden_refetch(*args, **kwargs):
        raise AssertionError("structural cache errors must not trigger provider reconstruction")

    paths = DataPaths(tmp_path / "data")
    (paths.root / "t_close_evidence").mkdir(parents=True)
    monkeypatch.setenv(EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION_ENV, "1")
    monkeypatch.setattr(live, "HiThinkClient", lambda **kwargs: object())
    monkeypatch.setattr(live, "_load_captured_market_bars", fail)
    monkeypatch.setattr(live, "_resolve_market_bars", forbidden_refetch)
    with pytest.raises(live.LiveAcquisitionError, match=status):
        load_strategy_rule_historical_ohlc([signal()], "2026-09-07", paths=paths, calendar=CALENDAR)


def test_single_account_blocks_duplicate_position_while_holding_and_enforces_exit_cooldown():
    from track_perf import (
        RULE_STATUS_SKIPPED_DEDUP,
        SINGLE_ACCOUNT_PERFORMANCE_MODEL,
        SKIP_REASON_ALREADY_HOLDING,
        SKIP_REASON_RECENT_EXIT_COOLDOWN,
        build_single_account_rule_performance,
    )

    # S1 enters on 09-04 and stays OPEN until stopping out on 09-15 (8 sessions after S1).
    # S2 (09-07) and S3 (09-14, >5 sessions after S1) occur while S1 is OPEN -> skipped as ALREADY_HOLDING.
    # S4 (09-18, 3 sessions after 09-15 exit) -> skipped as RECENT_EXIT_COOLDOWN.
    # S5 (09-22, 5 sessions after 09-15 exit) -> skipped as RECENT_EXIT_COOLDOWN (5D boundary inclusive).
    # S6 (09-23, 6 sessions after 09-15 exit) -> accepted and enters on 09-24!
    signals = [
        signal(code="601033", signal_date="2026-09-03", trigger=100, stop=95, target=110),
        signal(code="601033", signal_date="2026-09-07", trigger=100, stop=95, target=110),
        signal(code="601033", signal_date="2026-09-14", trigger=100, stop=95, target=110),
        signal(code="601033", signal_date="2026-09-18", trigger=96, stop=92, target=106),
        signal(code="601033", signal_date="2026-09-22", trigger=96, stop=92, target=106),
        signal(code="601033", signal_date="2026-09-23", trigger=96, stop=92, target=106),
    ]
    bars = [
        bar("2026-09-04", opening=99, high=101, low=98, close=100),  # S1 enters
        bar("2026-09-07", opening=100, high=102, low=98, close=101),
        bar("2026-09-08", opening=101, high=102, low=98, close=100),
        bar("2026-09-09", opening=100, high=102, low=98, close=100),
        bar("2026-09-10", opening=100, high=102, low=98, close=100),
        bar("2026-09-11", opening=100, high=102, low=98, close=100),
        bar("2026-09-14", opening=100, high=102, low=98, close=99),
        bar("2026-09-15", opening=97, high=98, low=94, close=95),   # S1 stops out at 95
        bar("2026-09-16", opening=95, high=97, low=94, close=96),   # post-exit 1
        bar("2026-09-17", opening=96, high=97, low=95, close=96),   # post-exit 2
        bar("2026-09-18", opening=96, high=97, low=95, close=96),   # post-exit 3
        bar("2026-09-21", opening=96, high=97, low=95, close=96),   # post-exit 4
        bar("2026-09-22", opening=96, high=97, low=95, close=96),   # post-exit 5
        bar("2026-09-23", opening=95, high=95.5, low=94, close=95), # post-exit 6 (S6 accepted)
        bar("2026-09-24", opening=95, high=97, low=95, close=96.5), # S6 enters and stays OPEN
    ]
    dedup = build_single_account_rule_performance(
        signals, {"601033": bars}, "2026-09-24", calendar=CALENDAR,
    )
    raw = build_strategy_rule_performance(
        signals, {"601033": bars}, "2026-09-24", calendar=CALENDAR,
    )

    assert dedup["performance_model"] == SINGLE_ACCOUNT_PERFORMANCE_MODEL
    assert dedup["total_signals"] == 6
    assert dedup["accepted_signals"] == 2
    assert dedup["skipped_dedup_count"] == 4
    assert [r["skip_reason"] for r in dedup["skipped_rows"]] == [
        SKIP_REASON_ALREADY_HOLDING,
        SKIP_REASON_ALREADY_HOLDING,
        SKIP_REASON_RECENT_EXIT_COOLDOWN,
        SKIP_REASON_RECENT_EXIT_COOLDOWN,
    ]
    assert all(r["status"] == RULE_STATUS_SKIPPED_DEDUP for r in dedup["skipped_rows"])
    assert dedup["resolved_closed_trades"] == 1
    assert dedup["open_rule_trades"] == 1
    assert [r["signal_date"] for r in dedup["open_position_rows"]] == ["2026-09-23"]
    assert dedup["open_position_rows"][0]["holding_sessions"] == 1
    # Underlying raw MODEL_R remains unchanged (opens 5 trades and holds 3 duplicate open positions).
    assert raw["triggered"] == 5
    assert raw["open_rule_trades"] == 3


def test_single_account_signal_cooldown_pending_order_and_10d_untriggered_expiry():
    from track_perf import (
        RULE_STATUS_EXPIRED_UNTRIGGERED,
        SKIP_REASON_PENDING_ORDER_ACTIVE,
        SKIP_REASON_RECENT_SIGNAL_COOLDOWN,
        build_single_account_rule_performance,
    )

    # S1 on 09-03 with high trigger=120 never triggers within 10 sessions (09-04..09-17).
    # S2 on 09-08 (3 sessions after S1) -> skipped as RECENT_SIGNAL_COOLDOWN.
    # S3 on 09-14 (7 sessions after S1) -> skipped as PENDING_ORDER_ACTIVE (still inside 10D window).
    # On 09-17 (10th session), S1 expires as EXPIRED_UNTRIGGERED.
    # Even though 09-18 surges to 125, S1 must NOT fill late; S4 on 09-18 (with trigger=102) is accepted!
    signals = [
        signal(code="600398", signal_date="2026-09-03", trigger=120, stop=95, target=135),
        signal(code="600398", signal_date="2026-09-08", trigger=101, stop=95, target=112),
        signal(code="600398", signal_date="2026-09-14", trigger=101, stop=95, target=112),
        signal(code="600398", signal_date="2026-09-18", trigger=102, stop=97, target=115),
    ]
    ten_sessions = [
        "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10",
        "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17",
    ]
    bars = [bar(d, opening=100, high=105, low=98, close=101) for d in ten_sessions] + [
        bar("2026-09-18", opening=101, high=125, low=100, close=103),
        bar("2026-09-21", opening=102, high=104, low=101, close=103),
    ]
    dedup = build_single_account_rule_performance(
        signals, {"600398": bars}, "2026-09-21", calendar=CALENDAR,
    )

    assert dedup["accepted_signals"] == 2
    assert dedup["expired_untriggered"] == 1
    assert dedup["expired_untriggered_rows"][0]["signal_date"] == "2026-09-03"
    assert dedup["expired_untriggered_rows"][0]["status"] == RULE_STATUS_EXPIRED_UNTRIGGERED
    assert dedup["expired_untriggered_rows"][0]["exit_date"] == "2026-09-17"
    assert [r["skip_reason"] for r in dedup["skipped_rows"]] == [
        SKIP_REASON_RECENT_SIGNAL_COOLDOWN,
        SKIP_REASON_PENDING_ORDER_ACTIVE,
    ]
    assert [r["signal_date"] for r in dedup["open_position_rows"]] == ["2026-09-18"]
    assert dedup["open_position_rows"][0]["entry_price"] == 102


def test_single_account_admission_is_strictly_causal_across_report_dates():
    from track_perf import build_single_account_rule_performance, single_account_shortlist_exclusions

    signals = [
        signal(code="600809", signal_date="2026-09-03", trigger=100, stop=95, target=110),
        signal(code="600809", signal_date="2026-09-08", trigger=100, stop=95, target=110),
    ]
    bars = [
        bar("2026-09-04", opening=99, high=101, low=98, close=100),
        bar("2026-09-07", opening=100, high=102, low=98, close=101),
        bar("2026-09-08", opening=101, high=103, low=99, close=102),
        bar("2026-09-09", opening=102, high=112, low=101, close=111),  # S1 hits target AFTER 09-08
    ]
    at_signal_day = build_single_account_rule_performance(
        signals, {"600809": bars}, "2026-09-08", calendar=CALENDAR,
    )
    later = build_single_account_rule_performance(
        signals, {"600809": bars}, "2026-09-09", calendar=CALENDAR,
    )

    assert single_account_shortlist_exclusions(at_signal_day, "2026-09-08") == {
        "600809": {
            "skip_reason": "ALREADY_HOLDING",
            "blocking_signal_id": signals[0]["signal_id"],
            "blocking_signal_date": "2026-09-03",
            "blocking_entry_date": "2026-09-04",
            "blocking_exit_date": None,
            "blocking_exit_reason": None,
            "sessions_since_signal": 3,
            "sessions_since_exit": None,
        }
    }
    assert later["skipped_rows"][0]["skip_reason"] == "ALREADY_HOLDING"
    assert later["accepted_signals"] == 1
