import copy
import json

import pytest

import live_acquisition as live
import track_perf as tracker
from data_paths import DataPaths
from test_watchlist_schema import payload
from test_watchlist_schema import candidate


def test_holiday_recovery_uses_existing_roster_policy_only_for_september_30(monkeypatch):
    monkeypatch.setenv("ASHARE_CLOSE_REPORT_RECOVERY_DATE", "2026-09-30")
    row = {"ticker": "600519", "thscode": "600519.SH", "exchange": "SH",
           "asset_type": "a-share", "name": "贵州茅台", "list_date": None}
    universe, _, quality = live._build_universe([row], "2026-09-30", "2026-10-01T17:00:00+08:00")
    assert universe.symbols == ("600519",)
    assert quality["list_date_eligibility"]["eligibility_mode"] == live.UNIVERSE_ELIGIBILITY_MODE_CLOSE_REPORT_RECOVERY
    live._validate_universe_quality(quality, "2026-09-30")
    for target, observed in [("2026-09-29", "2026-10-01T17:00:00+08:00"),
                             ("2026-09-30", "2026-10-08T17:00:00+08:00")]:
        with pytest.raises(live.LiveAcquisitionError):
            live.close_report_recovery_enabled(target, observed)
    monkeypatch.delenv("ASHARE_CLOSE_REPORT_RECOVERY_DATE")
    assert live._hithink_universe_eligibility_mode("2026-09-30", "2026-10-01T17:00:00+08:00") == live.UNIVERSE_ELIGIBILITY_MODE_LIST_DATE_HISTORICAL


def test_initialization_preserves_old_signals_and_leaves_future_reviews_pending(monkeypatch, tmp_path):
    paths = DataPaths(tmp_path)
    for day in ("2026-09-29", "2026-09-30"):
        paths.watchlist_file(day).write_text(json.dumps(payload(date=day, strategy_version=tracker.CURRENT_PROSPECTIVE_STRATEGY)), encoding="utf-8")
    before = tracker.new_tracker()
    old_list = paths.watchlist_file("2026-09-30")
    saved = old_list.read_bytes()
    old_list.unlink()
    tracker.ingest(before, paths=paths)
    old_signals = copy.deepcopy(before["signals"])
    old_list.write_bytes(saved)
    monkeypatch.setattr(tracker, "PATHS", paths)
    monkeypatch.setattr(tracker, "TRACK_FILE", tmp_path / "perf_tracker.json")
    monkeypatch.setattr(tracker, "REPORT_FILE", tmp_path / "review.md")
    tracker.save_tracker(before)
    monkeypatch.setattr(tracker, "run_daily_review", lambda *a, **k: pytest.fail("recovery must not fetch or update observations"))
    monkeypatch.setattr(tracker, "load_strategy_rule_historical_ohlc", lambda *a, **k: ({}, {}))
    assert tracker.main(["all", "--date", "2026-09-30", "--initialize-close-20260930"]) == 0
    after = tracker.load_tracker()
    assert all(after["signals"][key] == value for key, value in old_signals.items())
    fresh = next(s for s in after["signals"].values() if s["date"] == "2026-09-30")
    assert fresh["status"] == "pending"
    assert fresh["observations"] == []
    assert fresh["entry_price"] is None
    assert all(p["status"] == tracker.REVIEW_POINT_PENDING and p["return_pct"] is None
               and p["quote_date"] is None for p in fresh["review_points"].values())
    assert tracker.main(["all", "--date", "2026-10-01", "--initialize-close-20260930"]) == 2


def test_report_restores_volume_and_yesterday_ohlc_without_durable_observations(monkeypatch, tmp_path):
    from datetime import date, timedelta
    import render_daily_close_html as renderer
    from test_volume_observation import _bars
    paths = DataPaths(tmp_path)
    previous = candidate(code='000001')
    current = candidate(price=10.0, trigger=9.9, stop=9.0, target=11.0)
    for day, row in [('2026-09-29', previous), ('2026-09-30', current)]:
        paths.watchlist_file(day).write_text(json.dumps(payload(
            date=day, candidates=[row], strategy_version=tracker.CURRENT_PROSPECTIVE_STRATEGY)), encoding='utf-8')
    state = tracker.new_tracker()
    tracker.ingest(state, paths=paths)
    tracker.save_tracker(state, paths.perf_tracker_file())
    original_bytes = paths.perf_tracker_file().read_bytes()
    old_bars = [{'date':'2026-09-29', 'open':118.0, 'high':120.0, 'low':117.0, 'close':119.0, 'volume':100},
                {'date':'2026-09-30', 'open':119.0, 'high':124.0, 'low':118.0, 'close':122.0, 'volume':110}]
    monkeypatch.setattr(renderer, 'load_strategy_rule_historical_ohlc', lambda *a, **k: ({'000001':old_bars}, {}))
    volume_bars = _bars()
    shift = date(2026,9,30) - date.fromisoformat(volume_bars[-1]['date'])
    for bar in volume_bars:
        bar['date'] = (date.fromisoformat(bar['date']) + shift).isoformat()
    monkeypatch.setattr(live, '_load_captured_market_bars', lambda *a, **k: (volume_bars, {}))
    model = renderer.build_report_model('2026-09-30', paths=paths, recover_close_20260930=True)
    observation = model.watchlist_rows[0]['volume_observation']
    assert observation['down_volume_share'] == pytest.approx(110 / 240)
    assert observation['up_down_volume_ratio'] == pytest.approx(50 / (110 / 3))
    row = model.previous_signals[0]
    assert row['today_close'] == 122.0 and row['today_high'] == 124.0
    assert row['raw_status'] == 'triggered' and row['new_triggered']
    assert row['observation_status'] == '历史行情恢复'
    assert row['observation_source'] == '9/30 历史行情恢复（非前瞻）'
    assert paths.perf_tracker_file().read_bytes() == original_bytes
    assert not list(paths.root.glob('volume_observations/*.json'))
    normal = renderer.build_report_model('2026-09-30', paths=paths)
    assert normal.previous_signals[0]['today_close'] is None
    assert normal.watchlist_rows[0]['volume_observation'] == {}
    with pytest.raises(ValueError, match='limited to 2026-09-30'):
        renderer.build_report_model('2026-10-01', paths=paths, recover_close_20260930=True)
