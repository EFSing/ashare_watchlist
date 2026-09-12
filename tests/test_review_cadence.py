import json
from copy import deepcopy
from datetime import date, timedelta

import pytest

from data_paths import DataPaths
from test_watchlist_schema import payload as schema_payload


def payload(**overrides):
    return schema_payload(**{"date": "2026-09-03", "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1", **overrides})
from track_perf import (
    PRIMARY_REVIEW_HORIZON,
    REVIEW_POINT_CAPTURED,
    REVIEW_POINT_NOT_CAPTURED,
    REVIEW_POINT_PENDING,
    ingest,
    new_tracker,
    report,
    review_snapshot_id,
    update,
)
from trading_calendar import CalendarUnavailable, TradingCalendar


def quote(quote_date: str, *, price: float, high: float, low: float) -> dict[str, object]:
    return {
        "code": "600519",
        "name": "贵州茅台",
        "quote_date": quote_date,
        "price": price,
        "prev_close": 120.0,
        "open": price,
        "chg_pct": 0.0,
        "high": high,
        "low": low,
        "turnover": 4.0,
        "vol_ratio": 1.0,
    }


def make_tracker(tmp_path, signal_date: str, calendar: TradingCalendar) -> dict[str, object]:
    paths = DataPaths(tmp_path)
    paths.watchlist_file(signal_date).write_text(
        json.dumps(payload(date=signal_date)),
        encoding="utf-8",
    )
    tracker = new_tracker()
    assert ingest(tracker, paths=paths, calendar=calendar) == 1
    return tracker


def test_review_points_use_xshg_sessions_not_calendar_days(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 9, 7)})
    tracker = make_tracker(tmp_path, "2026-09-04", calendar)

    signal = next(iter(tracker["signals"].values()))
    points = signal["review_points"]
    assert points["T+3"]["scheduled_date"] == "2026-09-10"
    assert points["T+5"]["scheduled_date"] == "2026-09-14"
    assert points["T+10"]["scheduled_date"] == "2026-09-21"
    assert PRIMARY_REVIEW_HORIZON == "T+5"
    point = points["T+5"]
    assert point["signal_id"] == signal["signal_id"]
    assert point["signal_date"] == "2026-09-04"
    assert point["horizon"] == "T+5"
    assert point["review_trading_date"] == "2026-09-14"
    assert point["snapshot_id"] == review_snapshot_id(signal["signal_id"], "T+5", "2026-09-14")


def test_early_target_keeps_terminal_status_and_captures_later_fixed_point(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 9, 7)})
    tracker = make_tracker(tmp_path, "2026-09-04", calendar)

    update(
        tracker,
        quotes={"600519": quote("2026-09-08", price=121.0, high=125.0, low=119.0)},
        today="2026-09-08",
        calendar=calendar,
    )
    update(
        tracker,
        quotes={"600519": quote("2026-09-09", price=130.0, high=130.0, low=121.0)},
        today="2026-09-09",
        calendar=calendar,
    )
    update(
        tracker,
        quotes={"600519": quote("2026-09-10", price=127.0, high=128.0, low=126.0)},
        today="2026-09-10",
        calendar=calendar,
    )

    signal = next(iter(tracker["signals"].values()))
    assert signal["status"] == "win"
    assert signal["close_date"] == "2026-09-09"
    assert signal["entry_date"] == "2026-09-08"
    assert signal["entry_price"] == 121.0
    assert signal["sellable_from"] == "2026-09-09"
    assert signal["exit_reason"] == "TARGET_GAP"
    assert signal["exit_price"] == 130.0
    assert signal["days_tracked"] == 2
    assert signal["review_points"]["T+3"]["status"] == REVIEW_POINT_CAPTURED
    assert signal["review_points"]["T+3"]["signal_status"] == "win"
    assert signal["review_points"]["T+3"]["path_status"] == "win"
    assert signal["review_points"]["T+3"]["quote_date"] == "2026-09-10"
    assert signal["review_points"]["T+3"]["return_pct"] == 4.958678
    assert signal["review_points"]["T+5"]["status"] == REVIEW_POINT_PENDING


def test_early_stop_path_is_not_overwritten_by_later_fixed_horizon_return(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 9, 7)})
    tracker = make_tracker(tmp_path, "2026-09-04", calendar)

    update(
        tracker,
        quotes={"600519": quote("2026-09-08", price=119.0, high=121.0, low=116.0)},
        today="2026-09-08",
        calendar=calendar,
    )
    update(
        tracker,
        quotes={"600519": quote("2026-09-09", price=114.0, high=119.0, low=114.0)},
        today="2026-09-09",
        calendar=calendar,
    )
    update(
        tracker,
        quotes={"600519": quote("2026-09-10", price=117.0, high=118.0, low=116.0)},
        today="2026-09-10",
        calendar=calendar,
    )

    signal = next(iter(tracker["signals"].values()))
    assert signal["status"] == "loss"
    assert signal["close_date"] == "2026-09-09"
    assert signal["result_price"] == 114.0
    assert signal["exit_reason"] == "STOP_GAP"
    assert signal["exit_price"] == 114.0
    assert signal["review_points"]["T+3"]["path_status"] == "loss"
    assert signal["review_points"]["T+3"]["return_pct"] == -2.5
    assert signal["review_points"]["T+3"]["quote_date"] == "2026-09-10"


def test_ten_session_point_closes_untriggered_signal_and_marks_missed_nodes(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 9, 7)})
    tracker = make_tracker(tmp_path, "2026-09-04", calendar)

    current = date(2026, 9, 8)
    while current <= date(2026, 9, 21):
        if calendar.is_trading_day(current):
            update(
                tracker,
                quotes={"600519": quote(current.isoformat(), price=118.0, high=119.0, low=117.0)},
                today=current,
                calendar=calendar,
            )
        current += timedelta(days=1)

    signal = next(iter(tracker["signals"].values()))
    assert signal["status"] == "expired"
    assert signal["days_tracked"] == 10
    assert signal["exit_reason"] == "EXPIRED_UNTRIGGERED"
    assert signal["exit_date"] == "2026-09-21"
    assert signal["exit_price"] is None
    assert signal["realized_return_pct"] is None
    assert signal["review_points"]["T+3"]["status"] == REVIEW_POINT_CAPTURED
    assert signal["review_points"]["T+5"]["status"] == REVIEW_POINT_CAPTURED
    assert signal["review_points"]["T+10"]["status"] == REVIEW_POINT_CAPTURED
    assert signal["review_points"]["T+10"]["path_status"] == "expired"
    assert signal["review_points"]["T+10"]["return_pct"] is None
    assert "unverified" in signal["review_points"]["T+10"]["reason"]


def test_same_snapshot_update_is_idempotent(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 9, 7)})
    tracker = make_tracker(tmp_path, "2026-09-04", calendar)
    fixed_quote = {"600519": quote("2026-09-10", price=118.0, high=119.0, low=117.0)}

    assert update(tracker, quotes=fixed_quote, today="2026-09-10", calendar=calendar) > 0
    before = deepcopy(next(iter(tracker["signals"].values()))["review_points"])
    assert update(tracker, quotes=fixed_quote, today="2026-09-10", calendar=calendar) == 0
    after = next(iter(tracker["signals"].values()))["review_points"]

    assert after == before
    assert after["T+3"]["snapshot_id"] == before["T+3"]["snapshot_id"]


def test_update_rejects_non_trading_session_instead_of_using_natural_days(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 9, 7)})
    tracker = make_tracker(tmp_path, "2026-09-04", calendar)

    with pytest.raises(CalendarUnavailable):
        update(
            tracker,
            quotes={"600519": quote("2026-09-07", price=118.0, high=119.0, low=117.0)},
            today="2026-09-07",
            calendar=calendar,
        )


def test_missed_fixed_point_is_explicit_and_never_backfilled(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 9, 7)})
    tracker = make_tracker(tmp_path, "2026-09-04", calendar)

    update(
        tracker,
        quotes={"600519": quote("2026-09-11", price=121.0, high=125.0, low=119.0)},
        today="2026-09-11",
        calendar=calendar,
    )
    signal = next(iter(tracker["signals"].values()))
    point = signal["review_points"]["T+3"]
    assert point["status"] == REVIEW_POINT_NOT_CAPTURED
    assert point["quote_date"] is None
    assert "historical backfill" in point["reason"]


def test_report_exposes_formal_nodes_without_legacy_claims(tmp_path):
    calendar = TradingCalendar(holidays=set())
    tracker = make_tracker(tmp_path, "2026-09-03", calendar)

    text = report(tracker, calendar=calendar)

    assert "T+3" in text
    assert "T+5" in text
    assert "T+10" in text
    assert "PRIMARY REVIEW HORIZON" in text
    assert "延伸观察并结案" in text
    assert "MISSING_HISTORICAL_OBSERVATION" in report(tracker, calendar=calendar, as_of="2026-09-11")
    assert "交易绩效" in text
    assert "当前持仓" in text
