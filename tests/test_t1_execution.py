from __future__ import annotations

from datetime import date

import pytest

from track_perf import (
    EXECUTION_T_PLUS_1_PENDING,
    EXECUTION_VERIFIED,
    EXIT_REASON_AMBIGUOUS,
    EXIT_REASON_EXPIRED_UNTRIGGERED,
    EXIT_REASON_STOP,
    EXIT_REASON_STOP_GAP,
    EXIT_REASON_TARGET,
    EXIT_REASON_TARGET_GAP,
    EXIT_REASON_TIME,
    EXIT_REASON_TIME_DEFERRED_T1,
    UNVERIFIED_MISSING_EXECUTION_OBSERVATION,
    build_trade_performance_summary,
    new_tracker,
    rebuild_execution_state_from_observations,
    reconcile_tracker_execution,
    stable_signal_id,
)
from trading_calendar import TradingCalendar


CALENDAR = TradingCalendar(holidays=set())
SIGNAL_DATE = "2026-09-03"
STRATEGY = "B_BREAKOUT_RETEST_LEGACY_V1_1"


def signal(code: str = "600519", signal_date: str = SIGNAL_DATE) -> dict[str, object]:
    return {
        "signal_id": stable_signal_id(STRATEGY, signal_date, code, "B_BREAKOUT_RETEST"),
        "strategy_version": STRATEGY,
        "date": signal_date,
        "code": code,
        "setup": "B_BREAKOUT_RETEST",
        "name": f"测试{code}",
        "buy_type": "B 突破回踩",
        "score": 60,
        "trigger": 100.0,
        "stop": 95.0,
        "target": 110.0,
        "rr": 2.0,
        "status": "pending",
        "entry_price": None,
        "result_price": None,
        "days_tracked": 0,
        "first_trigger_date": None,
        "close_date": None,
        "ambiguity_reason": None,
        "observations": [],
        "review_points": {},
    }


def bar(day: str, *, opening: float, high: float, low: float, price: float | None = None) -> dict[str, object]:
    return {
        "date": day,
        "open": opening,
        "high": high,
        "low": low,
        "price": opening if price is None else price,
    }


def replay(item: dict[str, object], *bars: dict[str, object], as_of: str | None = None) -> dict[str, object]:
    item["observations"] = list(bars)
    return rebuild_execution_state_from_observations(item, calendar=CALENDAR, as_of=as_of)


def ten_sessions() -> list[str]:
    return [
        "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10",
        "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17",
    ]


def full_path(*, final_price: float = 103.0, entry: bool = True) -> list[dict[str, object]]:
    days = ten_sessions()
    bars = [
        bar(days[0], opening=100.0 if entry else 99.0, high=105.0 if entry else 99.0, low=99.0 if entry else 98.0),
    ]
    bars.extend(bar(day, opening=102.0, high=105.0, low=101.0) for day in days[1:-1])
    bars.append(bar(days[-1], opening=102.0, high=105.0, low=101.0, price=final_price))
    return bars


def test_t1_entry_day_stop_touch_does_not_exit_and_sets_sellable_from():
    item = signal()
    state = replay(item, bar("2026-09-04", opening=100, high=111, low=94, price=100), as_of="2026-09-04")

    assert state["status"] == "triggered"
    assert state["entry_date"] == "2026-09-04"
    assert state["entry_price"] == 100.0
    assert state["sellable_from"] == "2026-09-07"
    assert state["exit_date"] is None
    assert state["entry_day_stop_touched"] is True
    assert state["entry_day_target_touched"] is True


def test_t1_entry_day_target_touch_does_not_win():
    state = replay(
        signal("600520"),
        bar("2026-09-04", opening=100, high=110, low=99, price=105),
        as_of="2026-09-04",
    )

    assert state["status"] == "triggered"
    assert state["exit_reason"] is None
    assert state["realized_return_pct"] is None


def test_entry_day_both_stop_and_target_is_not_ambiguous_exit():
    state = replay(
        signal("600521"),
        bar("2026-09-04", opening=100, high=111, low=94, price=100),
        as_of="2026-09-04",
    )

    assert state["status"] == "triggered"
    assert state["status"] != EXIT_REASON_AMBIGUOUS
    assert state["exit_date"] is None


@pytest.mark.parametrize(
    ("day_bar", "reason", "exit_price", "status"),
    [
        (bar("2026-09-07", opening=100, high=104, low=94, price=98), EXIT_REASON_STOP, 95.0, "loss"),
        (bar("2026-09-07", opening=100, high=111, low=99, price=108), EXIT_REASON_TARGET, 110.0, "win"),
    ],
)
def test_sellable_day_single_stop_or_target_creates_confirmed_exit(day_bar, reason, exit_price, status):
    item = signal(str(600522 + int(exit_price)))
    state = replay(
        item,
        bar("2026-09-04", opening=100, high=105, low=99),
        day_bar,
        as_of="2026-09-07",
    )

    assert state["status"] == status
    assert state["exit_reason"] == reason
    assert state["exit_price"] == exit_price
    assert state["realized_return_pct"] == pytest.approx((exit_price / 100 - 1) * 100)
    assert state["holding_sessions"] == 2


def test_sellable_day_stop_and_target_is_ambiguous_and_unverified():
    state = replay(
        signal("600524"),
        bar("2026-09-04", opening=100, high=105, low=99),
        bar("2026-09-07", opening=100, high=111, low=94),
        as_of="2026-09-07",
    )

    assert state["status"] == "AMBIGUOUS_SAME_BAR"
    assert state["exit_reason"] == EXIT_REASON_AMBIGUOUS
    assert state["exit_date"] == "2026-09-07"
    assert state["realized_return_pct"] == "UNVERIFIED"
    assert state["realized_r"] == "UNVERIFIED"


@pytest.mark.parametrize(
    ("opening", "reason", "expected"),
    [(94.0, EXIT_REASON_STOP_GAP, 94.0), (111.0, EXIT_REASON_TARGET_GAP, 111.0)],
)
def test_sellable_day_gap_exits_at_open(opening, reason, expected):
    state = replay(
        signal(str(600525 + int(opening))),
        bar("2026-09-04", opening=100, high=105, low=99),
        bar("2026-09-07", opening=opening, high=max(opening, 105), low=min(opening, 94), price=opening),
        as_of="2026-09-07",
    )

    assert state["exit_reason"] == reason
    assert state["exit_price"] == expected


def test_t10_entry_waits_for_next_session_before_time_exit():
    item = signal("600527")
    bars = [bar(day, opening=99, high=99, low=98) for day in ten_sessions()[:-1]]
    bars.append(bar("2026-09-17", opening=100, high=101, low=99, price=100))
    state = replay(item, *bars, as_of="2026-09-17")

    assert state["status"] == "triggered"
    assert state["entry_date"] == "2026-09-17"
    assert state["sellable_from"] == "2026-09-18"
    assert state["exit_date"] is None
    assert state["exit_reason"] == "TIME_EXIT_PENDING_T1"
    assert state["execution_verification_status"] == EXECUTION_VERIFIED

    state = replay(
        item,
        *bars,
        bar("2026-09-18", opening=101, high=105, low=99, price=104),
        as_of="2026-09-18",
    )
    assert state["status"] == "expired"
    assert state["exit_reason"] == EXIT_REASON_TIME_DEFERRED_T1
    assert state["exit_price"] == 101.0


def test_untriggered_t10_is_expired_without_becoming_a_trade():
    item = signal("600528")
    state = replay(
        item,
        *[bar(day, opening=99, high=99, low=98) for day in ten_sessions()],
        as_of="2026-09-17",
    )

    assert state["status"] == "expired"
    assert state["exit_reason"] == EXIT_REASON_EXPIRED_UNTRIGGERED
    assert state["entry_date"] is None
    assert state["exit_price"] is None
    assert state["realized_return_pct"] is None


def test_time_exit_is_a_confirmed_trade_and_target_rate_stays_zero():
    tracker = new_tracker()
    positive = signal("600529")
    negative = signal("600530")
    untriggered = signal("600531")
    for item in (positive, negative, untriggered):
        tracker["signals"][item["signal_id"]] = item
    positive["observations"] = full_path(final_price=103.0)
    negative["observations"] = full_path(final_price=97.0)
    untriggered["observations"] = [bar(day, opening=99, high=99, low=98) for day in ten_sessions()]

    summary = build_trade_performance_summary(tracker, "2026-09-17", calendar=CALENDAR)

    assert summary["total_signals"] == 3
    assert summary["eligible_signals"] == 3
    assert summary["entered"] == 2
    assert summary["untriggered_expired"] == 1
    assert summary["confirmed_closed_count"] == 2
    assert summary["win_count"] == 1
    assert summary["loss_count"] == 1
    assert summary["flat_count"] == 0
    assert summary["win_rate"] == 50.0
    assert summary["target_exit_count"] == 0
    assert summary["stop_exit_count"] == 0
    assert summary["time_exit_count"] == 2
    assert summary["avg_return_pct"] == 0.0
    assert summary["profit_factor"] == 1.0


def test_missing_execution_observation_is_unverified_and_not_in_metrics():
    item = signal("600532")
    item["observations"] = [
        bar("2026-09-04", opening=100, high=105, low=99),
        bar("2026-09-08", opening=100, high=111, low=99),
    ]

    state = rebuild_execution_state_from_observations(item, calendar=CALENDAR, as_of="2026-09-08")
    tracker = new_tracker()
    tracker["signals"][item["signal_id"]] = item
    summary = build_trade_performance_summary(tracker, "2026-09-08", calendar=CALENDAR)

    assert state["status"] == "triggered"
    assert state["execution_verification_status"] == UNVERIFIED_MISSING_EXECUTION_OBSERVATION
    assert state["exit_date"] is None
    assert summary["eligible_signals"] == 0
    assert summary["execution_unverified"] == 1
    assert summary["confirmed_closed_count"] == 0


def test_as_of_date_never_uses_future_observation():
    item = signal("600533")
    item["observations"] = [
        bar("2026-09-04", opening=100, high=105, low=99),
        bar("2026-09-07", opening=100, high=111, low=99),
    ]
    state = rebuild_execution_state_from_observations(item, calendar=CALENDAR, as_of="2026-09-04")
    tracker = new_tracker()
    tracker["signals"][item["signal_id"]] = item
    summary = build_trade_performance_summary(tracker, "2026-09-04", calendar=CALENDAR)

    assert state["status"] == "triggered"
    assert state["exit_date"] is None
    assert summary["confirmed_closed_count"] == 0
    assert summary["open_positions"] == 1


def test_new_signal_before_first_execution_session_is_pending_not_unverified():
    item = signal("600534", signal_date="2026-09-11")
    state = rebuild_execution_state_from_observations(item, calendar=CALENDAR, as_of="2026-09-11")

    assert state["status"] == "pending"
    assert state["execution_verification_status"] == EXECUTION_T_PLUS_1_PENDING


def test_reconciliation_does_not_modify_fixed_horizon_review_points():
    item = signal("600535")
    item["review_points"] = {"T+3": {"sentinel": "keep"}}
    tracker = new_tracker()
    tracker["signals"][item["signal_id"]] = item

    reconcile_tracker_execution(tracker, "2026-09-04", calendar=CALENDAR)

    assert tracker["signals"][item["signal_id"]]["review_points"] == {"T+3": {"sentinel": "keep"}}
    assert tracker["signals"][item["signal_id"]]["execution_model"] == "EXECUTION_MODEL_DAILY_OHLC_T1_V1"
