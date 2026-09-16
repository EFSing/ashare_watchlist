"""Build and verify the small daily operational checkpoint.

The Google Drive connector is owned by the application layer, so the core
workflow accepts a tiny injected client instead of importing credentials or
building a second Drive SDK.  The command-line entry point always builds the
local manifest; an actual upload requires the connected app adapter.

This module deliberately knows nothing about raw captures, K-lines, source
evidence, freeze archives, or historical research files.  A checkpoint is a
single-writer, exact-logical-path operation: an existing exact SHA is a
no-op, a different SHA is a conflict, and neither case creates a duplicate.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

from data_paths import DataPaths
from trading_calendar import TradingCalendar, default_calendar
from watchlist_schema import validate_input_coverage


CHECKPOINT_SCHEMA = "DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT_V1"
CLOUD_ROOT_TITLE = "ashare_watchlist"
DAILY_CHECKPOINTS_TITLE = "daily_checkpoints"
LATEST_TITLE = "latest"

NO_OP_ALREADY_VERIFIED = "NO_OP_ALREADY_VERIFIED"
UPLOADED_AND_VERIFIED = "UPLOADED_AND_VERIFIED"
CLOUD_CHECKPOINT_VERIFIED = "CLOUD_CHECKPOINT_VERIFIED"
CLOUD_CHECKPOINT_CONFLICT = "CLOUD_CHECKPOINT_CONFLICT"
CLOUD_CHECKPOINT_FAILED = "CLOUD_CHECKPOINT_FAILED"

FORMAL_KEEP = "FORMAL_KEEP"
DAILY_KEEP = "DAILY_KEEP"
REDUNDANT_INTERMEDIATE_CANDIDATE = "REDUNDANT_INTERMEDIATE_CANDIDATE"
UNKNOWN_DO_NOT_DELETE = "UNKNOWN_DO_NOT_DELETE"

_BJT = timezone(timedelta(hours=8))
_SHA256_RE = r"^[0-9a-f]{64}$"


class CheckpointError(RuntimeError):
    """Base class for local or remote checkpoint failures."""


class CheckpointConflict(CheckpointError):
    """An exact logical path already has incompatible bytes or duplicates."""


class DriveCheckpointClient(Protocol):
    """Small adapter surface implemented by the connected Drive app layer."""

    def list_folder(self, folder_id: str) -> Sequence["RemoteEntry | Mapping[str, Any]"]: ...

    def create_folder(self, name: str, parent_folder_id: str) -> "RemoteEntry | Mapping[str, Any]": ...

    def upload_file(
        self,
        local_path: Path,
        file_name: str,
        parent_folder_id: str,
    ) -> "RemoteEntry | Mapping[str, Any]": ...

    def read_file_bytes(self, file_id: str) -> bytes: ...


@dataclass(frozen=True)
class RemoteEntry:
    id: str
    name: str
    is_folder: bool = False
    size: int | None = None
    modified_time: str | None = None
    sha256: str | None = None
    path: str | None = None


def _date_parts(value: str | date | datetime) -> tuple[str, str]:
    text = value.date().isoformat() if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else str(value)
    token = text.strip().replace("-", "")
    if len(token) != 8 or not token.isdigit():
        raise ValueError(f"invalid date: {value!r}")
    parsed = datetime.strptime(token, "%Y%m%d").date()
    return parsed.isoformat(), token


def _next_trading_day(list_date: str, calendar: TradingCalendar) -> str:
    current = datetime.strptime(list_date, "%Y-%m-%d").date() + timedelta(days=1)
    while True:
        if calendar.is_trading_day(current):
            return current.strftime("%Y-%m-%d")
        current += timedelta(days=1)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN_ORIGIN"
    return completed.stdout.strip() or "UNKNOWN_ORIGIN"


def _file_record(path: Path, *, filename: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise CheckpointError(f"LOCAL_CHECKPOINT_FILE_MISSING: {path}")
    return {
        "filename": filename or path.name,
        "byte_length": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def checkpoint_manifest_path(data_root: Path, date_value: str | date | datetime) -> Path:
    _, token = _date_parts(date_value)
    return data_root / "checkpoints" / f"daily_checkpoint_{token}.json"


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_daily_checkpoint_manifest(
    date_value: str | date | datetime,
    *,
    data_root: Path,
    calendar: TradingCalendar | None = None,
    code_git_sha: str | None = None,
    created_at_bjt: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic manifest over only the four operational files."""

    list_date, token = _date_parts(date_value)
    root = Path(data_root).expanduser().resolve()
    paths = DataPaths(root)
    watchlist_path = paths.watchlist_file(token)
    tracker_path = paths.perf_tracker_file()
    dated_html_path = paths.reports_dir() / f"daily_close_{token}.html"
    latest_html_path = paths.reports_dir() / "latest.html"

    try:
        watchlist = json.loads(watchlist_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"LOCAL_WATCHLIST_NOT_READY: {watchlist_path}: {exc}") from exc
    if not isinstance(watchlist, dict) or str(watchlist.get("date", "")) != list_date:
        raise CheckpointError(f"LOCAL_WATCHLIST_DATE_MISMATCH: expected {list_date}")
    strategy_version = str(watchlist.get("strategy_version", "")).strip()
    if not strategy_version:
        raise CheckpointError("LOCAL_WATCHLIST_STRATEGY_VERSION_MISSING")
    input_coverage = None
    if "input_coverage" in watchlist:
        try:
            input_coverage = validate_input_coverage(
                watchlist["input_coverage"],
                expected_target_date=list_date,
            )
        except ValueError as exc:
            raise CheckpointError("LOCAL_WATCHLIST_INPUT_COVERAGE_INVALID") from exc

    cal = calendar or default_calendar()
    try:
        earliest_execution = _next_trading_day(list_date, cal)
    except Exception as exc:
        raise CheckpointError(f"CALENDAR_CONTEXT_NOT_READY: {type(exc).__name__}: {exc}") from exc

    resolved_sha = code_git_sha or _git_sha()
    if not resolved_sha or resolved_sha == "UNKNOWN_ORIGIN":
        raise CheckpointError("CODE_GIT_SHA_UNAVAILABLE")

    # The timestamp is intentionally a deterministic session-close anchor.  A
    # wall-clock creation time would make a same-day retry look like a remote
    # SHA conflict even when all four operational bytes are unchanged.
    created = created_at_bjt or f"{list_date}T15:00:00+08:00"
    try:
        datetime.fromisoformat(created)
    except ValueError as exc:
        raise CheckpointError(f"INVALID_CREATED_AT_BJT: {created!r}") from exc

    manifest = {
        "schema_version": CHECKPOINT_SCHEMA,
        "list_date": list_date,
        "earliest_execution": earliest_execution,
        "strategy_version": strategy_version,
        "code_git_sha": resolved_sha,
        "watchlist": _file_record(watchlist_path, filename=f"watchlist_{token}.json"),
        "perf_tracker": _file_record(tracker_path, filename="perf_tracker.json"),
        "dated_html": _file_record(dated_html_path, filename=f"daily_close_{token}.html"),
        "latest_html": _file_record(latest_html_path, filename="latest.html"),
        "created_at_bjt": created,
        "cloud_target": f"{CLOUD_ROOT_TITLE}/{DAILY_CHECKPOINTS_TITLE}/{token}",
        "verification_status": "LOCAL_INPUTS_VERIFIED",
        "upload_scope": [
            f"watchlist_{token}.json",
            "perf_tracker.json",
            f"daily_close_{token}.html",
            f"daily_checkpoint_{token}.json",
            "latest.html",
            "latest_checkpoint.json",
        ],
    }
    if input_coverage is not None:
        manifest["input_coverage"] = copy.deepcopy(input_coverage)
    return manifest


def validate_manifest(manifest: Mapping[str, Any], date_value: str | date | datetime) -> None:
    list_date, token = _date_parts(date_value)
    required = {
        "schema_version",
        "list_date",
        "earliest_execution",
        "strategy_version",
        "code_git_sha",
        "watchlist",
        "perf_tracker",
        "dated_html",
        "latest_html",
        "created_at_bjt",
        "cloud_target",
        "verification_status",
    }
    missing = sorted(required.difference(manifest))
    if missing:
        raise CheckpointError(f"CHECKPOINT_MANIFEST_FIELDS_MISSING: {','.join(missing)}")
    if manifest.get("schema_version") != CHECKPOINT_SCHEMA:
        raise CheckpointError("CHECKPOINT_MANIFEST_SCHEMA_MISMATCH")
    if manifest.get("list_date") != list_date:
        raise CheckpointError(f"CHECKPOINT_MANIFEST_DATE_MISMATCH: expected {list_date}")
    if manifest.get("cloud_target") != f"{CLOUD_ROOT_TITLE}/{DAILY_CHECKPOINTS_TITLE}/{token}":
        raise CheckpointError("CHECKPOINT_MANIFEST_TARGET_MISMATCH")
    if not str(manifest.get("code_git_sha", "")).strip():
        raise CheckpointError("CHECKPOINT_MANIFEST_CODE_SHA_MISSING")
    if "input_coverage" in manifest:
        try:
            validate_input_coverage(
                manifest["input_coverage"],
                expected_target_date=list_date,
            )
        except ValueError as exc:
            raise CheckpointError("CHECKPOINT_MANIFEST_INPUT_COVERAGE_INVALID") from exc
    expected_names = {
        "watchlist": f"watchlist_{token}.json",
        "perf_tracker": "perf_tracker.json",
        "dated_html": f"daily_close_{token}.html",
        "latest_html": "latest.html",
    }
    for key, expected_name in expected_names.items():
        record = manifest.get(key)
        if not isinstance(record, Mapping):
            raise CheckpointError(f"CHECKPOINT_MANIFEST_RECORD_INVALID: {key}")
        if record.get("filename") != expected_name:
            raise CheckpointError(f"CHECKPOINT_MANIFEST_FILENAME_MISMATCH: {key}")
        if not isinstance(record.get("byte_length"), int) or record["byte_length"] < 0:
            raise CheckpointError(f"CHECKPOINT_MANIFEST_LENGTH_INVALID: {key}")
        sha = str(record.get("sha256", ""))
        if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
            raise CheckpointError(f"CHECKPOINT_MANIFEST_SHA_INVALID: {key}")


def persist_checkpoint_manifest(manifest: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """Persist the manifest without overwriting an incompatible local copy."""

    list_date = str(manifest.get("list_date", ""))
    validate_manifest(manifest, list_date)
    desired = _canonical_json_bytes(manifest)
    destination = Path(path).expanduser().resolve()
    if destination.exists():
        existing = destination.read_bytes()
        if existing == desired:
            return {"status": NO_OP_ALREADY_VERIFIED, "path": str(destination), "byte_length": len(existing), "sha256": file_sha256(destination)}
        raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: LOCAL_MANIFEST_SHA_CONFLICT: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(desired)
    try:
        if destination.exists():
            existing = destination.read_bytes()
            if existing == desired:
                temporary.unlink(missing_ok=True)
                return {"status": NO_OP_ALREADY_VERIFIED, "path": str(destination), "byte_length": len(existing), "sha256": file_sha256(destination)}
            raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: LOCAL_MANIFEST_SHA_CONFLICT: {destination}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "LOCAL_MANIFEST_PERSISTED", "path": str(destination), "byte_length": len(desired), "sha256": file_sha256(destination)}


def _local_files(manifest: Mapping[str, Any], data_root: Path) -> dict[str, Path]:
    _, token = _date_parts(str(manifest["list_date"]))
    paths = DataPaths(Path(data_root).expanduser().resolve())
    return {
        "watchlist": paths.watchlist_file(token),
        "perf_tracker": paths.perf_tracker_file(),
        "dated_html": paths.reports_dir() / f"daily_close_{token}.html",
        "latest_html": paths.reports_dir() / "latest.html",
    }


def _verify_local_files(manifest: Mapping[str, Any], data_root: Path) -> None:
    for key, path in _local_files(manifest, data_root).items():
        record = manifest[key]
        if not path.is_file():
            raise CheckpointError(f"LOCAL_CHECKPOINT_FILE_MISSING: {path}")
        actual_length = path.stat().st_size
        actual_sha = file_sha256(path)
        if actual_length != record["byte_length"] or actual_sha != record["sha256"]:
            raise CheckpointError(f"LOCAL_CHECKPOINT_SHA_MISMATCH: {key}: {path}")


def _verify_local_input_coverage(manifest: Mapping[str, Any], data_root: Path) -> None:
    """Keep the checkpoint's explicit coverage identity tied to its watchlist."""

    watchlist_path = _local_files(manifest, Path(data_root))["watchlist"]
    try:
        watchlist = json.loads(watchlist_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointError("LOCAL_WATCHLIST_INPUT_COVERAGE_UNREADABLE") from exc
    if not isinstance(watchlist, Mapping):
        raise CheckpointError("LOCAL_WATCHLIST_INPUT_COVERAGE_UNREADABLE")
    if watchlist.get("input_coverage") != manifest.get("input_coverage"):
        raise CheckpointError("CHECKPOINT_INPUT_COVERAGE_CONFLICT")


def _coerce_entry(value: RemoteEntry | Mapping[str, Any]) -> RemoteEntry:
    if isinstance(value, RemoteEntry):
        return value
    name = value.get("name", value.get("title"))
    entry_id = value.get("id")
    if not name or not entry_id:
        raise CheckpointError("DRIVE_ENTRY_METADATA_INCOMPLETE")
    mime = str(value.get("mime_type", value.get("mimeType", "")))
    file_or_folder = str(value.get("file_or_folder", ""))
    is_folder = file_or_folder == "folder" or mime == "application/vnd.google-apps.folder" or bool(value.get("is_folder", False))
    size = value.get("size")
    try:
        parsed_size = None if size is None else int(size)
    except (TypeError, ValueError):
        parsed_size = None
    return RemoteEntry(
        id=str(entry_id),
        name=str(name),
        is_folder=is_folder,
        size=parsed_size,
        modified_time=value.get("modified_time", value.get("updated_at")),
        sha256=value.get("sha256"),
        path=value.get("path"),
    )


def _children(client: DriveCheckpointClient, folder_id: str) -> list[RemoteEntry]:
    return [_coerce_entry(item) for item in client.list_folder(folder_id)]


def _ensure_folder(client: DriveCheckpointClient, parent_id: str, name: str) -> RemoteEntry:
    matches = [entry for entry in _children(client, parent_id) if entry.name == name]
    if len(matches) > 1:
        raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: DUPLICATE_FOLDER: {name}")
    if matches:
        if not matches[0].is_folder:
            raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: FILE_BLOCKS_FOLDER: {name}")
        return matches[0]
    created = _coerce_entry(client.create_folder(name, parent_id))
    # Some Drive adapters return only {id, title, url} for a successful
    # folder-create response. The method itself is the folder-kind contract.
    if not created.is_folder and created.name == name:
        created = RemoteEntry(
            id=created.id,
            name=created.name,
            is_folder=True,
            size=created.size,
            modified_time=created.modified_time,
            sha256=created.sha256,
            path=created.path,
        )
    if created.name != name or not created.is_folder:
        raise CheckpointError(f"DRIVE_FOLDER_CREATE_INVALID: {name}")
    return created


def _ensure_remote_file(
    client: DriveCheckpointClient,
    *,
    folder: RemoteEntry,
    file_name: str,
    local_path: Path,
    expected_length: int,
    expected_sha: str,
) -> dict[str, Any]:
    matches = [entry for entry in _children(client, folder.id) if entry.name == file_name]
    if len(matches) > 1:
        raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: DUPLICATE_FILE: {folder.name}/{file_name}")

    if matches:
        existing = matches[0]
        if existing.is_folder:
            raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: FOLDER_BLOCKS_FILE: {folder.name}/{file_name}")
        remote_bytes = client.read_file_bytes(existing.id)
        remote_sha = hashlib.sha256(remote_bytes).hexdigest()
        if len(remote_bytes) == expected_length and remote_sha == expected_sha:
            return {
                "status": NO_OP_ALREADY_VERIFIED,
                "file_name": file_name,
                "remote_id": existing.id,
                "byte_length": expected_length,
                "sha256": expected_sha,
            }
        raise CheckpointConflict(
            f"{CLOUD_CHECKPOINT_CONFLICT}: {folder.name}/{file_name}: "
            f"expected_sha={expected_sha}, remote_sha={remote_sha}, "
            f"expected_length={expected_length}, remote_length={len(remote_bytes)}"
        )

    uploaded = _coerce_entry(client.upload_file(local_path, file_name, folder.id))
    if uploaded.name != file_name or uploaded.is_folder:
        raise CheckpointError(f"DRIVE_UPLOAD_METADATA_INVALID: {folder.name}/{file_name}")
    readback = client.read_file_bytes(uploaded.id)
    readback_sha = hashlib.sha256(readback).hexdigest()
    if len(readback) != expected_length or readback_sha != expected_sha:
        raise CheckpointConflict(
            f"{CLOUD_CHECKPOINT_CONFLICT}: READBACK_SHA_MISMATCH: {folder.name}/{file_name}: "
            f"expected_sha={expected_sha}, readback_sha={readback_sha}"
        )
    return {
        "status": UPLOADED_AND_VERIFIED,
        "file_name": file_name,
        "remote_id": uploaded.id,
        "byte_length": expected_length,
        "sha256": expected_sha,
    }


def upload_checkpoint(
    manifest: Mapping[str, Any],
    *,
    data_root: Path,
    client: DriveCheckpointClient,
    root_folder_id: str,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Upload one dated checkpoint and then update fixed latest locations."""

    list_date, token = _date_parts(str(manifest["list_date"]))
    validate_manifest(manifest, list_date)
    _verify_local_input_coverage(manifest, Path(data_root))
    _verify_local_files(manifest, data_root)
    local_manifest_path = manifest_path or checkpoint_manifest_path(Path(data_root), token)
    desired_manifest_bytes = _canonical_json_bytes(manifest)
    if local_manifest_path.is_file():
        if local_manifest_path.read_bytes() != desired_manifest_bytes:
            raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: LOCAL_MANIFEST_SHA_CONFLICT: {local_manifest_path}")
    else:
        persist_checkpoint_manifest(manifest, local_manifest_path)

    daily_root = _ensure_folder(client, root_folder_id, DAILY_CHECKPOINTS_TITLE)
    dated_folder = _ensure_folder(client, daily_root.id, token)
    upload_specs = [
        ("watchlist", dated_folder, manifest["watchlist"]["filename"], _local_files(manifest, data_root)["watchlist"]),
        ("perf_tracker", dated_folder, manifest["perf_tracker"]["filename"], _local_files(manifest, data_root)["perf_tracker"]),
        ("dated_html", dated_folder, manifest["dated_html"]["filename"], _local_files(manifest, data_root)["dated_html"]),
    ]
    file_results: dict[str, dict[str, Any]] = {}
    for key, folder, file_name, local_path in upload_specs:
        record = manifest[key]
        file_results[key] = _ensure_remote_file(
            client,
            folder=folder,
            file_name=file_name,
            local_path=local_path,
            expected_length=record["byte_length"],
            expected_sha=record["sha256"],
        )

    manifest_record = _file_record(local_manifest_path, filename=f"daily_checkpoint_{token}.json")
    file_results["dated_manifest"] = _ensure_remote_file(
        client,
        folder=dated_folder,
        file_name=manifest_record["filename"],
        local_path=local_manifest_path,
        expected_length=manifest_record["byte_length"],
        expected_sha=manifest_record["sha256"],
    )

    latest_folder = _ensure_folder(client, daily_root.id, LATEST_TITLE)
    latest_record = manifest["latest_html"]
    file_results["latest_html"] = _ensure_remote_file(
        client,
        folder=latest_folder,
        file_name=latest_record["filename"],
        local_path=_local_files(manifest, data_root)["latest_html"],
        expected_length=latest_record["byte_length"],
        expected_sha=latest_record["sha256"],
    )
    latest_checkpoint_path = local_manifest_path
    file_results["latest_checkpoint"] = _ensure_remote_file(
        client,
        folder=latest_folder,
        file_name="latest_checkpoint.json",
        local_path=latest_checkpoint_path,
        expected_length=manifest_record["byte_length"],
        expected_sha=manifest_record["sha256"],
    )

    payload_bytes = sum(
        int(item["byte_length"])
        for item in file_results.values()
    )
    uploaded_bytes = sum(
        int(item["byte_length"])
        for item in file_results.values()
        if item["status"] == UPLOADED_AND_VERIFIED
    )
    return {
        "status": CLOUD_CHECKPOINT_VERIFIED,
        "list_date": list_date,
        "cloud_target": manifest["cloud_target"],
        "file_count": len(file_results),
        "uploaded_file_count": sum(item["status"] == UPLOADED_AND_VERIFIED for item in file_results.values()),
        "no_op_file_count": sum(item["status"] == NO_OP_ALREADY_VERIFIED for item in file_results.values()),
        "total_payload_bytes": payload_bytes,
        "uploaded_bytes": uploaded_bytes,
        "files": file_results,
        "remote_deletes": 0,
    }


def prepare_local_checkpoint(
    date_value: str | date | datetime,
    *,
    data_root: Path,
    calendar: TradingCalendar | None = None,
    code_git_sha: str | None = None,
) -> dict[str, Any]:
    """Build/persist the local manifest for a fail-soft daily runner."""

    manifest = build_daily_checkpoint_manifest(
        date_value,
        data_root=data_root,
        calendar=calendar,
        code_git_sha=code_git_sha,
    )
    path = checkpoint_manifest_path(Path(data_root), date_value)
    persisted = persist_checkpoint_manifest(manifest, path)
    return {"manifest": manifest, "manifest_path": str(path), "persist": persisted}


def restore_lightweight_checkpoint(
    date_value: str | date | datetime,
    *,
    client: DriveCheckpointClient,
    root_folder_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Restore only dated lightweight files after manifest SHA verification."""

    list_date, token = _date_parts(date_value)
    daily_root = _ensure_existing_folder(client, root_folder_id, DAILY_CHECKPOINTS_TITLE)
    dated_folder = _ensure_existing_folder(client, daily_root.id, token)
    entries = _children(client, dated_folder.id)
    manifest_entry = _one_named_entry(entries, f"daily_checkpoint_{token}.json", expect_folder=False)
    manifest_bytes = client.read_file_bytes(manifest_entry.id)
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"RESTORE_MANIFEST_INVALID: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise CheckpointError("RESTORE_MANIFEST_NOT_OBJECT")
    validate_manifest(manifest, list_date)
    expected_files = {
        "watchlist": manifest["watchlist"]["filename"],
        "perf_tracker": manifest["perf_tracker"]["filename"],
        "dated_html": manifest["dated_html"]["filename"],
    }
    restored: dict[str, str] = {}
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for key, filename in expected_files.items():
        entry = _one_named_entry(entries, filename, expect_folder=False)
        payload = client.read_file_bytes(entry.id)
        expected = manifest[key]
        actual_sha = hashlib.sha256(payload).hexdigest()
        if len(payload) != expected["byte_length"] or actual_sha != expected["sha256"]:
            raise CheckpointConflict(
                f"{CLOUD_CHECKPOINT_CONFLICT}: RESTORE_SHA_MISMATCH: {filename}: "
                f"expected_sha={expected['sha256']}, actual_sha={actual_sha}"
            )
        out_path = destination / filename
        _write_restore_bytes(out_path, payload)
        restored[key] = str(out_path)

    manifest_path = destination / manifest_entry.name
    _write_restore_bytes(manifest_path, manifest_bytes)
    restored["manifest"] = str(manifest_path)
    return {
        "status": "LIGHTWEIGHT_CLOUD_RECOVERY_VERIFIED",
        "list_date": list_date,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "restored": restored,
        "remote_deletes": 0,
    }


def _one_named_entry(entries: Iterable[RemoteEntry], name: str, *, expect_folder: bool) -> RemoteEntry:
    matches = [entry for entry in entries if entry.name == name]
    if len(matches) != 1:
        raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: EXPECTED_ONE_REMOTE_ENTRY: {name}: found={len(matches)}")
    if matches[0].is_folder != expect_folder:
        raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: REMOTE_ENTRY_KIND_MISMATCH: {name}")
    return matches[0]


def _ensure_existing_folder(client: DriveCheckpointClient, parent_id: str, name: str) -> RemoteEntry:
    return _one_named_entry(_children(client, parent_id), name, expect_folder=True)


def _write_restore_bytes(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: LOCAL_RESTORE_PATH_CONFLICT: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    try:
        if path.exists() and path.read_bytes() != payload:
            raise CheckpointConflict(f"{CLOUD_CHECKPOINT_CONFLICT}: LOCAL_RESTORE_PATH_CONFLICT: {path}")
        if not path.exists():
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def classify_inventory(
    entries: Iterable[RemoteEntry | Mapping[str, Any]],
    *,
    formal_paths: Iterable[str] = (),
    formal_prefixes: Iterable[str] = (),
    redundant_prefixes: Iterable[str] = (),
) -> dict[str, Any]:
    """Classify a read-only inventory; this function has no delete operation."""

    formal = set(formal_paths)
    formal_starts = tuple(formal_prefixes)
    redundant_starts = tuple(redundant_prefixes)
    records: list[dict[str, Any]] = []
    counts = {FORMAL_KEEP: 0, DAILY_KEEP: 0, REDUNDANT_INTERMEDIATE_CANDIDATE: 0, UNKNOWN_DO_NOT_DELETE: 0}
    bytes_by_class = {key: 0 for key in counts}
    for raw in entries:
        entry = _coerce_entry(raw)
        path = entry.path or entry.name
        if path.startswith(f"{CLOUD_ROOT_TITLE}/{DAILY_CHECKPOINTS_TITLE}/"):
            classification = DAILY_KEEP
        elif path in formal or path.startswith(formal_starts):
            classification = FORMAL_KEEP
        elif path.startswith(redundant_starts):
            classification = REDUNDANT_INTERMEDIATE_CANDIDATE
        else:
            classification = UNKNOWN_DO_NOT_DELETE
        record = {
            "path": path,
            "filename": entry.name,
            "size": entry.size,
            "modified_time": entry.modified_time,
            "sha256": entry.sha256,
            "classification": classification,
            "remote_id": entry.id,
        }
        records.append(record)
        counts[classification] += 1
        bytes_by_class[classification] += entry.size or 0
    return {
        "schema_version": "CLOUD_STORAGE_INVENTORY_V1",
        "read_only": True,
        "remote_deletes": 0,
        "counts": counts,
        "bytes_by_class": bytes_by_class,
        "entries": sorted(records, key=lambda item: item["path"]),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="list date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--manifest-only", action="store_true", help="build/persist the local manifest without attempting Drive")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = (args.data_root or DataPaths.from_env().root).expanduser().resolve()
    try:
        prepared = prepare_local_checkpoint(args.date, data_root=data_root)
    except (CheckpointError, OSError, ValueError) as exc:
        print(json.dumps({"status": CLOUD_CHECKPOINT_FAILED, "reason": str(exc)[:1000]}, ensure_ascii=False, sort_keys=True))
        return 1
    if args.manifest_only:
        print(json.dumps({"status": "LOCAL_CHECKPOINT_READY", "manifest_path": prepared["manifest_path"], "manifest": prepared["manifest"]}, ensure_ascii=False, sort_keys=True))
        return 0
    print(json.dumps({
        "status": CLOUD_CHECKPOINT_FAILED,
        "reason": "DRIVE_CONNECTOR_NOT_CONFIGURED",
        "manifest_path": prepared["manifest_path"],
        "message": "[CLOUD] FAILED DRIVE_CONNECTOR_NOT_CONFIGURED",
    }, ensure_ascii=False, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
