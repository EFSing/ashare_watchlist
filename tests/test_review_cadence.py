import json
from datetime import date

from data_paths import DataPaths
from test_watchlist_schema import payload
from track_perf import (
    REVIEW_POINT_CAPTURED,
    REVIEW_POINT_NOT_CAPTURED,
    REVIEW_POINT_PENDING,
    ingest,
    new_tracker,
    report,
    update,
)
from trading_calendar import TradingCalendar


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
    calendar = TradingCalendar(holidays={date(2026, 8, 24)})
    tracker = make_tracker(tmp_path, "2026-08-21", calendar)

    signal = next(iter(tracker["signals"].values()))
    points = signal["review_points"]
    assert points["T+3"]["scheduled_date"] == "2026-08-27"
    assert points["T+5"]["scheduled_date"] == "2026-08-31"
    assert points["T+10"]["scheduled_date"] == "2026-09-07"


def test_early_target_keeps_terminal_status_and_captures_later_fixed_point(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 8, 24)})
    tracker = make_tracker(tmp_path, "2026-08-21", calendar)

    update(
        tracker,
        quotes={"600519": quote("2026-08-25", price=121.0, high=125.0, low=119.0)},
        today="2026-08-25",
        calendar=calendar,
    )
    update(
        tracker,
        quotes={"600519": quote("2026-08-26", price=130.0, high=130.0, low=121.0)},
        today="2026-08-26",
        calendar=calendar,
    )
    update(
        tracker,
        quotes={"600519": quote("2026-08-27", price=127.0, high=128.0, low=126.0)},
        today="2026-08-27",
        calendar=calendar,
    )

    signal = next(iter(tracker["signals"].values()))
    assert signal["status"] == "win"
    assert signal["close_date"] == "2026-08-26"
    assert signal["days_tracked"] == 2
    assert signal["review_points"]["T+3"]["status"] == REVIEW_POINT_CAPTURED
    assert signal["review_points"]["T+3"]["signal_status"] == "win"
    assert signal["review_points"]["T+3"]["quote_date"] == "2026-08-27"
    assert signal["review_points"]["T+5"]["status"] == REVIEW_POINT_PENDING


def test_missed_fixed_point_is_explicit_and_never_backfilled(tmp_path):
    calendar = TradingCalendar(holidays={date(2026, 8, 24)})
    tracker = make_tracker(tmp_path, "2026-08-21", calendar)

    update(
        tracker,
        quotes={"600519": quote("2026-08-28", price=121.0, high=125.0, low=119.0)},
        today="2026-08-28",
        calendar=calendar,
    )
    signal = next(iter(tracker["signals"].values()))
    point = signal["review_points"]["T+3"]
    assert point["status"] == REVIEW_POINT_NOT_CAPTURED
    assert point["quote_date"] is None
    assert "historical backfill" in point["reason"]


def test_report_exposes_formal_nodes_without_legacy_claims(tmp_path):
    calendar = TradingCalendar(holidays=set())
    tracker = make_tracker(tmp_path, "2026-08-20", calendar)

    text = report(tracker, calendar=calendar)

    assert "T+3" in text
    assert "T+5" in text
    assert "T+10" in text
    assert "配对指标" not in text
    assert "持仓" not in text
    assert "体系可盈利" not in text
