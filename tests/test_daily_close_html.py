from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import render_daily_close_html as renderer
import t_close_runner
from data_paths import DataPaths
from track_perf import _signal_from_candidate, new_tracker
from trading_calendar import TradingCalendar
from watchlist_schema import load_watchlist, validate_watchlist


CALENDAR = TradingCalendar(holidays={date(2026, 9, 7)})


def _candidate(code: str, name: str, score: int, *, sector: str = "测试行业") -> dict[str, object]:
    return {
        "code": code,
        "name": name,
        "buy_type": "B 突破回踩",
        "score": score,
        "price": 10.0,
        "trigger": 10.2,
        "stop": 9.5,
        "target": 12.0,
        "rr": 2.57,
        "sector": sector,
        "setup": "B_BREAKOUT_RETEST",
    }


def _payload(list_date: str, candidates: list[dict[str, object]]) -> dict[str, object]:
    return {
        "date": f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:]}",
        "mode": "close",
        "market_env": {"grade": "A"},
        "sectors": [],
        "candidates": candidates,
        "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
    }


def _write_watchlist(root: Path, list_date: str, candidates: list[dict[str, object]]) -> dict[str, object]:
    data_root = root / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    path = data_root / f"watchlist_{list_date}.json"
    path.write_text(json.dumps(_payload(list_date, candidates), ensure_ascii=False), encoding="utf-8")
    return load_watchlist(path)


def _write_tracker(root: Path, watchlist: dict[str, object], *, calendar: TradingCalendar = CALENDAR) -> dict[str, object]:
    tracker = new_tracker()
    for candidate in watchlist["candidates"]:  # type: ignore[index]
        signal = _signal_from_candidate(watchlist, candidate, calendar)  # type: ignore[arg-type]
        tracker["signals"][signal["signal_id"]] = signal  # type: ignore[index]
    tracker_path = root / "data" / "perf_tracker.json"
    tracker_path.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding="utf-8")
    return tracker


def _paths(root: Path) -> DataPaths:
    return DataPaths(root / "data")


def test_canonical_watchlist_is_score_sorted_and_distance_is_display_only(tmp_path):
    candidates = [
        _candidate("600018", "上港集团", 31),
        _candidate("002124", "天邦食品", 70),
        _candidate("600278", "东方创业", 68),
    ]
    watchlist = _write_watchlist(tmp_path, "20260910", candidates)
    _write_tracker(tmp_path, watchlist)
    package = tmp_path / "data" / "prospective_inputs" / "20260910"
    package.mkdir(parents=True)
    package_file = package / f"2026-09-10_{'a' * 64}.json"
    package_file.write_bytes(b"package-bytes")

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)

    assert [row["code"] for row in model.watchlist_rows] == ["002124", "600278", "600018"]
    assert model.watchlist_rows[0]["name"] == "天邦食品"
    assert model.watchlist_rows[0]["distance_to_trigger_pct"] == pytest.approx(2.0)
    assert model.metadata["package_sha"] == hashlib.sha256(b"package-bytes").hexdigest()
    assert model.metadata["generation_fingerprint"] == "a" * 64
    assert model.metadata["earliest_execution"] == "2026-09-11"


def test_t_day_new_signal_is_explicitly_waiting_for_t1_not_missing(tmp_path):
    watchlist = _write_watchlist(tmp_path, "20260910", [_candidate("600018", "今日新信号", 70)])
    _write_tracker(tmp_path, watchlist)

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    row = model.watchlist_rows[0]
    quality = next(item for item in model.data_quality or [] if item["category"] == "今日新信号等待 T+1")
    text = renderer.render_html(model)

    assert row["status"] == "PENDING"
    assert row["observation_status"] == renderer._T1_PENDING
    assert row["status_explanation"] == "今日新信号，等待下一交易日观察"
    assert quality["count"] == 1 and quality["status"] == renderer._T1_PENDING
    assert "今日新信号，等待下一交易日观察" in text
    assert "历史节点或今日记录缺失" not in text


def test_historical_missing_observation_remains_unverified_and_is_not_t1(tmp_path):
    old = _write_watchlist(tmp_path, "20260903", [_candidate("600018", "历史缺口", 60)])
    tracker = _write_tracker(tmp_path, old)
    signal = next(iter(tracker["signals"].values()))
    signal["review_points"]["T+3"].update({"status": "NOT_CAPTURED", "reason": "historical node missing"})
    _write_watchlist(tmp_path, "20260910", [_candidate("600019", "今日新名单", 65)])
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    missing = next(item for item in model.data_quality or [] if item["category"] == "历史节点缺失")
    new_row = model.watchlist_rows[0]

    assert missing["count"] == 1
    assert missing["status"] == "MISSING_HISTORICAL_OBSERVATION / UNVERIFIED"
    assert new_row["observation_status"] == renderer._T1_PENDING
    assert new_row["observation_status"] != renderer._MISSING


def test_same_bar_ambiguity_is_preserved_and_sorted_first(tmp_path):
    old = _write_watchlist(tmp_path, "20260909", [
        _candidate("600018", "普通信号", 80),
        _candidate("600019", "歧义信号", 40),
    ])
    tracker = _write_tracker(tmp_path, old)
    signals = list(tracker["signals"].values())
    signals[0].update(status="triggered", observations=[{"date": "2026-09-10", "open": 10, "high": 10.2, "low": 9.9, "price": 10.1}])
    signals[1].update(
        status="AMBIGUOUS_SAME_BAR",
        observations=[{"date": "2026-09-10", "open": 10, "high": 10.5, "low": 9.5, "price": 10.0}],
        ambiguity_reason="same bar touched trigger, target",
        close_date="2026-09-10",
    )
    _write_watchlist(tmp_path, "20260910", [_candidate("600020", "今日新名单", 50)])
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    row = model.previous_signals[0]

    assert row["raw_status"] == "AMBIGUOUS_SAME_BAR"
    assert row["observation_status"] == "AMBIGUOUS_SAME_BAR"
    assert "same bar touched trigger, target" in row["status_explanation"]
    assert model.overview["ambiguous_count"] == 1


def test_report_information_architecture_has_overview_yesterday_new_list_quality_and_audit(tmp_path):
    old = _write_watchlist(tmp_path, "20260909", [_candidate("600018", "昨日信号", 60)])
    tracker = _write_tracker(tmp_path, old)
    signal = next(iter(tracker["signals"].values()))
    signal.update(status="triggered", observations=[{"date": "2026-09-10", "open": 10, "high": 10.4, "low": 9.8, "price": 10.2}])
    current = _write_watchlist(tmp_path, "20260910", [_candidate("600019", "今日新名单", 70)])
    current_before = (tmp_path / "data" / "watchlist_20260910.json").read_bytes()
    tracker_path = tmp_path / "data" / "perf_tracker.json"
    (tracker_path).write_text(json.dumps(tracker), encoding="utf-8")
    tracker_before = tracker_path.read_bytes()

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)

    for marker in (
        "T-close 日期", "昨日信号复盘", "今日新名单 / 明日观察", "策略滚动复盘",
        "异常与数据质量", "审计详情", "今日新信号，等待下一交易日观察",
    ):
        assert marker in text
    assert text.index('id="daily-review"') < text.index('id="tomorrow-watchlist"') < text.index('id="formal-review"') < text.index('id="anomalies"') < text.index('id="audit"')
    assert (tmp_path / "data" / "watchlist_20260910.json").read_bytes() == current_before
    assert tracker_path.read_bytes() == tracker_before
    assert current["candidates"][0]["signal_id"] in text


def test_report_keeps_full_audit_details_collapsed_after_review_sections(tmp_path):
    watchlist = _write_watchlist(tmp_path, "20260910", [_candidate("600018", "审计信号", 60)])
    _write_tracker(tmp_path, watchlist)
    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)

    audit = text.split('<details id="audit">', 1)[1].split("</details>", 1)[0]
    assert "signal_id" in audit
    assert '<details id="audit" open' not in text
    assert text.index('id="audit"') > text.index('id="anomalies"')


def test_html_escapes_text_and_has_no_external_dependency(tmp_path):
    candidate = _candidate("600018", '<script>alert("x")</script>', 31, sector='A & <B>')
    watchlist = _write_watchlist(tmp_path, "20260910", [candidate])
    _write_tracker(tmp_path, watchlist)
    model, _dated, _latest = renderer.render_daily_close(
        "20260910",
        paths=_paths(tmp_path),
        calendar=CALENDAR,
        generated_at=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc),
    )
    text = renderer.render_html(model)

    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in text
    assert "A &amp; &lt;B&gt;" in text
    assert "<script src=" not in text
    assert "http://" not in text
    assert "https://" not in text


def test_xshg_sessions_and_horizon_labels_are_used(tmp_path):
    _write_watchlist(tmp_path, "20260910", [_candidate("600018", "当前名单", 31)])
    signal_payload = {
        "date": "2026-09-04",
        "mode": "close",
        "market_env": {},
        "sectors": [],
        "candidates": [_candidate("600000", "历史信号", 60)],
        "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
    }
    (tmp_path / "data/watchlist_20260904.json").write_text(json.dumps(signal_payload), encoding="utf-8")
    old_normalized = validate_watchlist(signal_payload)
    signal = _signal_from_candidate(old_normalized, old_normalized["candidates"][0], CALENDAR)
    tracker = new_tracker()
    tracker["signals"][signal["signal_id"]] = signal
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)

    assert model.review_sections["T+3"][0]["review_date"] == "2026-09-10"
    assert model.review_sections["T+5"] == []
    assert model.review_sections["T+10"] == []
    text = renderer.render_html(model)
    assert "T+5 PRIMARY REVIEW" in text
    assert "T+10 EXTENSION / CLOSURE" in text
    assert signal["signal_id"] in text


def test_path_result_stays_separate_from_later_horizon_snapshot(tmp_path):
    watchlist = _write_watchlist(tmp_path, "20260903", [_candidate("600018", "路径信号", 60)])
    tracker = _write_tracker(tmp_path, watchlist)
    _write_watchlist(tmp_path, "20260909", [_candidate("600018", "路径信号", 60)])
    signal = next(iter(tracker["signals"].values()))  # type: ignore[union-attr]
    signal.update({"status": "loss", "entry_price": 10.0, "close_date": "2026-09-09", "result_price": 9.5})
    point = signal["review_points"]["T+3"]
    point.update(
        {
            "status": "CAPTURED",
            "quote_date": "2026-09-09",
            "price": 11.25,
            "high": 11.5,
            "low": 11.0,
            "return_pct": 12.5,
            "path_status": "loss",
            "signal_status": "loss",
        }
    )
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")

    model = renderer.build_report_model("20260909", paths=_paths(tmp_path), calendar=CALENDAR)
    row = model.review_sections["T+3"][0]

    assert row["horizon_return"] == "+12.50%"
    assert "LOSS" in row["path_status"]
    assert row["snapshot_status"] == "CAPTURED"
    assert "LOSS" in renderer.render_html(model)
    assert "+12.50%" in renderer.render_html(model)


def test_same_bar_and_missing_observation_are_explicit(tmp_path):
    watchlist = _write_watchlist(tmp_path, "20260903", [_candidate("600018", "歧义信号", 60)])
    tracker = _write_tracker(tmp_path, watchlist)
    _write_watchlist(tmp_path, "20260910", [_candidate("600018", "歧义信号", 60)])
    signal = next(iter(tracker["signals"].values()))  # type: ignore[union-attr]
    signal.update({"status": "AMBIGUOUS_SAME_BAR", "close_date": "2026-09-10", "ambiguity_reason": "order unknown"})
    signal["review_points"]["T+3"].update({"status": "NOT_CAPTURED", "reason": "no observation"})
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)

    assert "AMBIGUOUS_SAME_BAR" in text
    assert "MISSING_HISTORICAL_OBSERVATION" in text
    assert model.daily_summary["missing_observations"] >= 1


def test_active_status_does_not_use_a_later_quote_as_historical_data(tmp_path):
    watchlist = _write_watchlist(tmp_path, "20260908", [_candidate("600018", "观察信号", 60)])
    tracker = _write_tracker(tmp_path, watchlist)
    _write_watchlist(tmp_path, "20260910", [_candidate("600019", "新名单", 60)])
    signal = next(iter(tracker["signals"].values()))  # type: ignore[union-attr]
    signal.update({"status": "triggered", "entry_price": 10.2})
    signal["observations"] = [{"date": "2026-09-11", "price": 11.0, "high": 11.2, "low": 10.8}]
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)

    assert model.active_signals[0]["today_close"] is None
    assert model.active_signals[0]["today_high"] is None
    assert model.active_signals[0]["today_low"] is None


def test_review_failure_still_writes_complete_watchlist_bundle(tmp_path):
    watchlist = _write_watchlist(tmp_path, "20260910", [_candidate("600018", "名单仍可交付", 60)])
    _write_tracker(tmp_path, watchlist)
    (tmp_path / "data" / "perf_tracker.json").write_text("{not-json", encoding="utf-8")

    model, dated, latest = renderer.render_daily_close(
        "20260910",
        paths=_paths(tmp_path),
        calendar=CALENDAR,
        review_failure="provider failure: quote endpoint unavailable",
    )

    text = latest.read_text(encoding="utf-8")
    assert dated.exists() and latest.exists()
    assert model.review_status == "REVIEW_FAILED"
    assert "名单仍可交付" in text
    assert "REVIEW_FAILED" in text
    assert "provider failure: quote endpoint unavailable" in text


def test_latest_is_unchanged_when_atomic_latest_replace_fails(tmp_path, monkeypatch):
    watchlist = _write_watchlist(tmp_path, "20260910", [_candidate("600018", "稳定名单", 60)])
    _write_tracker(tmp_path, watchlist)
    _model, _dated, latest = renderer.render_daily_close("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    before = latest.read_bytes()
    original_replace = renderer.os.replace

    def fail_latest(source, destination):
        if Path(destination).name == "latest.html":
            raise OSError("simulated latest replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(renderer.os, "replace", fail_latest)
    with pytest.raises(OSError, match="simulated latest"):
        renderer.render_daily_close("20260910", paths=_paths(tmp_path), calendar=CALENDAR)

    assert latest.read_bytes() == before
    assert not list((_paths(tmp_path).reports_dir()).glob(".latest.html.*.tmp"))


def test_t_close_reporting_runs_renderer_after_track_failure(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if any(str(part).endswith("track_perf.py") for part in command):
            return t_close_runner.subprocess.CompletedProcess(command, 2, "", "provider failure")
        return t_close_runner.subprocess.CompletedProcess(command, 0, "latest_html=ready", "")

    monkeypatch.setattr(t_close_runner.subprocess, "run", fake_run)
    result = t_close_runner._run_daily_close_reporting("2026-09-10", tmp_path / "data")

    assert result["status"] == "REVIEW_FAILED_REPORT_READY"
    assert len(calls) == 2
    assert any("--review-failure" == item for item in calls[1])
    assert "provider failure" in calls[1][-1]

@pytest.mark.parametrize('status', ['pending', 'triggered', 'win', 'loss', 'AMBIGUOUS_SAME_BAR', 'expired'])
def test_complete_previous_session_includes_terminal_states(tmp_path, status):
    old = _write_watchlist(tmp_path, '20260909', [_candidate('600001', 'Yesterday', 60)])
    tracker = _write_tracker(tmp_path, old)
    signal = next(iter(tracker['signals'].values()))
    signal.update(status=status, observations=[{'date': '2026-09-10', 'price': 11, 'high': 12, 'low': 9}])
    if status not in {'pending', 'triggered'}:
        signal['close_date'] = '2026-09-10'
    (tmp_path / 'data/perf_tracker.json').write_text(json.dumps(tracker), encoding='utf-8')
    _write_watchlist(tmp_path, '20260910', [_candidate('600002', 'Tomorrow', 80)])
    model = renderer.build_report_model('20260910', paths=_paths(tmp_path), calendar=CALENDAR)
    assert len(model.previous_signals) == 1
    assert model.previous_signals[0]['path_status'] == status
    assert model.previous_signals[0]['today_open'] is None
    assert model.daily_summary['tracked'] == 1
    assert [r['code'] for r in model.watchlist_rows] == ['600002']
    assert not model.active_signals
    text = renderer.render_html(model)
    main = text.split('<details id="audit">')[0]
    assert signal['signal_id'] not in main
    assert renderer._display_status(status) in main
    assert 'package_sha' not in main
    assert '<details id="audit" open' not in text
    assert text.index('id="daily-review"') < text.index('id="tomorrow-watchlist"') < text.index('id="formal-review"')


def test_previous_watchlist_missing_tracker_identity_is_not_dropped(tmp_path):
    old = _write_watchlist(tmp_path, '20260909', [_candidate('600001', 'Missing', 60), _candidate('600002', 'Missing2', 55)])
    _write_watchlist(tmp_path, '20260910', [_candidate('600003', 'New', 80)])
    model = renderer.build_report_model('20260910', paths=_paths(tmp_path), calendar=CALENDAR)
    assert {r['signal_id'] for r in model.previous_signals} == {r['signal_id'] for r in old['candidates']}
    assert all(r['path_status'] == renderer._MISSING and r['today_close'] is None for r in model.previous_signals)
    assert model.review_status == 'REVIEW_FAILED'


def test_older_active_and_closed_today_are_separate(tmp_path):
    old = _write_watchlist(tmp_path, '20260903', [_candidate(str(600001+i), 'Old', 60) for i in range(4)])
    tracker = _write_tracker(tmp_path, old)
    signals = list(tracker['signals'].values())
    for signal, status in zip(signals, ['pending', 'triggered', 'win', 'loss']):
        signal.update(status=status, observations=[{'date': '2026-09-10', 'price': 11, 'high': 12, 'low': 9}])
    signals[2]['close_date'] = '2026-09-10'
    signals[3]['close_date'] = '2026-09-09'
    (tmp_path / 'data/perf_tracker.json').write_text(json.dumps(tracker), encoding='utf-8')
    _write_watchlist(tmp_path, '20260910', [_candidate('600005', 'New', 80)])
    model = renderer.build_report_model('20260910', paths=_paths(tmp_path), calendar=CALENDAR)
    assert [r['raw_status'] for r in model.active_signals] == ['triggered', 'pending']
    assert [r['raw_status'] for r in model.closed_today] == ['win']
    assert model.daily_summary['tracked'] == 3
    assert model.daily_summary['target_hits'] == 1


def test_formal_empty_keeps_rolling_summary_and_primary_is_first(tmp_path):
    watchlist = _write_watchlist(tmp_path, '20260910', [_candidate('600001', 'New', 60)])
    _write_tracker(tmp_path, watchlist)
    model = renderer.build_report_model('20260910', paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model).split('<section id="formal-review">')[1].split('</section>')[0]
    assert '现有正式计数' in text
    assert '今日无 T+5 到期信号' in text
    row = dict(code='600001', name='Old', list_date='2026-09-03', horizon_return='+2.00%', path_status='loss', snapshot_status='CAPTURED', signal_id='hidden')
    model.review_sections['T+5'].append(row)
    model.review_sections['T+3'].append(row)
    text = renderer.render_html(model).split('<section id="formal-review">')[1].split('</section>')[0]
    assert text.index('T+5 PRIMARY REVIEW') < text.index('T+3')
    assert '止损' in text and '已记录' in text and '+2.00%' in text
    assert 'hidden' not in text


@pytest.mark.parametrize('distance,label', [(-2, '已在 Trigger 上方'), (-0.1, '已在 Trigger 上方'), (0, '贴近 Trigger'), (1, '贴近 Trigger'), (1.01, '等待触发'), (None, '—')])
def test_position_labels_are_display_only(distance, label):
    assert renderer._position(distance) == label


def test_34_candidates_preserve_exact_identity_and_values(tmp_path):
    candidates = [_candidate(str(600000+i), f'Candidate {i}', i) for i in range(34)]
    watchlist = _write_watchlist(tmp_path, '20260922', candidates)
    path = tmp_path / 'data/watchlist_20260922.json'
    before = path.read_bytes()
    _write_tracker(tmp_path, watchlist)
    model, dated, latest = renderer.render_daily_close('20260922', paths=_paths(tmp_path), calendar=CALENDAR)
    assert len(model.watchlist_rows) == 34
    expected = {r['signal_id']: r for r in watchlist['candidates']}
    assert {r['signal_id'] for r in model.watchlist_rows} == set(expected)
    for row in model.watchlist_rows:
        for key in ('code', 'name', 'score', 'trigger', 'stop', 'target', 'rr'):
            assert row[key] == expected[row['signal_id']][key]
    assert path.read_bytes() == before
    assert dated.read_bytes() == latest.read_bytes()
    assert not model.previous_signals and not model.active_signals and not model.closed_today
    assert model.daily_summary['tracked'] == 0


def test_corrupt_previous_watchlist_is_fail_soft(tmp_path):
    _write_watchlist(tmp_path, '20260910', [_candidate('600001', 'New', 60)])
    (tmp_path / 'data/watchlist_20260909.json').write_text('{broken', encoding='utf-8')
    model, _, latest = renderer.render_daily_close('20260910', paths=_paths(tmp_path), calendar=CALENDAR)
    assert model.review_status == 'REVIEW_FAILED'
    assert len(model.watchlist_rows) == 1 and latest.exists()


def test_later_terminal_state_is_not_backfilled_into_previous_day(tmp_path):
    old = _write_watchlist(tmp_path, '20260909', [_candidate('600001', 'Old', 60)])
    tracker = _write_tracker(tmp_path, old)
    signal = next(iter(tracker['signals'].values()))
    signal.update(status='win', close_date='2026-09-11', observations=[{'date': '2026-09-10', 'price': 11, 'high': 12, 'low': 9}])
    (tmp_path / 'data/perf_tracker.json').write_text(json.dumps(tracker), encoding='utf-8')
    _write_watchlist(tmp_path, '20260910', [_candidate('600002', 'New', 80)])
    model = renderer.build_report_model('20260910', paths=_paths(tmp_path), calendar=CALENDAR)
    assert model.previous_signals[0]['path_status'] == renderer._MISSING
    assert model.previous_signals[0]['today_close'] == 11
    assert model.daily_summary['target_hits'] == 0
    assert model.daily_summary['daily_missing'] == 1


def test_current_watchlist_events_do_not_enter_historical_summary(tmp_path):
    current = _write_watchlist(tmp_path, '20260922', [_candidate('600001', 'New', 60)])
    tracker = _write_tracker(tmp_path, current)
    signal = next(iter(tracker['signals'].values()))
    signal.update(status='AMBIGUOUS_SAME_BAR', close_date='2026-09-22', first_trigger_date='2026-09-22', observations=[{'date': '2026-09-22', 'price': 11, 'high': 12, 'low': 9}])
    (tmp_path / 'data/perf_tracker.json').write_text(json.dumps(tracker), encoding='utf-8')
    model = renderer.build_report_model('20260922', paths=_paths(tmp_path), calendar=CALENDAR)
    assert model.daily_summary['tracked'] == 0
    assert model.daily_summary['new_triggered'] == 0
    assert model.daily_summary['ambiguous'] == 0
