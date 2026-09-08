from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, time
from pathlib import Path

import pytest

import exact_date_review_recovery as recovery
import render_daily_close_html as renderer
import track_perf
import t_close_runner
from data_paths import DataPaths
from track_perf import (
    REVIEW_OBSERVATION_INCOMPLETE,
    REVIEW_POINT_CAPTURED,
    SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1,
    _append_observation,
    _signal_from_candidate,
    expected_review_set,
    new_tracker,
    run_daily_review,
    verify_review_coverage,
)
from trading_calendar import TradingCalendar


CALENDAR = TradingCalendar(holidays=set(), session_close_time=time(15, 0))
TARGET = "2026-09-08"


def _quote_raw(
    code: str = "600519",
    *,
    quote_date: str = TARGET,
    price: float = 123.45,
    open_price: float = 121.0,
    high: float = 125.0,
    low: float = 119.5,
) -> bytes:
    fields = [""] * 50
    fields[1] = "测试股份"
    fields[2] = code
    fields[3] = f"{price:.2f}"
    fields[4] = "120.00"
    fields[5] = f"{open_price:.2f}"
    fields[6] = "1000"
    fields[30] = quote_date.replace("-", "") + "161459"
    fields[32] = "2.88"
    fields[33] = f"{high:.2f}"
    fields[34] = f"{low:.2f}"
    fields[38] = "4.56"
    fields[49] = "1.78"
    return f'v_sh{code}="{"~".join(fields)}";'.encode("gbk")


def _write_capture(
    root: Path,
    *,
    component: str = "tencent_quote",
    code: str = "600519",
    raw: bytes | None = None,
    metadata_overrides: dict[str, object] | None = None,
) -> Path:
    directory = root / component
    directory.mkdir(parents=True, exist_ok=True)
    raw = raw if raw is not None else _quote_raw(code)
    raw_path = directory / "capture.raw"
    sidecar = directory / "capture.json"
    raw_path.write_bytes(raw)
    metadata: dict[str, object] = {
        "schema_version": recovery.CAPTURE_SCHEMA,
        "target_date": TARGET,
        "effective_trading_date": TARGET,
        "actual_retrieved_at_bjt": "2026-09-08T18:00:00+08:00",
        "code_git_sha": recovery.EXPECTED_CODE_GIT_SHA,
        "completeness_status": "COMPLETE",
        "provider": "Tencent",
        "source_identity": "qt.gtimg.cn",
        "provider_version": "requests/test",
        "content_type": "provider_response",
        "encoding": "bytes",
        "decode_encoding": "gbk",
        "byte_length": len(raw),
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "logical_component_identity": "batch=0;codes=" + code,
        "request_identity": "https://qt.gtimg.cn/q=sh" + code,
        "record_count": 1,
        "batch_count": 1,
        "codes": [code],
    }
    metadata.update(metadata_overrides or {})
    sidecar.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return sidecar


def _minimal_candidate(code: str = "600519", *, price: float = 120.0) -> dict[str, object]:
    return {
        "signal_id": "B_BREAKOUT_RETEST_LEGACY_V1_1:2026-09-03:%s:B_BREAKOUT_RETEST" % code,
        "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
        "date": "2026-09-03",
        "code": code,
        "setup": "B_BREAKOUT_RETEST",
        "name": "测试股份",
        "buy_type": "B 突破回踩",
        "score": 60,
        "price": price,
        "trigger": 121.0,
        "stop": 114.0,
        "target": 132.0,
        "rr": 2.0,
    }


def _compatibility_fixture(*, adjustment_mode: str = "PROVIDER_QFQ_SNAPSHOT", open_price: float = 121.0):
    quote = {
        "code": "600519",
        "price": 123.45,
        "open": open_price,
        "high": 125.0,
        "low": 119.5,
        "quote_date": TARGET,
    }
    audit = {
        "quotes": {"600519": quote},
        "kline_records": {
            "600519": {
                "records": [
                    {"date": "2026-09-03", "close": 120.0},
                    {"date": TARGET, "open": open_price, "high": 125.0, "low": 119.5, "close": 123.45},
                ],
                "metadata": {"adjustment_mode": adjustment_mode},
            }
        },
    }
    watchlists = {
        "2026-09-03": {"candidates": [_minimal_candidate()]},
        "2026-09-07": {"candidates": []},
    }
    return audit, watchlists


def test_valid_immutable_quote_pair_is_integrity_pass_and_parsed(tmp_path):
    _write_capture(tmp_path)
    result = recovery.audit_exact_date_evidence(tmp_path, calendar=CALENDAR, expected_codes={"600519"})

    assert result["integrity_status"] == "PASS"
    assert result["pair_count"] == result["valid_pair_count"] == 1
    assert result["provider_calls"] == 0
    assert result["quotes"]["600519"]["open"] == 121.0


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"file_sha256": "0" * 64}, "file_sha256"),
        ({"byte_length": 1}, "byte_length"),
        ({"target_date": "2026-09-07"}, "target_date"),
        ({"effective_trading_date": "2026-09-07"}, "effective_trading_date"),
        ({"code_git_sha": "UNKNOWN_ORIGIN"}, "code_git_sha"),
        ({"completeness_status": "FAILED"}, "completeness_status"),
        ({"provider": "Unknown", "source_identity": "unknown"}, "formal_provider_source"),
    ],
)
def test_immutable_pair_rejects_integrity_or_provenance_mismatch(tmp_path, overrides, expected):
    _write_capture(tmp_path, metadata_overrides=overrides)
    result = recovery.audit_exact_date_evidence(tmp_path, calendar=CALENDAR, expected_codes={"600519"})

    assert result["integrity_status"] == "FAIL"
    assert any(expected in item for item in result["errors"])
    assert result["provider_calls"] == 0


def test_immutable_pair_rejects_retrieval_before_session_close(tmp_path):
    _write_capture(tmp_path, metadata_overrides={"actual_retrieved_at_bjt": "2026-09-08T14:59:59+08:00"})
    result = recovery.audit_exact_date_evidence(tmp_path, calendar=CALENDAR, expected_codes={"600519"})

    assert result["integrity_status"] == "FAIL"
    assert any("retrieved_before_session_close" in item for item in result["errors"])


def test_evidence_root_resolution_accepts_capture_date_layout(tmp_path):
    nested = tmp_path / "20260908" / "20260908"
    _write_capture(nested)

    assert recovery.resolve_evidence_root(tmp_path, TARGET) == nested.resolve()


def test_evidence_root_resolution_rejects_ambiguous_layout(tmp_path):
    base = tmp_path / "base"
    _write_capture(base)
    _write_capture(base / "20260908")

    with pytest.raises(recovery.ExactDateEvidenceError, match="UNRESOLVED"):
        recovery.resolve_evidence_root(base, TARGET)


def test_price_compatibility_passes_with_qfq_cross_check():
    audit, watchlists = _compatibility_fixture()

    result = recovery.audit_price_compatibility(audit, watchlists)

    assert result["status"] == "PASS"
    assert result["codes_compatible"] == 1
    assert result["field_matches"] == {"open": 1, "high": 1, "low": 1, "close": 1}


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_price_compatibility_rejects_mismatched_qfq_basis(field):
    audit, watchlists = _compatibility_fixture()
    current = audit["kline_records"]["600519"]["records"][1]
    current[field] = float(current[field]) + 0.01

    result = recovery.audit_price_compatibility(audit, watchlists)

    assert result["status"] == "PARTIAL"
    assert "600519" in result["incompatible_codes"]
    assert "RECOVERY_PRICE_BASIS_INCOMPATIBLE" in result["incompatible_codes"]["600519"]


def test_price_compatibility_rejects_non_qfq_adjustment_mode():
    audit, watchlists = _compatibility_fixture(adjustment_mode="PROVIDER_RAW_SNAPSHOT")

    result = recovery.audit_price_compatibility(audit, watchlists)

    assert "600519" in result["incompatible_codes"]


def test_observation_provenance_is_written_without_changing_quote_fields():
    signal = {"observations": []}
    quote = {"quote_date": TARGET, "open": 121.0, "price": 123.45, "high": 125.0, "low": 119.5}
    changed = _append_observation(
        signal,
        quote,
        source_mode=SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1,
        provenance={"capture_sha256": "abc", "source_identity": "qt.gtimg.cn"},
    )

    assert changed is True
    assert signal["observations"][0]["date"] == TARGET
    assert signal["observations"][0]["open"] == 121.0
    assert signal["observations"][0]["source_mode"] == SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1
    assert signal["observations"][0]["provenance"]["capture_sha256"] == "abc"


def test_expected_review_set_excludes_same_day_signal():
    calendar = TradingCalendar(holidays=set())
    tracker = new_tracker()
    old = _signal_from_candidate(
        {"date": "2026-09-03", "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1"},
        _minimal_candidate(),
        calendar,
    )
    same_day_candidate = dict(_minimal_candidate(), signal_id="B_BREAKOUT_RETEST_LEGACY_V1_1:2026-09-08:600519:B_BREAKOUT_RETEST", date="2026-09-08")
    same_day = _signal_from_candidate(
        {"date": "2026-09-08", "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1"},
        same_day_candidate,
        calendar,
    )
    tracker["signals"].update({old["signal_id"]: old, same_day["signal_id"]: same_day})

    expected = expected_review_set(tracker, TARGET, calendar)

    assert expected["execution_signal_ids"] == [old["signal_id"]]
    assert same_day["signal_id"] not in expected["execution_signal_ids"]


def test_run_daily_review_marks_provider_failure_as_incomplete(monkeypatch):
    calendar = TradingCalendar(holidays=set())
    tracker = new_tracker()
    signal = _signal_from_candidate(
        {"date": "2026-09-03", "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1"},
        _minimal_candidate(),
        calendar,
    )
    tracker["signals"][signal["signal_id"]] = signal

    def fail_fetch(*args, **kwargs):
        raise track_perf.QuoteDataError("provider must not be used in this test")

    monkeypatch.setattr(track_perf, "fetch_quotes", fail_fetch)
    with pytest.raises(track_perf.QuoteDataError):
        run_daily_review(tracker, today=TARGET, calendar=calendar)

    assert tracker["review_coverage"]["status"] == REVIEW_OBSERVATION_INCOMPLETE
    assert tracker["review_coverage"]["execution_missing"] == 1
    assert tracker["review_coverage"]["horizon_missing"] == 1
    point = signal["review_points"]["T+3"]
    assert point["status"] == track_perf.REVIEW_POINT_NOT_CAPTURED
    assert point["reason"] == REVIEW_OBSERVATION_INCOMPLETE


def test_verify_review_coverage_requires_exact_observation_date():
    calendar = TradingCalendar(holidays=set())
    tracker = new_tracker()
    signal = _signal_from_candidate(
        {"date": "2026-09-03", "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1"},
        _minimal_candidate(),
        calendar,
    )
    signal["observations"] = [{"date": "2026-09-07", "price": 1.0}]
    tracker["signals"][signal["signal_id"]] = signal
    expected = expected_review_set(tracker, TARGET, calendar)

    coverage = verify_review_coverage(tracker, TARGET, expected=expected, calendar=calendar)

    assert coverage["execution_expected"] == 1
    assert coverage["execution_captured"] == 0
    assert coverage["execution_missing"] == 1
    assert coverage["horizon_missing"] == 1


def test_real_20260908_recovery_is_local_only_and_separates_9_7_from_9_3(monkeypatch):
    paths = DataPaths(Path(__file__).resolve().parents[1] / "data")
    tracker = track_perf.load_tracker(paths.perf_tracker_file())

    def fail_provider(*args, **kwargs):
        raise AssertionError("exact-date recovery must not call a provider")

    monkeypatch.setattr(track_perf, "fetch_quotes", fail_provider)
    result = recovery.recover_exact_date_review(
        tracker,
        paths=paths,
        evidence_root=paths.root / "t_close_evidence" / "20260908",
        target_date=TARGET,
    )

    assert result["status"] == "RECOVERY_APPLIED"
    assert result["integrity_status"] == "PASS"
    assert result["evidence_pair_count"] == result["valid_pair_count"] == 10598
    assert result["provider_calls"] == 0
    assert result["execution_2026_09_07"]["expected"] == 25
    assert result["execution_2026_09_07"]["recovered"] == 25
    assert result["snapshot_2026_09_03_t_plus_3"]["expected"] == 11
    assert result["snapshot_2026_09_03_t_plus_3"]["recovered"] == 11
    assert all(
        observation.get("source_mode") == SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1
        for signal in tracker["signals"].values()
        if signal.get("date") == "2026-09-07"
        for observation in signal.get("observations", [])
        if observation.get("date") == TARGET
    )
    assert all(
        not any(observation.get("date") == TARGET for observation in signal.get("observations", []))
        for signal in tracker["signals"].values()
        if signal.get("date") == "2026-09-03"
    )
    assert all(
        signal["review_points"]["T+3"]["status"] == REVIEW_POINT_CAPTURED
        and signal["review_points"]["T+3"]["return_pct"] is None
        and signal["review_points"]["T+3"]["path_status"] == track_perf.PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH
        for signal in tracker["signals"].values()
        if signal.get("date") == "2026-09-03"
    )
    assert result["review_coverage"]["status"] == REVIEW_OBSERVATION_INCOMPLETE


def test_real_recovered_html_shows_25_yesterday_rows_and_11_unverified_nodes():
    paths = DataPaths(Path(__file__).resolve().parents[1] / "data")
    model = renderer.build_report_model(TARGET, paths=paths)
    text = renderer.render_html(model)

    assert model.metadata["candidate_count"] == 34
    assert len(model.previous_signals) == 25
    assert all(row["today_open"] is not None for row in model.previous_signals)
    assert all(row["today_high"] is not None for row in model.previous_signals)
    assert all(row["today_low"] is not None for row in model.previous_signals)
    assert all(row["today_close"] is not None for row in model.previous_signals)
    assert all(row["observation_source"] == "已恢复（不可变证据）" for row in model.previous_signals)
    assert len(model.review_sections["T+3"]) == 11
    assert all(row["horizon_return"] == "UNVERIFIED" for row in model.review_sections["T+3"])
    assert all(row["path_status"] == "UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH" for row in model.review_sections["T+3"])
    assert all(row["snapshot_source"] == "已恢复（不可变证据）" for row in model.review_sections["T+3"])
    assert model.review_status == REVIEW_OBSERVATION_INCOMPLETE
    assert "复盘数据不完整：execution expected=36, captured=25, missing=11" in text
    assert "昨日名单今日表现 · 2026-09-07" in text
    assert "今日开盘" in text and "收盘较 Trigger %" in text
    assert "路径未完整验证" in text and "已恢复（不可变证据）" in text


def test_real_recovery_is_idempotent_and_does_not_duplicate_observations():
    paths = DataPaths(Path(__file__).resolve().parents[1] / "data")
    tracker = track_perf.load_tracker(paths.perf_tracker_file())
    recovery.recover_exact_date_review(
        tracker,
        paths=paths,
        evidence_root=paths.root / "t_close_evidence" / "20260908",
        target_date=TARGET,
    )

    observations = [
        observation
        for signal in tracker["signals"].values()
        if signal.get("date") == "2026-09-07"
        for observation in signal.get("observations", [])
        if observation.get("date") == TARGET
    ]
    assert len(observations) == 25
    assert len({signal_id for signal_id in tracker["signals"]}) == 70


def test_daily_close_runner_surfaces_incomplete_guard_as_fail_soft_bundle(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    (data_root / "perf_tracker.json").write_text(
        json.dumps({
            "review_coverage": {
                "report_date": TARGET,
                "status": REVIEW_OBSERVATION_INCOMPLETE,
                "execution_expected": 1,
                "execution_captured": 0,
                "execution_missing": 1,
                "horizon_expected": 1,
                "horizon_captured": 0,
                "horizon_missing": 1,
            }
        }),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(command)
        if any(str(part).endswith("track_perf.py") for part in command):
            return t_close_runner.subprocess.CompletedProcess(command, 0, "ok", "")
        return t_close_runner.subprocess.CompletedProcess(command, 0, "rendered", "")

    monkeypatch.setattr(t_close_runner.subprocess, "run", fake_run)
    result = t_close_runner._run_daily_close_reporting(TARGET, data_root)

    assert result["status"] == "REVIEW_OBSERVATION_INCOMPLETE_REPORT_READY"
    assert result["track_perf"]["review_coverage"]["execution_missing"] == 1
    assert "--date" in calls[0] and TARGET in calls[0]
