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
    from datetime import date
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


def _report_signal(day, **overrides):
    from watchlist_schema import validate_watchlist
    watch = validate_watchlist(payload(date=day, candidates=[candidate(**overrides)],
                                      strategy_version=tracker.CURRENT_PROSPECTIVE_STRATEGY))
    signal = tracker._signal_from_candidate(watch, watch['candidates'][0], tracker.default_calendar())
    return watch, signal


def _session_bars(start, end, close=122.0):
    from datetime import date, timedelta
    calendar = tracker.default_calendar()
    result = []
    day = date.fromisoformat(start)
    while day <= date.fromisoformat(end):
        if calendar.is_trading_day(day):
            result.append({'date':day.isoformat(), 'open':120.0, 'high':125.0, 'low':119.0,
                           'close':close, 'volume':100.0})
        day += timedelta(days=1)
    return result


def test_each_matured_horizon_uses_its_own_session_price_and_keeps_source_unchanged():
    import render_daily_close_html as renderer
    watch, signal = _report_signal('2026-09-03', price=119.0)
    original = {'version':2, 'signals':{signal['signal_id']:signal}, 'updated':None, 'review_coverage':None}
    frozen = copy.deepcopy(original)
    bars = _session_bars('2026-09-03', '2026-09-30')
    prices = {'2026-09-03':119.0, '2026-09-08':121.0, '2026-09-10':122.0,
              '2026-09-17':123.0, '2026-09-30':124.0}
    for bar in bars:
        bar['close'] = prices.get(bar['date'], 122.0)
    view, _, _ = renderer._historical_report_view(original, [watch], {'600519':bars},
                                                 '2026-09-30', tracker.default_calendar())
    points = view['signals'][signal['signal_id']]['review_points']
    for label, day, price in [('T+3','2026-09-08',121), ('T+5','2026-09-10',122), ('T+10','2026-09-17',123)]:
        assert points[label]['quote_date'] == day
        assert points[label]['price'] == price
        assert points[label]['entry_basis_price'] == 120
        assert points[label]['return_pct'] == pytest.approx((price / 120 - 1) * 100, abs=1e-6)
    assert original == frozen


def test_later_entry_does_not_create_an_earlier_return_or_future_t10_result():
    import render_daily_close_html as renderer
    watch, signal = _report_signal('2026-09-16', price=119.0)
    original = {'version':2, 'signals':{signal['signal_id']:signal}, 'updated':None, 'review_coverage':None}
    bars = _session_bars('2026-09-16', '2026-09-30')
    for bar in bars:
        if bar['date'] < '2026-09-23':
            bar.update(open=119.0, high=119.5, low=118.0, close=119.0)
        else:
            bar.update(open=121.0, high=124.0, low=120.0, close=122.0)
    view, _, _ = renderer._historical_report_view(original, [watch], {'600519':bars},
                                                 '2026-09-30', tracker.default_calendar())
    points = view['signals'][signal['signal_id']]['review_points']
    assert points['T+3']['quote_date'] == '2026-09-21'
    assert points['T+3']['return_pct'] is None and points['T+3']['entry_basis_price'] is None
    assert points['T+5']['entry_basis_date'] == '2026-09-23'
    assert points['T+5']['entry_basis_price'] == 121.0
    assert points['T+5']['return_pct'] == pytest.approx((122 / 121 - 1) * 100, abs=1e-6)
    assert points['T+10']['scheduled_date'] == '2026-10-08'
    assert points['T+10']['status'] == tracker.REVIEW_POINT_PENDING
    assert points['T+10']['price'] is None and points['T+10']['return_pct'] is None


def test_restated_qfq_is_replaced_only_by_raw_prices_matching_original_records():
    import render_daily_close_html as renderer
    watch, signal = _report_signal('2026-09-16', price=119.0)
    raw = _session_bars('2026-09-16', '2026-09-30')
    raw[0].update(open=118.0, high=120.0, low=117.0, close=119.0)
    first = raw[1]
    signal['observations'] = [{'date':first['date'], 'open':first['open'], 'high':first['high'],
                               'low':first['low'], 'price':first['close']}]
    original = {'version':2, 'signals':{signal['signal_id']:signal}, 'updated':None, 'review_coverage':None}
    restated = copy.deepcopy(raw)
    for bar in restated:
        if bar['date'] < '2026-09-30':
            for field in ('open','high','low','close'):
                bar[field] -= 1.0
    view, merged, conflicts = renderer._historical_report_view(original, [watch], {'600519':restated},
        '2026-09-30', tracker.default_calendar(), raw_history={'600519':raw})
    assert conflicts == ['600519']
    assert view['signals'][signal['signal_id']]['entry_price'] == 120.0
    assert merged['600519'][0]['close'] == 119.0
    incompatible = copy.deepcopy(raw)
    incompatible[0]['close'] = 118.0
    _, unsafe, _ = renderer._historical_report_view(original, [watch], {'600519':restated},
        '2026-09-30', tracker.default_calendar(), raw_history={'600519':incompatible})
    assert {b['date'] for b in unsafe['600519']} == {first['date'], '2026-09-30'}


def test_horizon_panel_counts_restored_prices_and_does_not_average_untriggered_rows():
    import render_daily_close_html as renderer
    rows = [{'source_mode':renderer._HISTORICAL_REPORT_SOURCE, 'snapshot_status':'历史节点已恢复',
             'node_close':12, 'horizon_return_value':10, 'path_status_code':'triggered'},
            {'source_mode':renderer._HISTORICAL_REPORT_SOURCE, 'snapshot_status':'历史节点已恢复',
             'node_close':9, 'horizon_return_value':None, 'path_status_code':'pending',
             'return_reason':'节点时尚未触发'}]
    text = renderer._research_panel('T+3', '短期观察', rows)
    assert '2 历史已恢复' in text
    assert '+10.00%' in text and '+5.00%' not in text
    assert '未触发，无入场收益' in text
    assert '下一批到期：2026-10-08' in renderer._research_panel('T+10', '延伸观察', [], '2026-10-08')
