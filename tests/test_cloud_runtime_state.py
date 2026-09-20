from __future__ import annotations

import json
import subprocess
from datetime import date
from html import escape
from pathlib import Path

import pytest

from b_shadow_monitor import new_store, save_store
from cloud_runtime_state import (
    ALREADY_COMPLETED,
    INCOMPLETE_SAME_DAY_STATE,
    RuntimeStateError,
    _is_allowlisted_data_relative,
    allowlisted_data_files,
    bootstrap_allowlist,
    build_summary,
    completed_run_status,
    persist_allowlist,
    persist_failure_notice,
    persist_input_diagnostic,
    restore_allowlist,
    validate_runtime_data,
    validate_state_tree,
)
from data_paths import DataPaths
from track_perf import _signal_from_candidate, load_tracker, new_tracker, save_tracker
from trading_calendar import TradingCalendar
from upload_daily_checkpoint import (
    build_daily_checkpoint_manifest,
    checkpoint_manifest_path,
    file_sha256,
    persist_checkpoint_manifest,
)
from watchlist_schema import validate_watchlist
from daily_report_delivery import write_failure_notice


CALENDAR = TradingCalendar(holidays=set())
DATE = "2026-09-10"


def _workflow_step_body(workflow: str, step_name: str) -> str:
    marker = f"      - name: {step_name}\n"
    start = workflow.index(marker)
    run_marker = "        run: |\n"
    body_start = workflow.index(run_marker, start) + len(run_marker)
    body_end = workflow.find("\n      - name:", body_start)
    assert body_end != -1
    return "\n".join(line[10:] for line in workflow[body_start:body_end].splitlines())


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_runtime_git_repo(path: Path) -> None:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "core.autocrlf", "false")
    _git(path, "config", "user.name", "runtime-state-test")
    _git(path, "config", "user.email", "runtime-state-test@example.invalid")
    (path / "RUNTIME_STATE.md").write_text(
        "GITHUB_ACTIONS_DAILY_RUNTIME_V1\noperational state only\n",
        encoding="utf-8",
    )
    _git(path, "add", "--", "RUNTIME_STATE.md")
    _git(path, "commit", "-m", "base runtime state")


def _workflow_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily_t_close.yml"


def _marker(state_root: Path) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "RUNTIME_STATE.md").write_text(
        """# Runtime state

GITHUB_ACTIONS_DAILY_RUNTIME_V1

- this branch is operational state only
- never merge into master
- cloud workflow is the normal single writer
- local devices are read-only consumers unless explicit recovery
- no secrets
- no raw market evidence
- no generation input packages
""",
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> tuple[Path, dict, dict]:
    data_root = tmp_path / "source-data"
    paths = DataPaths(data_root)
    data_root.mkdir(parents=True)
    payload = validate_watchlist(
        {
            "date": DATE,
            "mode": "close",
            "market_env": {},
            "sectors": [],
            "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
            "universe_policy": "ASHARE_MAIN_BOARD_ONLY_V1",
            "candidates": [
                {
                    "code": "600519",
                    "name": "测试股份",
                    "buy_type": "B 突破回踩",
                    "setup": "B_BREAKOUT_RETEST",
                    "score": 80.0,
                    "price": 100.0,
                    "trigger": 100.0,
                    "stop": 95.0,
                    "target": 110.0,
                    "rr": 2.0,
                }
            ],
        }
    )
    watchlist_path = paths.watchlist_file(DATE)
    watchlist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tracker = new_tracker()
    candidate = payload["candidates"][0]
    tracker["signals"][candidate["signal_id"]] = _signal_from_candidate(payload, candidate, CALENDAR)
    save_tracker(tracker, paths.perf_tracker_file())

    paths.reports_dir().mkdir(parents=True)
    (paths.reports_dir() / f"daily_close_{DATE.replace('-', '')}.html").write_text("<html>dated</html>\n", encoding="utf-8")
    (paths.reports_dir() / "latest.html").write_text("<html>latest</html>\n", encoding="utf-8")
    (paths.reports_dir() / "perf_report.md").write_text("# report\n", encoding="utf-8")
    save_store(new_store(), paths.root / "shadow_monitor")

    manifest = build_daily_checkpoint_manifest(
        DATE,
        data_root=data_root,
        calendar=CALENDAR,
        code_git_sha="a" * 40,
    )
    persist_checkpoint_manifest(manifest, checkpoint_manifest_path(data_root, DATE))
    return data_root, payload, tracker


def _write_daily_watchlist_and_report(data_root: Path, list_date: str, code: str) -> dict:
    paths = DataPaths(data_root)
    payload = validate_watchlist(
        {
            "date": list_date,
            "mode": "close",
            "market_env": {},
            "sectors": [],
            "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
            "universe_policy": "ASHARE_MAIN_BOARD_ONLY_V1",
            "candidates": [
                {
                    "code": code,
                    "name": f"测试股份{code[-2:]}",
                    "buy_type": "B 突破回踩",
                    "setup": "B_BREAKOUT_RETEST",
                    "score": 80.0,
                    "price": 100.0,
                    "trigger": 100.0,
                    "stop": 95.0,
                    "target": 110.0,
                    "rr": 2.0,
                }
            ],
        }
    )
    paths.watchlist_file(list_date).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths.reports_dir().mkdir(parents=True, exist_ok=True)
    token = list_date.replace("-", "")
    (paths.reports_dir() / f"daily_close_{token}.html").write_text(
        f"<html>dated {list_date}</html>\n",
        encoding="utf-8",
    )
    return payload


def _two_day_fixture(tmp_path: Path) -> tuple[Path, str, str, dict, dict]:
    data_root = tmp_path / "two-day-data"
    data_root.mkdir()
    d1 = "2026-09-09"
    d2 = "2026-09-10"
    d1_payload = _write_daily_watchlist_and_report(data_root, d1, "600519")
    paths = DataPaths(data_root)
    tracker = new_tracker()
    d1_candidate = d1_payload["candidates"][0]
    tracker["signals"][d1_candidate["signal_id"]] = _signal_from_candidate(
        d1_payload, d1_candidate, CALENDAR
    )
    save_tracker(tracker, paths.perf_tracker_file())
    (paths.reports_dir() / "latest.html").write_text(
        f"<html>latest {d1}</html>\n", encoding="utf-8"
    )
    save_store(new_store(), paths.root / "shadow_monitor")

    d1_manifest = build_daily_checkpoint_manifest(
        d1,
        data_root=data_root,
        calendar=CALENDAR,
        code_git_sha="a" * 40,
    )
    persist_checkpoint_manifest(d1_manifest, checkpoint_manifest_path(data_root, d1))

    d2_payload = _write_daily_watchlist_and_report(data_root, d2, "600520")
    d2_candidate = d2_payload["candidates"][0]
    tracker["signals"][d2_candidate["signal_id"]] = _signal_from_candidate(
        d2_payload, d2_candidate, CALENDAR
    )
    tracker["updated"] = f"{d2}T15:00:00+08:00"
    save_tracker(tracker, paths.perf_tracker_file())
    (paths.reports_dir() / "latest.html").write_text(
        f"<html>latest {d2}</html>\n", encoding="utf-8"
    )
    return data_root, d1, d2, d1_payload, d2_payload


def test_allowlist_contains_only_durable_files_and_excludes_raw_inputs(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    (data_root / "t_close_evidence").mkdir()
    (data_root / "t_close_evidence" / "capture.raw").write_bytes(b"raw")
    (data_root / "prospective_inputs").mkdir()
    (data_root / "prospective_inputs" / "input.json").write_text("{}", encoding="utf-8")
    (data_root / "development_candidate").mkdir()
    (data_root / "development_candidate" / "run_manifest.json").write_text("{}", encoding="utf-8")

    relative = {path.as_posix() for _path, path in allowlisted_data_files(data_root)}

    assert "watchlist_20260910.json" in relative
    assert "perf_tracker.json" in relative
    assert "shadow_monitor/b_shadow_monitor.json" in relative
    assert "reports/perf_report.md" in relative
    assert "checkpoints/daily_checkpoint_20260910.json" in relative
    assert all("t_close_evidence" not in item for item in relative)
    assert all("prospective_inputs" not in item for item in relative)
    assert all("development_candidate" not in item for item in relative)


def test_no_valid_input_diagnostic_is_allowlisted_and_persisted_without_formal_watchlist(tmp_path):
    data_root = tmp_path / "diagnostic-data"
    (data_root / "diagnostics").mkdir(parents=True)
    (data_root / "reports").mkdir(parents=True)
    token = DATE.replace("-", "")
    diagnostic_path = data_root / "diagnostics" / f"daily_input_diagnostic_{token}.json"
    report_path = data_root / "reports" / f"daily_close_{token}.html"
    diagnostic_path.write_text(
        json.dumps(
            {
                "schema_version": "DAILY_INPUT_DIAGNOSTIC_V1",
                "target_date": DATE,
                "coverage_status": "NO_VALID_INPUT",
                "formal_result_valid": False,
                "exclusions": [],
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(f"<html>NO_VALID_INPUT {DATE}</html>\n", encoding="utf-8")

    assert _is_allowlisted_data_relative(Path("diagnostics") / diagnostic_path.name)
    state_root = tmp_path / "diagnostic-runtime-state"
    _marker(state_root)

    persisted = persist_input_diagnostic(state_root, data_root, DATE)

    assert persisted["status"] == "INPUT_DIAGNOSTIC_READY_TO_COMMIT"
    assert f"data/diagnostics/daily_input_diagnostic_{token}.json" in persisted["copied"]
    assert f"data/reports/daily_close_{token}.html" in persisted["copied"]
    assert validate_state_tree(state_root)["raw_persisted"] is False


def test_no_valid_input_actions_summary_marks_diagnostic_not_formal_success(tmp_path):
    data_root = tmp_path / "summary-data"
    report_path = data_root / "reports" / f"daily_close_{DATE.replace('-', '')}.html"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(f"<html>NO_VALID_INPUT {DATE}</html>\n", encoding="utf-8")

    summary = build_summary(
        data_root,
        DATE,
        status="NO_VALID_INPUT",
        state_commit="a" * 40,
        result={
            "status": "NO_VALID_INPUT",
            "formal_result_valid": False,
            "diagnostic_report": str(report_path),
            "input_coverage": {
                "coverage_status": "NO_VALID_INPUT",
                "excluded_symbol_count": 4,
            },
        },
    )

    assert "- Status: NO_VALID_INPUT" in summary
    assert "- Input coverage: NO_VALID_INPUT" in summary
    assert "- Formal result valid: NO" in summary
    assert "- Report: DIAGNOSTIC_READY" in summary


def test_historical_checkpoint_survives_legal_tracker_and_latest_report_advance(tmp_path):
    data_root, d1, _d2, _d1_payload, _d2_payload = _two_day_fixture(tmp_path)
    paths = DataPaths(data_root)
    manifest = json.loads(
        (paths.root / "checkpoints" / f"daily_checkpoint_{d1.replace('-', '')}.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["perf_tracker"]["sha256"] != file_sha256(paths.perf_tracker_file())
    assert manifest["latest_html"]["sha256"] != file_sha256(paths.reports_dir() / "latest.html")

    result = validate_runtime_data(data_root)

    assert result["status"] == "RUNTIME_STATE_VALID"
    assert result["checkpoint_count"] == 1
    assert result["current_watchlist_count"] == 2
    assert result["current_tracker_signal_count"] == 2


@pytest.mark.parametrize("mutated_payload", ["perf_tracker", "latest_html"])
def test_current_day_checkpoint_remains_strict_for_mutable_payloads(tmp_path, mutated_payload):
    data_root, _d1, d2, _d1_payload, _d2_payload = _two_day_fixture(tmp_path)
    paths = DataPaths(data_root)
    manifest = build_daily_checkpoint_manifest(
        d2,
        data_root=data_root,
        calendar=CALENDAR,
        code_git_sha="b" * 40,
    )
    persist_checkpoint_manifest(manifest, checkpoint_manifest_path(data_root, d2))
    assert completed_run_status(data_root, d2)["status"] == ALREADY_COMPLETED

    if mutated_payload == "perf_tracker":
        tracker = load_tracker(paths.perf_tracker_file())
        tracker["updated"] = f"{d2}T15:01:00+08:00"
        save_tracker(tracker, paths.perf_tracker_file())
    else:
        (paths.reports_dir() / "latest.html").write_text(
            "<html>latest mutated after checkpoint</html>\n", encoding="utf-8"
        )

    result = completed_run_status(data_root, d2)

    assert result["status"] == INCOMPLETE_SAME_DAY_STATE
    assert mutated_payload in result["reason"]


def test_degraded_checkpoint_and_report_bind_the_same_input_coverage(tmp_path):
    data_root, payload, _tracker = _fixture(tmp_path)
    coverage = {
        "schema_version": "INPUT_COVERAGE_V1",
        "coverage_status": "DEGRADED",
        "evaluated_symbol_count": 2,
        "excluded_symbol_count": 1,
        "excluded_symbols": [
            {
                "symbol": "605366",
                "provider_symbol": "605366.SH",
                "target_date": DATE,
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
    payload["input_coverage"] = coverage
    watchlist_path = DataPaths(data_root).watchlist_file(DATE)
    watchlist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage_json = json.dumps(coverage, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    dated_path = DataPaths(data_root).reports_dir() / f"daily_close_{DATE.replace('-', '')}.html"
    dated_path.write_text(
        f'<meta name="input-coverage-json" content="{escape(coverage_json, quote=True)}">\n',
        encoding="utf-8",
    )
    checkpoint_manifest_path(data_root, DATE).unlink()

    manifest = build_daily_checkpoint_manifest(
        DATE,
        data_root=data_root,
        calendar=CALENDAR,
        code_git_sha="a" * 40,
    )
    persist_checkpoint_manifest(manifest, checkpoint_manifest_path(data_root, DATE))

    assert validate_runtime_data(data_root)["status"] == "RUNTIME_STATE_VALID"
    completion = completed_run_status(data_root, DATE)
    assert completion["status"] == ALREADY_COMPLETED
    assert completion["input_coverage"] == coverage

    mismatched = {
        "schema_version": "INPUT_COVERAGE_V1",
        "coverage_status": "COMPLETE",
        "evaluated_symbol_count": 2,
        "excluded_symbol_count": 0,
        "excluded_symbols": [],
        "policy_version": "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
    }
    mismatch_json = json.dumps(mismatched, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    dated_path.write_text(
        f'<meta name="input-coverage-json" content="{escape(mismatch_json, quote=True)}">\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeStateError, match="report input coverage mismatch"):
        validate_runtime_data(data_root)
    assert completed_run_status(data_root, DATE)["status"] == INCOMPLETE_SAME_DAY_STATE


@pytest.mark.parametrize("corruption", ["schema", "list_date", "filename", "dated_watchlist"])
def test_historical_checkpoint_corruption_still_fails_closed(tmp_path, corruption):
    data_root, d1, _d2, _d1_payload, _d2_payload = _two_day_fixture(tmp_path)
    paths = DataPaths(data_root)
    manifest_path = paths.root / "checkpoints" / f"daily_checkpoint_{d1.replace('-', '')}.json"

    if corruption == "filename":
        manifest_path.rename(paths.root / "checkpoints" / "daily_checkpoint_20260911.json")
    elif corruption == "dated_watchlist":
        watchlist_path = paths.watchlist_file(d1)
        watchlist_path.write_bytes(watchlist_path.read_bytes() + b"\n")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if corruption == "schema":
            manifest["schema_version"] = "BROKEN_CHECKPOINT_SCHEMA"
        else:
            manifest["list_date"] = "2026-09-08"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeStateError):
        validate_runtime_data(data_root)


def test_two_consecutive_production_day_lifecycle_validates_and_completes(tmp_path):
    data_root, _d1, d2, _d1_payload, _d2_payload = _two_day_fixture(tmp_path)
    manifest = build_daily_checkpoint_manifest(
        d2,
        data_root=data_root,
        calendar=CALENDAR,
        code_git_sha="c" * 40,
    )
    persist_checkpoint_manifest(manifest, checkpoint_manifest_path(data_root, d2))

    validation = validate_runtime_data(data_root)
    completion = completed_run_status(data_root, d2)

    assert validation["status"] == "RUNTIME_STATE_VALID"
    assert validation["checkpoint_count"] == 2
    assert completion["status"] == ALREADY_COMPLETED


def test_bootstrap_reuses_historical_checkpoint_after_mutable_state_advances(tmp_path):
    data_root, d1, _d2, _d1_payload, _d2_payload = _two_day_fixture(tmp_path)
    state_root = tmp_path / "runtime-state"
    _marker(state_root)

    result = bootstrap_allowlist(state_root, data_root)

    assert result["skipped_checkpoints"] == {}
    assert f"data/checkpoints/daily_checkpoint_{d1.replace('-', '')}.json" in result["copied"]


def test_persist_and_restore_preserve_watchlist_tracker_shadow_and_reports(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    state_root = tmp_path / "runtime-state"
    _marker(state_root)

    persisted = persist_allowlist(state_root, data_root)
    assert persisted["status"] == "RUNTIME_STATE_READY_TO_COMMIT"
    assert persisted["raw_persisted"] is False
    assert validate_state_tree(state_root)["raw_persisted"] is False

    restored = tmp_path / "restored-data"
    result = restore_allowlist(state_root, restored)
    assert result["status"] == "RUNTIME_STATE_RESTORED"
    for source, relative in allowlisted_data_files(data_root):
        assert (restored / relative).read_bytes() == source.read_bytes()
    assert validate_runtime_data(restored)["provider_calls"] == 0


def test_failure_notice_is_dated_allowlisted_operational_state_and_does_not_complete_a_run(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    write_failure_notice(
        data_root,
        {
            "schema_version": "DAILY_FAILURE_NOTICE_V1",
            "report_date": DATE,
            "target_date": DATE,
            "first_failure_stage": "production",
            "error_summary": "PRODUCTION_RUNTIME_FAILURE",
            "email_status": "SUCCESS",
            "bark_status": "FAILED",
            "first_attempt_at_bjt": "2026-09-10T17:31:42+08:00",
            "last_attempt_at_bjt": "2026-09-10T17:31:42+08:00",
            "email_sent_at_bjt": "2026-09-10T17:31:42+08:00",
            "bark_sent_at_bjt": None,
            "run_url": "https://github.com/EFSing/ashare_watchlist/actions/runs/1",
        },
    )
    assert _is_allowlisted_data_relative(Path("delivery/daily_failure_notice_20260910.json"))
    assert not _is_allowlisted_data_relative(Path("delivery/daily_failure_notice_latest.json"))

    state_root = tmp_path / "runtime-state"
    _marker(state_root)
    persist_allowlist(state_root, data_root)
    result = persist_failure_notice(state_root, data_root, DATE)

    assert result["status"] == "FAILURE_NOTICE_READY_TO_COMMIT"
    assert (state_root / "data" / "delivery" / "daily_failure_notice_20260910.json").is_file()
    assert completed_run_status(data_root, DATE)["status"] == ALREADY_COMPLETED

    restored = tmp_path / "restored-data"
    restore_allowlist(state_root, restored)
    assert validate_runtime_data(restored)["failure_notice_count"] == 1
    assert completed_run_status(restored, DATE)["status"] == ALREADY_COMPLETED

    (state_root / "data" / "delivery" / "daily_failure_notice_latest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeStateError, match="non-allowlisted"):
        validate_state_tree(state_root)


def test_state_tree_rejects_non_allowlisted_files(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    state_root = tmp_path / "runtime-state"
    _marker(state_root)
    persist_allowlist(state_root, data_root)
    forbidden = state_root / "data" / "t_close_evidence" / "capture.raw"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_bytes(b"must not persist")

    with pytest.raises(RuntimeStateError, match="non-allowlisted"):
        validate_state_tree(state_root)


def test_persist_requires_source_and_state_trees_to_be_separate(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    _marker(data_root)

    with pytest.raises(RuntimeStateError, match="separate"):
        persist_allowlist(data_root, data_root)


def test_completed_run_requires_the_dated_checkpoint_not_just_a_watchlist(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)

    complete = completed_run_status(data_root, DATE)
    assert complete["status"] == ALREADY_COMPLETED
    assert complete["provider_calls"] == 0

    (data_root / "checkpoints" / "daily_checkpoint_20260910.json").unlink()
    partial = completed_run_status(data_root, DATE)
    assert partial["status"] == INCOMPLETE_SAME_DAY_STATE
    assert partial["missing"]


def test_completed_run_rejects_partial_dated_html_state(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    (data_root / "reports" / "daily_close_20260910.html").unlink()

    result = completed_run_status(data_root, DATE)

    assert result["status"] == INCOMPLETE_SAME_DAY_STATE
    assert any("daily_close_20260910.html" in item for item in result["missing"])


def test_runtime_validation_rejects_empty_prospective_tracker(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    save_tracker(new_tracker(), DataPaths(data_root).perf_tracker_file())

    with pytest.raises(RuntimeStateError, match="tracker is empty"):
        validate_runtime_data(data_root)


def test_summary_is_secret_free_and_declares_raw_and_oos_boundaries(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)

    summary = build_summary(
        data_root,
        DATE,
        status=ALREADY_COMPLETED,
        state_commit="b" * 40,
    )

    assert "A股每日云端运行" in summary
    assert "ASHARE_MAIN_BOARD_ONLY_V1" in summary
    assert "raw persisted: NO" in summary
    assert "prospective input persisted: NO" in summary
    assert "Final OOS read: NO" in summary
    assert "b" * 40 in summary
    assert "HITHINK_FINANCE_API_KEY" not in summary


def test_checkpoint_restore_does_not_copy_unknown_data_files(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    unknown = data_root / "positions.json"
    unknown.write_text("{\"local\": true}\n", encoding="utf-8")
    state_root = tmp_path / "runtime-state"
    _marker(state_root)

    persist_allowlist(state_root, data_root)

    assert not (state_root / "data" / "positions.json").exists()


def test_durable_state_metadata_does_not_add_device_specific_data_root(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    state_root = tmp_path / "runtime-state"
    _marker(state_root)

    persist_allowlist(state_root, data_root)

    for path in (state_root / "data").rglob("*"):
        if path.is_file():
            assert str(data_root) not in path.read_text(encoding="utf-8", errors="ignore")


def test_bootstrap_omits_legacy_non_b_watchlists(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    legacy = validate_watchlist(
        {
            "date": "2026-08-20",
            "mode": "close",
            "market_env": {},
            "sectors": [],
            "candidates": [],
        }
    )
    DataPaths(data_root).watchlist_file("20260820").write_text(
        json.dumps(legacy), encoding="utf-8"
    )
    state_root = tmp_path / "runtime-state"
    _marker(state_root)

    result = bootstrap_allowlist(state_root, data_root)

    assert "data/watchlist_20260820.json" in result["skipped"]
    assert not (state_root / "data" / "watchlist_20260820.json").exists()


def test_restore_rejects_conflicting_existing_bytes(tmp_path):
    data_root, _payload, _tracker = _fixture(tmp_path)
    state_root = tmp_path / "runtime-state"
    _marker(state_root)
    persist_allowlist(state_root, data_root)
    restored = tmp_path / "restored-data"
    restored.mkdir()
    (restored / "perf_tracker.json").write_bytes(b"different")

    with pytest.raises(RuntimeStateError, match="conflicts"):
        restore_allowlist(state_root, restored)


def test_workflow_declares_linux_schedule_token_permissions_and_no_broad_stage():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily_t_close.yml").read_text(encoding="utf-8")

    assert 'runs-on: ubuntu-latest' in workflow
    assert 'python-version: "3.11"' in workflow
    assert 'pip install -e ".[test]"' in workflow
    assert 'timeout-minutes: 120' in workflow
    assert '17 10 * * 1-5' in workflow
    assert '17 11 * * 1-5' in workflow
    assert 'contents: write' in workflow
    assert 'ref: runtime-state' in workflow
    assert 'git add .' not in workflow
    assert 'git add -A' not in workflow
    assert 'C:\\Users\\' not in workflow


def test_runtime_state_commit_gate_preserves_allowlist_idempotency_and_delivery_order():
    workflow = _workflow_path().read_text(encoding="utf-8")
    commit_gate = _workflow_step_body(workflow, "Atomically commit and push runtime-state with GITHUB_TOKEN")
    receipt_gate = _workflow_step_body(workflow, "Persist delivery receipt to runtime-state")

    assert 'mapfile -t stage_paths < <(python scripts/cloud_runtime_state.py list --state-root "$GITHUB_WORKSPACE/runtime-state" --paths-only)' in commit_gate
    assert '(cd runtime-state && git add -- "${stage_paths[@]}")' in commit_gate
    assert 'git -C runtime-state diff --cached --check' not in commit_gate
    assert 'unexpected="$(git -C runtime-state diff --cached --name-only' in commit_gate
    assert 'if [[ -n "$unexpected" ]]; then' in commit_gate
    assert 'echo "unexpected staged runtime-state paths: $unexpected"' in commit_gate
    assert 'git -C runtime-state diff --cached --quiet' in commit_gate
    assert 'git -C runtime-state config user.name "github-actions[bot]"' in commit_gate
    assert 'git -C runtime-state config user.email "41898282+github-actions[bot]@users.noreply.github.com"' in commit_gate
    assert 'git -C runtime-state push origin HEAD:runtime-state' in commit_gate
    assert 'echo "RUNTIME_STATE_SHA=$state_sha" >> "$GITHUB_ENV"' in commit_gate
    assert 'echo "PRODUCTION_CANONICAL_READY=1" >> "$GITHUB_ENV"' in commit_gate
    assert 'echo "RUNTIME_STATE_PERSISTED=YES" >> "$GITHUB_ENV"' in commit_gate

    assert 'git -C runtime-state diff --cached --check' in receipt_gate
    assert workflow.index("Validate production outputs before state copy") < workflow.index(
        "Copy allowlisted durable outputs into runtime-state checkout"
    ) < workflow.index("Atomically commit and push runtime-state with GITHUB_TOKEN") < workflow.index(
        "Deliver production report by Email and Bark"
    )


def test_runtime_state_commit_gate_commits_allowlisted_html_without_whitespace_lint(tmp_path):
    state_root = tmp_path / "runtime-state"
    _init_runtime_git_repo(state_root)
    relative = Path("data/reports/daily_close_20260914.html")
    payload = b"<!doctype html>\n<div>generated output </div> \n"
    html_path = state_root / relative
    html_path.parent.mkdir(parents=True)
    html_path.write_bytes(payload)

    allowlisted = allowlisted_data_files(state_root / "data")
    assert [path.relative_to(state_root / "data").as_posix() for path, _relative in allowlisted] == [
        "reports/daily_close_20260914.html"
    ]
    stage_paths = ["RUNTIME_STATE.md", relative.as_posix()]
    _git(state_root, "add", "--", *stage_paths)

    whitespace_check = subprocess.run(
        ["git", "diff", "--cached", "--check"],
        cwd=state_root,
        capture_output=True,
        text=True,
    )
    assert whitespace_check.returncode != 0
    assert "trailing whitespace" in whitespace_check.stdout + whitespace_check.stderr
    assert _git(state_root, "diff", "--cached", "--name-only").stdout.splitlines() == [relative.as_posix()]

    _git(state_root, "commit", "-m", "runtime: persist generated report")
    assert html_path.read_bytes() == payload
    committed = subprocess.run(
        ["git", "show", f"HEAD:{relative.as_posix()}"],
        cwd=state_root,
        check=True,
        capture_output=True,
    )
    assert committed.stdout == payload


def test_runtime_state_commit_gate_remains_fail_closed_for_unexpected_staged_path(tmp_path):
    workflow = _workflow_path().read_text(encoding="utf-8")
    commit_gate = _workflow_step_body(workflow, "Atomically commit and push runtime-state with GITHUB_TOKEN")
    assert 'if [[ -n "$unexpected" ]]; then' in commit_gate
    assert 'exit 1' in commit_gate[commit_gate.index('if [[ -n "$unexpected" ]]; then') :]

    state_root = tmp_path / "runtime-state"
    _init_runtime_git_repo(state_root)
    allowed = Path("data/reports/daily_close_20260914.html")
    unexpected = Path("data/unexpected.txt")
    (state_root / allowed).parent.mkdir(parents=True)
    (state_root / allowed).write_text("generated\n", encoding="utf-8")
    (state_root / unexpected).write_text("must fail closed\n", encoding="utf-8")
    stage_paths = ["RUNTIME_STATE.md", allowed.as_posix()]

    _git(state_root, "add", "--", unexpected.as_posix())
    _git(state_root, "add", "--", *stage_paths)
    staged = set(_git(state_root, "diff", "--cached", "--name-only").stdout.splitlines())

    assert staged - set(stage_paths) == {unexpected.as_posix()}
