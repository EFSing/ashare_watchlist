from __future__ import annotations

import copy

from b_volume_confirm_focus import build_t1_giveback_diagnostic
from track_perf import build_strategy_rule_performance, stable_signal_id
from trading_calendar import TradingCalendar


CALENDAR = TradingCalendar(holidays=set())
STRATEGY = "B_BREAKOUT_RETEST_LEGACY_V1_1"
SETUP = "B_BREAKOUT_RETEST"


def candidate(code: str = "300546", *, trigger: float = 18.14, stop: float = 17.64, target: float = 20.19) -> dict[str, object]:
    return {
        "code": code,
        "name": "雄帝科技" if code == "300546" else f"测试{code}",
        "buy_type": "B 突破回踩",
        "score": 45,
        "price": trigger,
        "trigger": trigger,
        "stop": stop,
        "target": target,
        "rr": (target - trigger) / (trigger - stop),
        "setup": SETUP,
        "vol_ratio": 0.91,
    }


def watchlist(item: dict[str, object], signal_date: str = "2026-09-03") -> dict[str, object]:
    return {
        "date": signal_date,
        "mode": "close",
        "market_env": {},
        "sectors": [],
        "strategy_version": STRATEGY,
        "candidates": [item],
    }


def bar(day: str, *, opening: float, high: float, low: float, close: float) -> dict[str, object]:
    return {"date": day, "open": opening, "high": high, "low": low, "close": close}


def evaluate(item: dict[str, object], bars: list[dict[str, object]], as_of: str = "2026-09-08"):
    return build_strategy_rule_performance(
        [watchlist(item)],
        {str(item["code"]): bars},
        as_of,
        calendar=CALENDAR,
    )


def test_entry_day_target_touch_then_later_stop_is_classified_separately_from_fast_stop():
    item = candidate()
    history = {
        "300546": [
            bar("2026-09-04", opening=18.99, high=20.55, low=18.63, close=18.79),
            bar("2026-09-07", opening=18.50, high=18.67, low=17.95, close=17.99),
            bar("2026-09-08", opening=17.86, high=18.30, low=17.62, close=17.91),
        ]
    }
    performance = evaluate(item, history["300546"])

    before = copy.deepcopy(performance)
    diagnostic = build_t1_giveback_diagnostic(
        [watchlist(item)],
        history,
        "2026-09-08",
        performance=performance,
        calendar=CALENDAR,
    )

    assert diagnostic["stop_count"] == 1
    assert diagnostic["entry_day_target_touched_then_stop_count"] == 1
    assert diagnostic["entry_day_target_touched_then_stop_rate_pct"] == 100.0
    assert diagnostic["fast_stop_count"] == 1
    assert diagnostic["fast_stop_and_entry_day_target_touched_count"] == 1
    assert diagnostic["categories_are_distinct"] is True
    assert performance == before


def test_sellable_day_target_is_not_mislabeled_as_entry_day_target_then_stop():
    item = candidate("600001")
    history = [
        bar("2026-09-04", opening=18.14, high=18.50, low=18.00, close=18.30),
        bar("2026-09-07", opening=18.20, high=20.30, low=18.10, close=20.00),
    ]
    performance = evaluate(item, history)
    diagnostic = build_t1_giveback_diagnostic(
        [watchlist(item)],
        {"600001": history},
        "2026-09-07",
        performance=performance,
        calendar=CALENDAR,
    )

    assert performance["resolved_target"] == 1
    assert diagnostic["stop_count"] == 0
    assert diagnostic["entry_day_target_touched_then_stop_count"] == 0


def test_entry_day_target_not_touched_remains_false_for_later_stop():
    item = candidate("600002")
    history = [
        bar("2026-09-04", opening=18.14, high=18.50, low=18.00, close=18.30),
        bar("2026-09-07", opening=17.70, high=18.00, low=17.60, close=17.80),
    ]
    performance = evaluate(item, history)
    diagnostic = build_t1_giveback_diagnostic(
        [watchlist(item)],
        {"600002": history},
        "2026-09-07",
        performance=performance,
        calendar=CALENDAR,
    )

    assert diagnostic["stop_count"] == 1
    assert diagnostic["entry_day_target_touched_then_stop_count"] == 0
    assert diagnostic["rows"][0]["entry_day_target_touched"] is False


def test_300546_fixture_confirms_real_entry_day_ohlc_and_formal_stop():
    item = candidate()
    history = {
        "300546": [
            bar("2026-09-04", opening=18.99, high=20.55, low=18.63, close=18.79),
            bar("2026-09-07", opening=18.50, high=18.67, low=17.95, close=17.99),
            bar("2026-09-08", opening=17.86, high=18.30, low=17.62, close=17.91),
        ]
    }
    performance = evaluate(item, history["300546"])
    diagnostic = build_t1_giveback_diagnostic(
        [watchlist(item)],
        history,
        "2026-09-08",
        performance=performance,
        calendar=CALENDAR,
    )

    row = diagnostic["300546_verification"]
    assert row["status"] == "CLOSED"
    assert row["entry_day_ohlc"] == {"open": 18.99, "high": 20.55, "low": 18.63, "close": 18.79}
    assert row["entry_day_target_touched"] is True
    assert row["formal_exit_type"] == "STOP"
    assert row["formal_exit_date"] == "2026-09-08"
    assert row["final_return_pct"] == -2.75634
    assert row["total_mfe_pct"] == 13.285557
