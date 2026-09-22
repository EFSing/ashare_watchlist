from __future__ import annotations

import hashlib
import json
import re
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


def _payload(
    list_date: str,
    candidates: list[dict[str, object]],
    *,
    input_coverage: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "date": f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:]}",
        "mode": "close",
        "market_env": {"grade": "A"},
        "sectors": [],
        "candidates": candidates,
        "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
    }
    if input_coverage is not None:
        payload["input_coverage"] = input_coverage
    return payload


def _write_watchlist(
    root: Path,
    list_date: str,
    candidates: list[dict[str, object]],
    *,
    input_coverage: dict[str, object] | None = None,
) -> dict[str, object]:
    data_root = root / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    path = data_root / f"watchlist_{list_date}.json"
    path.write_text(
        json.dumps(_payload(list_date, candidates, input_coverage=input_coverage), ensure_ascii=False),
        encoding="utf-8",
    )
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


def test_report_displays_main_board_universe_and_keeps_policy_literal_in_audit(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    payload = _payload("20260910", [_candidate("600018", "主板信号", 70)])
    payload["universe_policy"] = "ASHARE_MAIN_BOARD_ONLY_V1"
    path = data_root / "watchlist_20260910.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    watchlist = load_watchlist(path)
    _write_tracker(tmp_path, watchlist)

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)
    main = text.split('<details id="audit">', 1)[0]
    audit = text.split('<details id="audit">', 1)[1]

    assert model.metadata["universe"] == "沪深主板 / Main Board Only"
    assert "股票池：<strong>沪深主板 / Main Board Only</strong>" in main
    assert "ASHARE_MAIN_BOARD_ONLY_V1" not in main
    assert "ASHARE_MAIN_BOARD_ONLY_V1" in audit


def test_report_explicitly_displays_degraded_input_coverage(tmp_path):
    coverage = {
        "schema_version": "INPUT_COVERAGE_V1",
        "coverage_status": "DEGRADED",
        "evaluated_symbol_count": 2,
        "excluded_symbol_count": 1,
        "excluded_symbols": [
            {
                "symbol": "605366",
                "provider_symbol": "605366.SH",
                "target_date": "2026-09-10",
                "provider": "HiThink Financial-API",
                "status": "EXCLUDED_PROVIDER_STALE",
                "reason": "TARGET_DAY_HISTORICAL_STALE",
                "latest_historical_date": "2026-09-09",
                "quote_trade_state": "TRADED",
                "evidence": {"quote": {}, "historical": {}},
                "policy_version": "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
            }
        ],
        "policy_version": "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
    }
    watchlist = _write_watchlist(
        tmp_path,
        "20260910",
        [_candidate("600018", "剩余信号", 70)],
        input_coverage=coverage,
    )
    _write_tracker(tmp_path, watchlist)

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)

    assert model.metadata["input_coverage_status"] == "DEGRADED"
    assert model.metadata["evaluated_symbol_count"] == 2
    assert model.metadata["excluded_symbol_count"] == 1
    coverage_block = re.search(
        r'<div class="review-callout warning"><strong>数据质量：部分覆盖</strong>.*?</div>',
        text,
        re.S,
    )
    assert coverage_block is not None
    assert "本次有效评估 2 只股票，1 只因行情数据异常未参与筛选。下方候选名单不包含这些股票。" in coverage_block.group(0)
    for machine_detail in (
        "605366",
        "TARGET_DAY_HISTORICAL_STALE",
        "2026-09-09",
        "2026-09-10",
        "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
        "excluded_reason_counts",
    ):
        assert machine_detail not in coverage_block.group(0)
    assert model.metadata["input_coverage"]["excluded_symbols"][0]["symbol"] == "605366"
    assert "input-coverage-json" in text
    assert "&quot;symbol&quot;:&quot;605366&quot;" in text


def test_report_keeps_complete_input_coverage_presentation(tmp_path):
    coverage = {
        "schema_version": "INPUT_COVERAGE_V1",
        "coverage_status": "COMPLETE",
        "evaluated_symbol_count": 2,
        "excluded_symbol_count": 0,
        "excluded_symbols": [],
        "raw_symbol_count": 2,
        "qualified_symbol_count": 2,
        "formal_result_valid": True,
        "policy_version": "PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1",
    }
    watchlist = _write_watchlist(
        tmp_path,
        "20260910",
        [_candidate("600018", "完整输入", 70)],
        input_coverage=coverage,
    )
    _write_tracker(tmp_path, watchlist)

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)

    assert "INPUT COVERAGE = COMPLETE" in text
    assert "raw_symbol_count = 2" in text
    assert "policy version = PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1" in text


def test_no_valid_input_diagnostic_is_dated_bounded_and_does_not_touch_latest(tmp_path):
    paths = _paths(tmp_path)
    paths.reports_dir().mkdir(parents=True, exist_ok=True)
    latest = paths.reports_dir() / "latest.html"
    latest.write_text("previous formal latest", encoding="utf-8")
    records = [
        {
            "symbol": f"600{index:03d}",
            "provider_symbol": f"600{index:03d}.SH",
            "target_date": "2026-09-10",
            "provider": "HiThink Financial-API",
            "status": "EXCLUDED_INPUT_ANOMALY",
            "reason": "SNAPSHOT_MISSING",
            "latest_historical_date": None,
            "quote_trade_state": "UNAVAILABLE",
            "evidence": {"quote": {}, "historical": {}},
            "policy_version": "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
        }
        for index in range(25)
    ]
    coverage = {
        "schema_version": "INPUT_COVERAGE_V1",
        "coverage_status": "NO_VALID_INPUT",
        "evaluated_symbol_count": 0,
        "excluded_symbol_count": len(records),
        "excluded_symbols": records,
        "excluded_reason_counts": {"SNAPSHOT_MISSING": len(records)},
        "formal_result_valid": False,
        "policy_version": "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
    }

    record_path, report_path = renderer.render_input_diagnostic_report(
        "20260910",
        {
            "target_date": "2026-09-10",
            "actual_retrieved_at_bjt": "2026-09-10T17:20:00+08:00",
            "run_type": "SAME_CALENDAR_DATE",
            "raw_symbol_count": 25,
            "qualified_symbol_count": 25,
            "evaluated_symbol_count": 0,
            "excluded_symbol_count": 25,
            "excluded_reason_counts": {"SNAPSHOT_MISSING": 25},
            "input_coverage": coverage,
            "exclusions": records,
            "global_failures": [],
        },
        paths=paths,
        generated_at=datetime.fromisoformat("2026-09-10T17:21:00+08:00"),
    )

    text = report_path.read_text(encoding="utf-8")
    machine = json.loads(record_path.read_text(encoding="utf-8"))
    assert report_path.name == "daily_close_20260910.html"
    assert record_path.name == "daily_input_diagnostic_20260910.json"
    assert "NO_VALID_INPUT" in text
    assert "600000" in text
    assert "600024" not in text
    assert len(machine["exclusions"]) == 25
    assert machine["formal_watchlist_created"] is False
    assert latest.read_text(encoding="utf-8") == "previous formal latest"


def test_no_valid_input_report_displays_universe_qualification_reasons(tmp_path):
    paths = _paths(tmp_path)
    qualification = {
        "schema_version": "HITHINK_UNIVERSE_QUALIFICATION_DIAGNOSTIC_V1",
        "source": "HiThink Financial-API /api/meta/tickers/list",
        "target_date": "2026-09-22",
        "source_row_count": 5576,
        "sh_sz_scope_count": 5226,
        "main_board_count": 3197,
        "eligible_count": 0,
        "reason_counts": {
            "UNIVERSE_LIST_DATE_MISSING": 3197,
            "UNIVERSE_NON_MAIN_BOARD": 2029,
            "UNIVERSE_OUT_OF_SCOPE_EXCHANGE": 350,
        },
        "reason_samples": {
            "UNIVERSE_LIST_DATE_MISSING": ["001246"],
            "UNIVERSE_NON_MAIN_BOARD": ["300001"],
            "UNIVERSE_OUT_OF_SCOPE_EXCHANGE": ["430047"],
        },
    }

    _record_path, report_path = renderer.render_input_diagnostic_report(
        "20260922",
        {
            "target_date": "2026-09-22",
            "raw_symbol_count": 5576,
            "qualified_symbol_count": 0,
            "evaluated_symbol_count": 0,
            "excluded_symbol_count": 0,
            "excluded_reason_counts": {},
            "input_coverage": {
                "schema_version": "INPUT_COVERAGE_V1",
                "coverage_status": "NO_VALID_INPUT",
                "evaluated_symbol_count": 0,
                "excluded_symbol_count": 0,
                "excluded_symbols": [],
                "policy_version": "PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1",
                "formal_result_valid": False,
            },
            "exclusions": [],
            "global_failures": [],
            "universe_qualification": qualification,
        },
        paths=paths,
        generated_at=datetime.fromisoformat("2026-09-22T17:30:00+08:00"),
    )

    text = report_path.read_text(encoding="utf-8")
    assert "股票池资格过滤诊断" in text
    assert "UNIVERSE_LIST_DATE_MISSING" in text
    assert "UNIVERSE_NON_MAIN_BOARD" in text
    assert "UNIVERSE_OUT_OF_SCOPE_EXCHANGE" in text
    assert "001246" in text


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
        "T-close", "昨日 / 活跃信号复盘", "今日新名单", "固定节点研究",
        "数据质量", "技术与审计信息", "今日新信号，等待下一交易日观察",
    ):
        assert marker in text
    assert (
        text.index('id="overview"') < text.index('id="trade-performance"')
        < text.index('id="tomorrow-watchlist"') < text.index('id="daily-review"')
        < text.index('id="formal-review"') < text.index('id="anomalies"')
        < text.index('id="audit"')
    )
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


def test_fixed_node_separates_unverified_path_from_true_untriggered(tmp_path):
    watchlist = _write_watchlist(
        tmp_path,
        "20260903",
        [_candidate("600018", "路径待核验", 60), _candidate("600019", "真实未触发", 59)],
    )
    tracker = _write_tracker(tmp_path, watchlist)
    _write_watchlist(tmp_path, "20260909", [_candidate("600020", "今日信号", 70)])
    signals = list(tracker["signals"].values())
    for signal, execution_status in zip(
        signals,
        [renderer.UNVERIFIED_MISSING_EXECUTION_OBSERVATION, "VERIFIED"],
    ):
        signal["execution_verification_status"] = execution_status
        point = signal["review_points"]["T+3"]
        point.update(
            {
                "status": "CAPTURED",
                "quote_date": "2026-09-09",
                "open": 10.0,
                "price": 10.1,
                "high": 10.2,
                "low": 9.9,
                "return_pct": None,
                "path_status": "pending",
                "signal_status": "pending",
                "reason": "confirmed entry unavailable; return is unverified",
            }
        )
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")

    model = renderer.build_report_model("20260909", paths=_paths(tmp_path), calendar=CALENDAR)
    rows = model.review_sections["T+3"]
    text = renderer.render_html(model)

    by_code = {row["code"]: row for row in rows}
    assert by_code["600018"]["path_status_code"] == renderer.PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH
    assert by_code["600018"]["path_status"] == "UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH"
    assert by_code["600019"]["path_status_code"] == "pending"
    assert by_code["600019"]["path_status"] == "PENDING"
    assert text.count("<span>可计算</span><strong>0</strong>") >= 1
    assert text.count("<span>未触发</span><strong>1</strong>") >= 1
    assert text.count("<span>路径待核验</span><strong>1</strong>") >= 1
    assert "路径未完整验证" in text
    assert "未触发" in text


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
    assert len(calls) == 3
    assert any(str(part).endswith("b_shadow_monitor.py") for part in calls[1])
    assert "update" in calls[1]
    assert any("--review-failure" == item for item in calls[2])
    assert "provider failure" in calls[2][-1]


def test_t_close_reporting_marks_backfill_tracker_and_skips_shadow_update(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return t_close_runner.subprocess.CompletedProcess(command, 0, "{}\n", "")

    monkeypatch.setattr(t_close_runner.subprocess, "run", fake_run)
    t_close_runner._run_daily_close_reporting(
        "2026-09-18",
        tmp_path / "data",
        skip_shadow_capture=True,
    )

    assert len(calls) == 2
    assert any(str(part).endswith("track_perf.py") for part in calls[0])
    assert "--authorized-weekend-backfill" in calls[0]
    assert not any(str(part).endswith("b_shadow_monitor.py") for part in calls)


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
    assert text.index('id="tomorrow-watchlist"') < text.index('id="daily-review"') < text.index('id="formal-review"')


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
    assert '查看节点覆盖' in text
    assert '今日无该节点到期信号' in text
    row = dict(code='600001', name='Old', list_date='2026-09-03', horizon_return='+2.00%', path_status='loss', snapshot_status='CAPTURED', signal_id='hidden')
    model.review_sections['T+5'].append(row)
    model.review_sections['T+3'].append(row)
    text = renderer.render_html(model).split('<section id="formal-review">')[1].split('</section>')[0]
    assert text.index('查看 T+3 明细') < text.index('查看 T+5 明细')
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


def test_trade_performance_section_is_before_audit_and_keeps_small_sample_visible(tmp_path):
    watchlist = _write_watchlist(tmp_path, '20260911', [_candidate('600001', '绩效信号', 60)])
    _write_tracker(tmp_path, watchlist)

    model, dated, latest = renderer.render_daily_close('20260911', paths=_paths(tmp_path), calendar=CALENDAR)
    text = dated.read_text(encoding='utf-8')

    assert model.trade_performance is not None
    assert text.index('id="trade-performance"') < text.index('id="daily-review"')
    for marker in (
        '交易绩效', '样本不足', '胜率', '平均收益', '平均盈利', '平均亏损',
        '盈亏比', 'Profit Factor', '期望收益', '平均 R', '平均持有',
        '平均 MFE', '平均 MAE', '中位收益', '已结案交易', '当前持仓', '排除 / 未核验',
        'SAMPLE_SMALL', 'N/A / sample=0',
    ):
        assert marker in text
    assert dated.read_bytes() == latest.read_bytes()


def test_presentation_regression_has_compact_sections_and_collapsed_technical_detail(tmp_path):
    candidates = [_candidate(f'6000{i:02d}', f'候选{i}', 80 - i) for i in range(5)]
    watchlist = _write_watchlist(tmp_path, '20260911', candidates)
    _write_tracker(tmp_path, watchlist)

    model, dated, latest = renderer.render_daily_close('20260911', paths=_paths(tmp_path), calendar=CALENDAR)
    text = dated.read_text(encoding='utf-8')
    main = text.split('<details id="audit">', 1)[0]
    audit = text.split('<details id="audit">', 1)[1]

    assert len(re.findall(r'<article class="kpi-card primary-kpi"', text)) == 6
    assert text.index('id="trade-performance"') < text.index('id="tomorrow-watchlist"')
    assert text.index('id="tomorrow-watchlist"') < text.index('id="daily-review"') < text.index('id="formal-review"')
    assert '<details id="unverified-excluded"' in text
    assert '<details class="research-detail"><summary>查看 T+3 明细' in text
    assert text.count('sample=0') <= 1
    assert 'N/A' not in main
    for literal in ('UNVERIFIED_MISSING_EXECUTION_OBSERVATION', 'EXECUTION_MODEL_DAILY_OHLC_T1_V1'):
        assert literal not in main
        assert literal in audit
    assert len(re.findall(r'<article class="watch-row"', text)) == 5
    assert all(candidate['code'] in main and candidate['name'] in main for candidate in candidates)
    assert '<table class="trade-table">' not in text
    assert 'font-variant-numeric: tabular-nums' in text
    assert 'class="positive"' in text and 'class="negative"' in text
    assert dated.read_bytes() == latest.read_bytes()


def test_mobile_responsive_css_preserves_core_fields_and_wide_table_fallback(tmp_path):
    watchlist = _write_watchlist(tmp_path, '20260910', [_candidate('600018', '手机可读名单', 70)])
    _write_tracker(tmp_path, watchlist)

    model, dated, latest = renderer.render_daily_close(
        '20260910',
        paths=_paths(tmp_path),
        calendar=CALENDAR,
        generated_at=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc),
    )
    text = dated.read_text(encoding='utf-8')
    css = text.split('<style>', 1)[1].split('</style>', 1)[0]
    mobile_css = css.split('@media (max-width: 600px)', 1)[1]

    def assert_mobile_rule(selector: str, declaration: str) -> None:
        assert re.search(rf'{re.escape(selector)}\s*\{{[^}}]*{re.escape(declaration)}', mobile_css)

    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in text
    assert 'overflow-x: hidden' in css
    assert 'env(safe-area-inset-left' in mobile_css
    assert 'env(safe-area-inset-right' in mobile_css
    assert 'env(safe-area-inset-bottom' in mobile_css
    assert_mobile_rule('.overview-grid', 'grid-template-columns: 1fr;')
    assert_mobile_rule('.overview-facts', 'grid-template-columns: repeat(2, minmax(0, 1fr));')
    assert_mobile_rule('.primary-kpis', 'grid-template-columns: repeat(2, minmax(0, 1fr));')
    assert_mobile_rule('.metric-strip', 'grid-template-columns: repeat(2, minmax(0, 1fr));')
    assert_mobile_rule('.funnel', 'grid-template-columns: repeat(2, minmax(0, 1fr));')
    assert_mobile_rule('.watch-primary', 'grid-template-columns: 26px minmax(0, 1fr) auto;')
    assert_mobile_rule('.watch-state', 'grid-column: 2 / -1;')
    assert_mobile_rule('.watch-facts', 'grid-template-columns: repeat(2, minmax(0, 1fr));')
    assert_mobile_rule('.action-facts', 'grid-template-columns: repeat(2, minmax(0, 1fr));')
    assert_mobile_rule('.research-panels', 'grid-template-columns: 1fr;')
    assert_mobile_rule('.quality-grid', 'grid-template-columns: 1fr;')
    assert 'min-height: 44px' in mobile_css
    assert '.table-scroll' in css
    assert 'overflow-x: auto' in css
    assert '-webkit-overflow-scrolling: touch' in css
    assert 'overscroll-behavior-inline: contain' in css
    assert '.trade-table { min-width: 1260px; }' in css
    assert '.audit-table { min-width: 1180px; }' in css
    assert 'overflow-wrap: anywhere' in css

    row = model.watchlist_rows[0]
    assert [row['code']] == ['600018']
    for marker in (
        str(row['code']),
        str(row['name']),
        renderer._integer(row['score']),
        *(renderer._number(row[key]) for key in ('trigger', 'stop', 'target', 'rr')),
    ):
        assert marker in text
    assert all(marker in text for marker in ('触发', '止损', '目标'))
    assert dated.read_bytes() == latest.read_bytes()
    assert renderer.render_html(model) == renderer.render_html(model)


def test_entered_unverified_paths_are_marked_in_the_compact_funnel():
    performance = {
        'entered': 21,
        'eligible_signals': 0,
        'execution_unverified': 70,
    }
    assert '21*' in renderer._performance_funnel(performance)
