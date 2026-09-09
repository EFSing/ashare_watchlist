from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import t_close_runner as runner
from data_paths import DataPaths
from trading_calendar import TradingCalendar
from upload_daily_checkpoint import (
    CLOUD_CHECKPOINT_CONFLICT,
    CLOUD_CHECKPOINT_FAILED,
    DAILY_KEEP,
    FORMAL_KEEP,
    NO_OP_ALREADY_VERIFIED,
    REDUNDANT_INTERMEDIATE_CANDIDATE,
    UNKNOWN_DO_NOT_DELETE,
    RemoteEntry,
    build_daily_checkpoint_manifest,
    checkpoint_manifest_path,
    classify_inventory,
    file_sha256,
    persist_checkpoint_manifest,
    restore_lightweight_checkpoint,
    upload_checkpoint,
)


DATE = "2026-09-08"
CODE_SHA = "a" * 40
CALENDAR = TradingCalendar(holidays=set())


class FakeDrive:
    def __init__(self) -> None:
        self.entries: dict[str, list[RemoteEntry]] = {"root": []}
        self.contents: dict[str, bytes] = {}
        self.parents: dict[str, str] = {}
        self.events: list[tuple[str, str]] = []
        self._counter = 0

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def list_folder(self, folder_id: str):
        self.events.append(("list", folder_id))
        return list(self.entries.get(folder_id, []))

    def create_folder(self, name: str, parent_folder_id: str):
        folder = RemoteEntry(self._id("folder"), name, is_folder=True)
        self.entries.setdefault(parent_folder_id, []).append(folder)
        self.entries[folder.id] = []
        self.parents[folder.id] = parent_folder_id
        self.events.append(("create_folder", name))
        return folder

    def upload_file(self, local_path: Path, file_name: str, parent_folder_id: str):
        if getattr(self, "fail_on_upload", None) == file_name:
            raise OSError(f"simulated upload failure for {file_name}")
        file_id = self._id("file")
        payload = Path(local_path).read_bytes()
        entry = RemoteEntry(file_id, file_name, size=len(payload))
        self.entries.setdefault(parent_folder_id, []).append(entry)
        self.contents[file_id] = payload
        self.parents[file_id] = parent_folder_id
        self.events.append(("upload", file_name))
        return entry

    def read_file_bytes(self, file_id: str) -> bytes:
        self.events.append(("read", file_id))
        return self.contents[file_id]

    def files_in(self, folder_id: str) -> list[RemoteEntry]:
        return list(self.entries[folder_id])


def _write_operational_files(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    paths = DataPaths(data_root)
    data_root.mkdir(parents=True)
    paths.watchlist_file(DATE).write_text(
        json.dumps(
            {
                "date": "2026-09-08",
                "mode": "close",
                "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
                "market_env": {},
                "sectors": [],
                "candidates": [{"code": "600519", "score": 60}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paths.perf_tracker_file().write_bytes(b'{"signals": {}}\n')
    paths.reports_dir().mkdir(parents=True)
    (paths.reports_dir() / "daily_close_20260908.html").write_bytes(b"<html>dated</html>\n")
    (paths.reports_dir() / "latest.html").write_bytes(b"<html>latest</html>\n")
    return data_root


def _prepared(tmp_path: Path):
    data_root = _write_operational_files(tmp_path)
    manifest = build_daily_checkpoint_manifest(
        DATE,
        data_root=data_root,
        calendar=CALENDAR,
        code_git_sha=CODE_SHA,
    )
    manifest_path = checkpoint_manifest_path(data_root, DATE)
    persist = persist_checkpoint_manifest(manifest, manifest_path)
    return data_root, manifest, manifest_path, persist


def _upload(tmp_path: Path) -> tuple[Path, dict, Path, FakeDrive, dict]:
    data_root, manifest, manifest_path, _ = _prepared(tmp_path)
    client = FakeDrive()
    result = upload_checkpoint(
        manifest,
        data_root=data_root,
        client=client,
        root_folder_id="root",
        manifest_path=manifest_path,
    )
    return data_root, manifest, manifest_path, client, result


def test_manifest_records_exact_hashes_and_stable_identity(tmp_path):
    data_root, manifest, path, persisted = _prepared(tmp_path)

    assert manifest["schema_version"] == "DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT_V1"
    assert manifest["list_date"] == DATE
    assert manifest["earliest_execution"] == "2026-09-09"
    assert manifest["watchlist"]["sha256"] == file_sha256(data_root / "watchlist_20260908.json")
    assert persisted["sha256"] == file_sha256(path)
    assert manifest["created_at_bjt"] == "2026-09-08T15:00:00+08:00"


def test_same_date_same_sha_is_noop_and_does_not_duplicate_remote_files(tmp_path):
    data_root, manifest, manifest_path, client, first = _upload(tmp_path)
    upload_events_before = [event for event in client.events if event[0] == "upload"]

    second = upload_checkpoint(
        manifest,
        data_root=data_root,
        client=client,
        root_folder_id="root",
        manifest_path=manifest_path,
    )
    upload_events_after = [event for event in client.events if event[0] == "upload"]

    assert first["uploaded_file_count"] == 6
    assert second["uploaded_file_count"] == 0
    assert second["no_op_file_count"] == 6
    assert all(item["status"] == NO_OP_ALREADY_VERIFIED for item in second["files"].values())
    assert upload_events_after == upload_events_before
    assert sum(entry.name == "daily_checkpoint_20260908.json" for entries in client.entries.values() for entry in entries) == 1


def test_different_sha_for_same_logical_file_fails_closed(tmp_path):
    data_root, manifest, manifest_path, client, _ = _upload(tmp_path)
    watchlist = data_root / "watchlist_20260908.json"
    changed_payload = json.loads(watchlist.read_text(encoding="utf-8"))
    changed_payload["candidates"][0]["score"] = 61
    watchlist.write_text(json.dumps(changed_payload), encoding="utf-8")
    changed = build_daily_checkpoint_manifest(DATE, data_root=data_root, calendar=CALENDAR, code_git_sha=CODE_SHA)
    changed_path = tmp_path / "changed_manifest.json"
    persist_checkpoint_manifest(changed, changed_path)

    with pytest.raises(Exception, match=CLOUD_CHECKPOINT_CONFLICT):
        upload_checkpoint(
            changed,
            data_root=data_root,
            client=client,
            root_folder_id="root",
            manifest_path=changed_path,
        )


def test_remote_layout_uses_fixed_date_and_latest_locations(tmp_path):
    _data_root, _manifest, _path, client, result = _upload(tmp_path)
    folders = {entry.name for entries in client.entries.values() for entry in entries if entry.is_folder}
    assert {"daily_checkpoints", "20260908", "latest"}.issubset(folders)
    assert not any(name.startswith("latest_") and name != "latest" for name in folders)
    assert result["remote_deletes"] == 0


def test_failure_does_not_modify_canonical_tracker_or_html(tmp_path):
    data_root, manifest, manifest_path, _ = _prepared(tmp_path)
    before = {
        "tracker": (data_root / "perf_tracker.json").read_bytes(),
        "dated_html": (data_root / "reports" / "daily_close_20260908.html").read_bytes(),
        "latest_html": (data_root / "reports" / "latest.html").read_bytes(),
    }
    client = FakeDrive()
    client.fail_on_upload = "daily_close_20260908.html"

    with pytest.raises(OSError, match="simulated upload failure"):
        upload_checkpoint(
            manifest,
            data_root=data_root,
            client=client,
            root_folder_id="root",
            manifest_path=manifest_path,
        )

    assert (data_root / "perf_tracker.json").read_bytes() == before["tracker"]
    assert (data_root / "reports" / "daily_close_20260908.html").read_bytes() == before["dated_html"]
    assert (data_root / "reports" / "latest.html").read_bytes() == before["latest_html"]


def test_dated_files_are_verified_before_latest_upload(tmp_path):
    _data_root, _manifest, _path, client, _result = _upload(tmp_path)
    uploads = [name for kind, name in client.events if kind == "upload"]
    assert uploads == [
        "watchlist_20260908.json",
        "perf_tracker.json",
        "daily_close_20260908.html",
        "daily_checkpoint_20260908.json",
        "latest.html",
        "latest_checkpoint.json",
    ]


def test_dated_manifest_waits_for_first_three_readbacks(tmp_path):
    data_root, manifest, manifest_path, _persisted = _prepared(tmp_path)

    class ReadbackFailDrive(FakeDrive):
        def __init__(self):
            super().__init__()
            self.failed = False

        def read_file_bytes(self, file_id: str) -> bytes:
            if not self.failed:
                self.failed = True
                raise OSError("simulated readback failure")
            return super().read_file_bytes(file_id)

    client = ReadbackFailDrive()
    with pytest.raises(OSError, match="simulated readback failure"):
        upload_checkpoint(
            manifest,
            data_root=data_root,
            client=client,
            root_folder_id="root",
            manifest_path=manifest_path,
        )

    uploads = [name for kind, name in client.events if kind == "upload"]
    assert uploads == ["watchlist_20260908.json"]
    assert "daily_checkpoint_20260908.json" not in uploads
    assert "latest.html" not in uploads
    assert "latest_checkpoint.json" not in uploads


def test_latest_failure_leaves_dated_checkpoint_intact(tmp_path):
    data_root, manifest, manifest_path, _persisted = _prepared(tmp_path / "latest-failure")
    client = FakeDrive()
    client.fail_on_upload = "latest.html"

    with pytest.raises(OSError, match="simulated upload failure"):
        upload_checkpoint(
            manifest,
            data_root=data_root,
            client=client,
            root_folder_id="root",
            manifest_path=manifest_path,
        )

    dated_folder = next(
        entry
        for entries in client.entries.values()
        for entry in entries
        if entry.is_folder and entry.name == "20260908"
    )
    latest_folder = next(
        entry
        for entries in client.entries.values()
        for entry in entries
        if entry.is_folder and entry.name == "latest"
    )
    assert {entry.name for entry in client.entries[dated_folder.id]} == {
        "watchlist_20260908.json",
        "perf_tracker.json",
        "daily_close_20260908.html",
        "daily_checkpoint_20260908.json",
    }
    assert client.entries[latest_folder.id] == []


def test_restore_verifies_manifest_and_all_dated_bytes(tmp_path):
    data_root, manifest, _path, client, _result = _upload(tmp_path)
    restore_dir = tmp_path / "recovery"
    result = restore_lightweight_checkpoint(
        DATE,
        client=client,
        root_folder_id="root",
        output_dir=restore_dir,
    )

    assert result["status"] == "LIGHTWEIGHT_CLOUD_RECOVERY_VERIFIED"
    assert json.loads((restore_dir / "daily_checkpoint_20260908.json").read_text(encoding="utf-8")) == manifest
    assert (restore_dir / "watchlist_20260908.json").read_bytes() == (data_root / "watchlist_20260908.json").read_bytes()
    assert (restore_dir / "perf_tracker.json").read_bytes() == (data_root / "perf_tracker.json").read_bytes()
    assert (restore_dir / "daily_close_20260908.html").read_bytes() == (data_root / "reports" / "daily_close_20260908.html").read_bytes()


def test_restore_sha_mismatch_fails_closed(tmp_path):
    _data_root, _manifest, _path, client, _result = _upload(tmp_path)
    date_folder = next(entry for entries in client.entries.values() for entry in entries if entry.is_folder and entry.name == "20260908")
    watchlist_entry = next(entry for entry in client.entries[date_folder.id] if entry.name == "watchlist_20260908.json")
    client.contents[watchlist_entry.id] = b"tampered"

    with pytest.raises(Exception, match="RESTORE_SHA_MISMATCH"):
        restore_lightweight_checkpoint(
            DATE,
            client=client,
            root_folder_id="root",
            output_dir=tmp_path / "recovery",
        )


def test_daily_upload_scope_excludes_evidence_and_formal_archives(tmp_path):
    data_root, manifest, manifest_path, client, result = _upload(tmp_path)
    (data_root / "t_close_evidence").mkdir()
    (data_root / "t_close_evidence" / "capture.raw").write_bytes(b"must not upload")
    (data_root / "formal_freeze.zip").write_bytes(b"must not upload")

    assert result["file_count"] == 6
    assert all("evidence" not in name.lower() and "freeze" not in name.lower() and "kline" not in name.lower() for kind, name in client.events if kind == "upload")
    assert manifest["upload_scope"] == [
        "watchlist_20260908.json",
        "perf_tracker.json",
        "daily_close_20260908.html",
        "daily_checkpoint_20260908.json",
        "latest.html",
        "latest_checkpoint.json",
    ]
    assert manifest_path.is_file()


def test_inventory_is_read_only_and_unknown_defaults_to_do_not_delete():
    entries = [
        RemoteEntry("1", "daily.html", size=10, path="ashare_watchlist/daily_checkpoints/20260908/daily.html"),
        RemoteEntry("2", "formal.bin", size=20, path="ashare_watchlist/formal/formal.bin"),
        RemoteEntry("3", "chunk-001", size=30, path="ashare_watchlist/old/chunk-001"),
        RemoteEntry("4", "mystery.bin", size=40, path="ashare_watchlist/mystery.bin"),
    ]
    report = classify_inventory(
        entries,
        formal_prefixes=("ashare_watchlist/formal/",),
        redundant_prefixes=("ashare_watchlist/old/",),
    )

    assert report["read_only"] is True
    assert report["remote_deletes"] == 0
    assert report["counts"] == {
        FORMAL_KEEP: 1,
        DAILY_KEEP: 1,
        REDUNDANT_INTERMEDIATE_CANDIDATE: 1,
        UNKNOWN_DO_NOT_DELETE: 1,
    }
    assert next(item for item in report["entries"] if item["filename"] == "mystery.bin")["classification"] == UNKNOWN_DO_NOT_DELETE


def test_manifest_does_not_change_tracker_or_html_bytes(tmp_path):
    data_root = _write_operational_files(tmp_path)
    before_tracker = (data_root / "perf_tracker.json").read_bytes()
    before_dated = (data_root / "reports" / "daily_close_20260908.html").read_bytes()
    before_latest = (data_root / "reports" / "latest.html").read_bytes()
    build_daily_checkpoint_manifest(DATE, data_root=data_root, calendar=CALENDAR, code_git_sha=CODE_SHA)

    assert (data_root / "perf_tracker.json").read_bytes() == before_tracker
    assert (data_root / "reports" / "daily_close_20260908.html").read_bytes() == before_dated
    assert (data_root / "reports" / "latest.html").read_bytes() == before_latest


def test_runner_cloud_failure_is_fail_soft_and_local_manifest_is_ready(tmp_path):
    data_root = _write_operational_files(tmp_path)
    result = runner._daily_cloud_checkpoint(DATE, data_root, tracker_failure=None)

    assert result["status"] == CLOUD_CHECKPOINT_FAILED
    assert result["reason"] == "DRIVE_CONNECTOR_NOT_CONFIGURED"
    assert Path(result["manifest_path"]).is_file()
    assert result["message"] == "[CLOUD] FAILED DRIVE_CONNECTOR_NOT_CONFIGURED"


def test_real_20260908_watchlist_sha_is_exact_when_local_artifact_is_available():
    path = Path(__file__).resolve().parents[1] / "data" / "watchlist_20260908.json"
    if not path.exists():
        pytest.skip("local 2026-09-08 operational artifact is not committed")
    assert file_sha256(path) == "f58059cd5269f8ac5cd10da357a2bd008a76ef84feaa399846d74ad7daa4b5fc"


def test_upload_result_reports_total_and_new_bytes(tmp_path):
    _data_root, _manifest, _path, _client, result = _upload(tmp_path)
    assert result["file_count"] == 6
    assert result["uploaded_file_count"] == 6
    assert result["no_op_file_count"] == 0
    assert result["uploaded_bytes"] == result["total_payload_bytes"]
    assert result["total_payload_bytes"] > 0


def test_manifest_sha_is_stable_for_same_day_retry(tmp_path):
    data_root, first, path, _ = _prepared(tmp_path)
    first_sha = file_sha256(path)
    second = build_daily_checkpoint_manifest(DATE, data_root=data_root, calendar=CALENDAR, code_git_sha=CODE_SHA)
    second_path = tmp_path / "second.json"
    persist_checkpoint_manifest(second, second_path)
    assert file_sha256(second_path) == first_sha
    assert second == first
