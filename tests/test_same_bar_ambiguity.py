from data_paths import DataPaths
from test_watchlist_schema import payload
from track_perf import classify_signal_bar, ingest, new_tracker, update
from trading_calendar import TradingCalendar
import json


def test_trigger_stop_target_on_same_bar_is_ambiguous_and_explains_why():
    result = classify_signal_bar(
        status="pending",
        trigger=100.0,
        stop=95.0,
        target=110.0,
        high=112.0,
        low=94.0,
    )

    assert result["status"] == "AMBIGUOUS_SAME_BAR"
    assert "trigger" in result["reason"]
    assert "stop" in result["reason"]
    assert "target" in result["reason"]


def test_tracker_persists_ambiguous_status_instead_of_counting_a_loss(tmp_path):
    paths = DataPaths(tmp_path)
    paths.watchlist_file("2026-08-20").write_text(json.dumps(payload()), encoding="utf-8")
    tracker = new_tracker()
    assert ingest(tracker, paths=paths) == 1

    quote = {
        "code": "600519",
        "quote_date": "2026-08-21",
        "price": 100.0,
        "prev_close": 100.0,
        "open": 100.0,
        "chg_pct": 0.0,
        "high": 132.0,
        "low": 114.0,
        "turnover": 4.0,
        "vol_ratio": 1.0,
    }
    update(
        tracker,
        quotes={"600519": quote},
        today="2026-08-21",
        calendar=TradingCalendar(holidays=set()),
    )

    signal = next(iter(tracker["signals"].values()))
    assert signal["status"] == "AMBIGUOUS_SAME_BAR"
    assert signal["result_price"] is None
