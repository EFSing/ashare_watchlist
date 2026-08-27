import json

from data_paths import DataPaths
from test_watchlist_schema import payload
from track_perf import ingest, new_tracker


def test_same_symbol_on_different_signal_dates_is_tracked_independently(tmp_path):
    paths = DataPaths(tmp_path)
    for date in ("2026-08-20", "2026-08-21"):
        data = payload(date=date)
        paths.watchlist_file(date).write_text(json.dumps(data), encoding="utf-8")

    tracker = new_tracker()
    assert ingest(tracker, paths=paths) == 2
    signals = tracker["signals"]

    assert len(signals) == 2
    assert {signal["code"] for signal in signals.values()} == {"600519"}
    assert {signal["date"] for signal in signals.values()} == {"2026-08-20", "2026-08-21"}
    assert all(signal["signal_id"] for signal in signals.values())

