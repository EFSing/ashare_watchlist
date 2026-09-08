import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

import render_daily_close_html as renderer
import track_perf as perf
from data_paths import DataPaths
from test_daily_close_html import _candidate, _write_watchlist
from test_review_cadence import quote
from trading_calendar import TradingCalendar
from watchlist_schema import load_watchlist


CAL = TradingCalendar(holidays=set())


def write_list(root, token, count=1, strategy=perf.CURRENT_PROSPECTIVE_STRATEGY):
    _write_watchlist(root, token, [_candidate(f'{600000+i:06d}', f'Signal {i}', 60+i) for i in range(count)])
    path = root / 'data' / f'watchlist_{token}.json'
    raw = json.loads(path.read_text(encoding='utf-8'))
    raw['strategy_version'] = strategy
    path.write_text(json.dumps(raw), encoding='utf-8')
    return load_watchlist(path)


def save(root, tracker):
    perf.save_tracker(tracker, root / 'data/perf_tracker.json')


def test_epoch_ingest_and_deterministic_cleanup_preserve_originals(tmp_path):
    old = write_list(tmp_path, '20260820', strategy='legacy-v1')
    wrong = write_list(tmp_path, '20260904', strategy='other-project')
    for token, count in [('20260903', 11), ('20260907', 25), ('20260908', 34)]:
        write_list(tmp_path, token, count)
    paths = DataPaths(tmp_path / 'data')
    originals = {p: p.read_bytes() for p in paths.watchlist_files()}
    tracker = perf.new_tracker()
    for watchlist in (old, wrong):
        signal = perf._signal_from_candidate(watchlist, watchlist['candidates'][0], CAL)
        tracker['signals'][signal['signal_id']] = signal
    with pytest.warns(RuntimeWarning, match=perf.SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST):
        assert perf.ingest(tracker, paths, CAL) == 70
    kept = {k: deepcopy(v) for k, v in tracker['signals'].items() if perf.is_current_prospective_signal(v)}
    before = deepcopy(tracker)
    plan = perf.current_tracker_cleanup_plan(tracker, paths)
    assert tracker == before
    assert plan == perf.current_tracker_cleanup_plan(tracker, paths)
    assert len(plan['KEEP']) == 70 and len(plan['REMOVE_FROM_CURRENT_TRACKER']) == 2
    assert perf.cleanup_current_tracker(tracker, paths) == plan
    assert tracker['signals'] == kept
    assert originals == {p: p.read_bytes() for p in originals}
    assert all(not s['observations'] for s in tracker['signals'].values())
    assert {d: sum(s['date'] == d for s in tracker['signals'].values()) for d in
            ('2026-09-03', '2026-09-07', '2026-09-08')} == {
                '2026-09-03': 11, '2026-09-07': 25, '2026-09-08': 34}
    assert perf.ingest(tracker, paths, CAL) == 0


def test_report_uses_yesterday_canonical_and_rejects_legacy(tmp_path):
    old = write_list(tmp_path, '20260820', strategy='legacy-v1')
    write_list(tmp_path, '20260903', 11)
    previous = write_list(tmp_path, '20260907', 25)
    write_list(tmp_path, '20260908', 34)
    paths = DataPaths(tmp_path / 'data')
    tracker = perf.new_tracker()
    perf.ingest(tracker, paths, CAL)
    legacy = perf._signal_from_candidate(old, old['candidates'][0], CAL)
    legacy.update(status='expired', close_date='2026-09-08', observations=[{
        'date': '2026-09-08', 'price': 88, 'high': 99, 'low': 77}])
    tracker['signals'][legacy['signal_id']] = legacy
    save(tmp_path, tracker)
    model, dated, latest = renderer.render_daily_close('20260908', paths=paths, calendar=CAL)
    assert {r['signal_id'] for r in model.previous_signals} == {c['signal_id'] for c in previous['candidates']}
    assert len(model.previous_signals) == 25 and len(model.active_signals) == 11
    assert all(r['list_date'] == '2026-09-07' for r in model.previous_signals)
    assert all(r['list_date'] == '2026-09-03' for r in model.active_signals)
    for rows in [model.previous_signals, model.active_signals, model.closed_today, *model.review_sections.values()]:
        assert len(rows) == len({r['signal_id'] for r in rows})
    assert len(model.review_sections['T+3']) == 11
    assert all(r['snapshot_status'] == renderer._MISSING for r in model.review_sections['T+3'])
    assert all(r['path_status'] == renderer._MISSING for r in model.previous_signals)
    assert all(r['today_open'] is None and r['today_high'] is None and r['today_close'] is None
               and r['close_vs_trigger_pct'] is None for r in model.previous_signals)
    text = latest.read_text(encoding='utf-8')
    assert all(text.count(renderer._esc(r['signal_id'])) == 1 for r in
               model.watchlist_rows + model.previous_signals + model.active_signals)
    assert '2026-08-20' not in text and legacy['signal_id'] not in text
    assert '数据缺失' in text and '收盘较 Trigger %' in text
    assert dated.read_bytes() == latest.read_bytes()
    assert all(not s['observations'] for s in tracker['signals'].values() if s is not legacy)


@pytest.mark.parametrize('conflict', ['different_id', 'same_id_under_alias', 'canonical_mismatch'])
def test_identity_conflicts_fail_closed_before_mutation(tmp_path, conflict):
    write_list(tmp_path, '20260907')
    paths = DataPaths(tmp_path / 'data')
    tracker = perf.new_tracker()
    perf.ingest(tracker, paths, CAL)
    key = next(iter(tracker['signals']))
    if conflict == 'canonical_mismatch':
        tracker['signals'][key]['trigger'] += 1
        marker = 'CURRENT_PROSPECTIVE_TRACKER_IDENTITY_MISMATCH'
    else:
        row = deepcopy(tracker['signals'][key])
        if conflict == 'different_id':
            row['signal_id'] = 'alternate-id'
        tracker['signals']['alternate-id'] = row
        marker = 'TRACKER_IDENTITY_CONFLICT'
    before = deepcopy(tracker)
    for action in (perf.ingest, perf.cleanup_current_tracker):
        with pytest.raises(perf.TrackerSchemaError, match=marker):
            action(tracker, paths)
        assert tracker == before
    (tmp_path / 'data/perf_tracker.json').write_text(json.dumps(tracker), encoding='utf-8')
    write_list(tmp_path, '20260908')
    model, _, latest = renderer.render_daily_close('20260908', paths=paths, calendar=CAL)
    assert model.review_status == 'REVIEW_FAILED'
    assert len(model.watchlist_rows) == 1 and latest.exists()
    assert all(not r['observed'] for r in model.previous_signals)


def test_observation_open_is_prospective_and_t_close_is_not_execution(tmp_path):
    watchlist = write_list(tmp_path, '20260907')
    paths = DataPaths(tmp_path / 'data')
    tracker = perf.new_tracker()
    perf.ingest(tracker, paths, CAL)
    key = next(iter(tracker['signals']))
    q = quote('2026-09-07', price=11, high=11.5, low=10.5)
    q['code'] = '600000'
    assert perf.update(tracker, {'600000': q}, today='2026-09-07', calendar=CAL) == 0
    assert not tracker['signals'][key]['observations']
    q.update(quote_date='2026-09-08', open=10.6)
    perf.update(tracker, {'600000': q}, today='2026-09-08', calendar=CAL)
    obs = tracker['signals'][key]['observations'][0]
    assert obs == {'date': '2026-09-08', 'open': 10.6, 'high': 11.5, 'low': 10.5, 'price': 11}
    save(tmp_path, tracker)
    write_list(tmp_path, '20260908')
    model = renderer.build_report_model('20260908', paths=paths, calendar=CAL)
    assert model.previous_signals[0]['today_open'] == 10.6
    assert model.previous_signals[0]['close_vs_trigger_pct'] == pytest.approx((11/10.2-1)*100)
    del obs['open']
    save(tmp_path, tracker)
    model = renderer.build_report_model('20260908', paths=paths, calendar=CAL)
    assert model.previous_signals[0]['today_open'] is None
    assert 'open' not in tracker['signals'][key]['observations'][0]


def test_exact_local_canonical_continuity_when_available():
    paths = DataPaths(Path(__file__).resolve().parents[1] / 'data')
    expected = {
        '20260903': (11, '50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085'),
        '20260907': (25, '5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100'),
        '20260908': (34, 'f58059cd5269f8ac5cd10da357a2bd008a76ef84feaa399846d74ad7daa4b5fc'),
    }
    if not all(paths.watchlist_file(d).exists() for d in expected):
        pytest.skip('exact operational canonical artifacts not present')
    for d, (count, sha) in expected.items():
        p = paths.watchlist_file(d)
        assert hashlib.sha256(p.read_bytes()).hexdigest() == sha
        assert len(load_watchlist(p)['candidates']) == count
    tracker = perf.new_tracker()
    assert perf.ingest(tracker, paths, CAL) == 70
    assert len(tracker['signals']) == 70


@pytest.mark.parametrize('field', ['first_trigger_date', 'close_date', 'observation'])
@pytest.mark.parametrize('bad_date', ['2026-09-07', '2026-09-08'])
def test_pre_t_plus_1_state_rejected(tmp_path, field, bad_date):
    write_list(tmp_path, '20260908')
    paths = DataPaths(tmp_path / 'data')
    tracker = perf.new_tracker()
    perf.ingest(tracker, paths, CAL)
    signal = next(iter(tracker['signals'].values()))
    if field == 'observation':
        signal['observations'] = [{'date': bad_date, 'price': 11, 'high': 12, 'low': 10}]
    else:
        signal[field] = bad_date
    before = deepcopy(tracker)
    with pytest.raises(perf.TrackerSchemaError, match='PRE_T_PLUS_1_STATE_VIOLATION'):
        perf.update(tracker, today='2026-09-09', calendar=CAL)
    assert tracker == before
    with pytest.raises(perf.TrackerSchemaError, match='PRE_T_PLUS_1_STATE_VIOLATION'):
        perf.save_tracker(tracker, paths.perf_tracker_file())


def test_34_same_day_noop_then_t_plus_1_fetch(tmp_path, monkeypatch):
    write_list(tmp_path, '20260908', 34)
    paths = DataPaths(tmp_path / 'data')
    tracker = perf.new_tracker()
    perf.ingest(tracker, paths, CAL)
    before = deepcopy(tracker)
    calls = []
    def fetch(codes, expected_date):
        calls.append((codes, expected_date))
        assert expected_date.isoformat() == '2026-09-09'
        result = {}
        for code in codes:
            q = quote('2026-09-09', price=11, high=11.5, low=10.5)
            q['code'] = code
            result[code] = q
        return result
    monkeypatch.setattr(perf, 'fetch_quotes', fetch)
    assert perf.update(tracker, today='2026-09-08', calendar=CAL) == 0
    assert tracker == before and calls == []
    assert perf.update(tracker, today='2026-09-09', calendar=CAL) > 0
    assert len(calls) == 1 and len(calls[0][0]) == 34
    assert all(s['status'] == 'triggered' and s['first_trigger_date'] == '2026-09-09'
               and [o['date'] for o in s['observations']] == ['2026-09-09']
               for s in tracker['signals'].values())
    perf.save_tracker(tracker, paths.perf_tracker_file())


def test_committed_908_tracker_is_pre_execution():
    paths = DataPaths(Path(__file__).resolve().parents[1] / 'data')
    tracker = perf.load_tracker(paths.perf_tracker_file())
    counts = {d: sum(s['date'] == d for s in tracker['signals'].values())
              for d in ('2026-09-03', '2026-09-07', '2026-09-08')}
    assert counts == {'2026-09-03': 11, '2026-09-07': 25, '2026-09-08': 34}
    assert len(tracker['signals']) == 70
    for signal in tracker['signals'].values():
        if signal['date'] == '2026-09-08':
            assert signal['status'] == 'pending'
            assert signal['observations'] == [] and signal['days_tracked'] == 0
            assert all(signal[k] is None for k in ('entry_price', 'result_price', 'first_trigger_date', 'close_date', 'ambiguity_reason'))
    model = renderer.build_report_model('20260908', paths=paths, calendar=CAL)
    assert len(model.watchlist_rows) == 34
    assert all(r['status'] == 'PENDING' for r in model.watchlist_rows)
    assert all(r['list_date'] < '2026-09-08' for r in model.previous_signals + model.active_signals + model.closed_today)
