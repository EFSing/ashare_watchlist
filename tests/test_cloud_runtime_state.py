from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from b_shadow_monitor import new_store, save_store
from cloud_runtime_state import (
    ALREADY_COMPLETED,
    INCOMPLETE_SAME_DAY_STATE,
    RuntimeStateError,
    allowlisted_data_files,
    bootstrap_allowlist,
    build_summary,
    completed_run_status,
    persist_allowlist,
    restore_allowlist,
    validate_runtime_data,
    validate_state_tree,
)
from data_paths import DataPaths
from track_perf import _signal_from_candidate, new_tracker, save_tracker
from trading_calendar import TradingCalendar
from upload_daily_checkpoint import (
    build_daily_checkpoint_manifest,
    checkpoint_manifest_path,
    persist_checkpoint_manifest,
)
from watchlist_schema import validate_watchlist


CALENDAR = TradingCalendar(holidays=set())
DATE = "2026-09-10"


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
