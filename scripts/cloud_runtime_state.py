"""Manage the small durable state surface used by the cloud runner.

The production runner writes raw market evidence and generation inputs only
under its temporary ``ASHARE_DATA_ROOT``.  This module is the explicit copy
boundary: only the allowlisted canonical watchlists, tracker, shadow store,
final reports, and checkpoint manifests can cross into the ``runtime-state``
checkout.  The source checkout and the state checkout are intentionally
separate trees.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256
from b_shadow_monitor import ShadowMonitorError, load_store
from data_paths import DataPaths
from track_perf import (
    CURRENT_PROSPECTIVE_STRATEGY,
    TrackerSchemaError,
    current_prospective_tracker,
    current_prospective_watchlists,
    load_tracker,
)
from upload_daily_checkpoint import CheckpointError, file_sha256, validate_manifest
from universe_policy import BOARD_CHINEXT, BOARD_STAR, classify_board, policy_display_label
from watchlist_schema import WatchlistSchemaError, load_watchlist


RUNTIME_STATE_MARKER = "GITHUB_ACTIONS_DAILY_RUNTIME_V1"
RUNTIME_STATE_FILE = "RUNTIME_STATE.md"
RUNTIME_STATE_SCHEMA = "RUNTIME_STATE_ALLOWLIST_V1"
ALREADY_COMPLETED = "ALREADY_COMPLETED"
INCOMPLETE_SAME_DAY_STATE = "INCOMPLETE_SAME_DAY_STATE"
RUNTIME_STATE_VALID = "RUNTIME_STATE_VALID"
RUNTIME_STATE_ERROR = "RUNTIME_STATE_ERROR"

_DATE_TOKEN = re.compile(r"^\d{8}$")
_WATCHLIST_NAME = re.compile(r"^watchlist_\d{8}\.json$")
_DATED_REPORT_NAME = re.compile(r"^daily_close_\d{8}\.html$")
_CHECKPOINT_NAME = re.compile(r"^daily_checkpoint_\d{8}\.json$")
_ALLOWED_TOP_LEVEL = {RUNTIME_STATE_FILE, ".gitattributes", "data", ".git"}


class RuntimeStateError(ValueError):
    """The durable state boundary or its integrity contract is invalid."""


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _date_parts(value: str | date | datetime) -> tuple[str, str]:
    if isinstance(value, datetime):
        text = value.date().isoformat()
    elif isinstance(value, date):
        text = value.isoformat()
    else:
        text = str(value).strip().replace("/", "-")
    try:
        parsed = date.fromisoformat(text.replace("-", ""))
    except ValueError as exc:
        if len(text) == 8 and text.isdigit():
            parsed = datetime.strptime(text, "%Y%m%d").date()
        else:
            raise RuntimeStateError(f"invalid date: {value!r}") from exc
    return parsed.isoformat(), parsed.strftime("%Y%m%d")


def _is_allowlisted_data_relative(relative: Path) -> bool:
    token = relative.as_posix()
    if _WATCHLIST_NAME.fullmatch(token) or token == "perf_tracker.json":
        return True
    if token == "shadow_monitor/b_shadow_monitor.json":
        return True
    if token in {"reports/latest.html", "reports/perf_report.md"}:
        return True
    if _DATED_REPORT_NAME.fullmatch(Path(token).name) and token.startswith("reports/"):
        return True
    if _CHECKPOINT_NAME.fullmatch(Path(token).name) and token.startswith("checkpoints/"):
        return True
    return False


def _data_candidates(root: Path) -> Iterable[Path]:
    """Yield only explicit allowlist patterns; never walk raw evidence."""

    patterns = (
        "watchlist_????????.json",
        "perf_tracker.json",
        "shadow_monitor/b_shadow_monitor.json",
        "reports/daily_close_????????.html",
        "reports/latest.html",
        "reports/perf_report.md",
        "checkpoints/daily_checkpoint_????????.json",
    )
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            yield path


def allowlisted_data_files(data_root: str | Path) -> list[tuple[Path, Path]]:
    """Return ``(absolute_path, relative_path)`` for durable files only."""

    root = _resolved(data_root)
    result: list[tuple[Path, Path]] = []
    for path in _data_candidates(root):
        if path.is_symlink():
            raise RuntimeStateError(f"symlink is not allowed in durable state: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if not _is_allowlisted_data_relative(relative):
            raise RuntimeStateError(f"internal allowlist mismatch: {relative.as_posix()}")
        result.append((path, relative))
    return sorted(result, key=lambda item: item[1].as_posix())


def _state_data_root(state_root: str | Path) -> Path:
    return _resolved(state_root) / "data"


def _assert_separate_trees(state_root: Path, data_root: Path) -> None:
    state = state_root.resolve()
    data = data_root.resolve()
    if state == data or state in data.parents or data in state.parents:
        raise RuntimeStateError("source data root and runtime-state checkout must be separate")


def _read_marker(state_root: Path) -> str:
    marker = state_root / RUNTIME_STATE_FILE
    if not marker.is_file():
        raise RuntimeStateError(f"{RUNTIME_STATE_FILE} is missing")
    try:
        text = marker.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeStateError(f"cannot read {marker}: {exc}") from exc
    required = (
        RUNTIME_STATE_MARKER,
        "operational state only",
        "never merge into master",
        "cloud workflow is the normal single writer",
        "no secrets",
        "no raw market evidence",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeStateError(f"runtime-state marker is incomplete: {','.join(missing)}")
    return text


def validate_state_tree(state_root: str | Path) -> dict[str, Any]:
    """Reject files outside the marker plus the durable data allowlist."""

    root = _resolved(state_root)
    _read_marker(root)
    data = root / "data"
    if not data.is_dir():
        raise RuntimeStateError(f"runtime-state data directory is missing: {data}")

    unexpected_top_level = sorted(
        child.name for child in root.iterdir() if child.name not in _ALLOWED_TOP_LEVEL
    )
    if unexpected_top_level:
        raise RuntimeStateError(
            "runtime-state has unexpected top-level entries: "
            + ",".join(unexpected_top_level)
        )

    unexpected: list[str] = []
    for path in sorted(data.rglob("*")):
        if path.is_symlink():
            unexpected.append(path.relative_to(root).as_posix())
            continue
        if path.is_file() and not _is_allowlisted_data_relative(path.relative_to(data)):
            unexpected.append(path.relative_to(root).as_posix())
    if unexpected:
        raise RuntimeStateError(
            "runtime-state contains non-allowlisted files: " + ",".join(unexpected)
        )
    files = [f"data/{relative.as_posix()}" for _path, relative in allowlisted_data_files(data)]
    return {
        "schema_version": RUNTIME_STATE_SCHEMA,
        "marker": RUNTIME_STATE_MARKER,
        "state_root": str(root),
        "files": files,
        "raw_persisted": False,
        "prospective_inputs_persisted": False,
    }


def _write_bytes(path: Path, payload: bytes, *, overwrite: bool) -> bool:
    if path.is_symlink():
        raise RuntimeStateError(f"refusing symlink destination: {path}")
    if path.exists() and not overwrite:
        existing = path.read_bytes()
        if existing != payload:
            raise RuntimeStateError(f"restore path conflicts with existing bytes: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise RuntimeStateError(f"cannot atomically write durable state: {path}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def _hash_record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "byte_length": path.stat().st_size, "sha256": file_sha256(path)}


def _manifest_paths(data_root: Path, manifest: Mapping[str, Any]) -> dict[str, Path]:
    _list_date, token = _date_parts(str(manifest.get("list_date", "")))
    paths = DataPaths(data_root)
    return {
        "watchlist": paths.watchlist_file(token),
        "perf_tracker": paths.perf_tracker_file(),
        "dated_html": paths.reports_dir() / f"daily_close_{token}.html",
        "latest_html": paths.reports_dir() / "latest.html",
    }


def _validate_checkpoint_manifest(data_root: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeStateError(f"checkpoint manifest cannot be read: {manifest_path}: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise RuntimeStateError(f"checkpoint manifest is not an object: {manifest_path}")
    try:
        list_date, token = _date_parts(str(manifest.get("list_date", "")))
        validate_manifest(manifest, list_date)
    except (CheckpointError, ValueError) as exc:
        raise RuntimeStateError(f"checkpoint manifest is invalid: {manifest_path}: {exc}") from exc
    expected_name = f"daily_checkpoint_{token}.json"
    if manifest_path.name != expected_name:
        raise RuntimeStateError(f"checkpoint filename/date mismatch: {manifest_path.name}")
    local_paths = _manifest_paths(data_root, manifest)
    for key, path in local_paths.items():
        record = manifest.get(key)
        if not isinstance(record, Mapping):
            raise RuntimeStateError(f"checkpoint record is missing: {key}")
        if not path.is_file():
            raise RuntimeStateError(f"checkpoint payload is missing: {path}")
        if path.stat().st_size != record.get("byte_length") or file_sha256(path) != record.get("sha256"):
            raise RuntimeStateError(f"checkpoint SHA/length mismatch: {key}")
    return dict(manifest)


def _checkpoint_files(data_root: Path) -> list[Path]:
    directory = data_root / "checkpoints"
    return sorted(path for path in directory.glob("daily_checkpoint_????????.json") if path.is_file())


def _is_formal_b_watchlist(path: Path) -> bool:
    try:
        watchlist = load_watchlist(path)
    except (OSError, UnicodeDecodeError, WatchlistSchemaError):
        return False
    return (
        watchlist.get("strategy_version") == CURRENT_PROSPECTIVE_STRATEGY
        and all(
            isinstance(candidate, Mapping)
            and candidate.get("strategy_version") == CURRENT_PROSPECTIVE_STRATEGY
            for candidate in watchlist.get("candidates", [])
        )
    )


def validate_runtime_data(
    data_root: str | Path,
    *,
    require_current_tracker: bool = True,
    validate_checkpoints: bool = True,
) -> dict[str, Any]:
    """Validate the restored operational state without any provider calls."""

    root = _resolved(data_root)
    paths = DataPaths(root)
    watchlist_paths = paths.watchlist_files()
    if not watchlist_paths:
        raise RuntimeStateError("no canonical watchlists were restored")
    try:
        watchlists = [load_watchlist(path) for path in watchlist_paths]
    except (OSError, UnicodeDecodeError, WatchlistSchemaError) as exc:
        raise RuntimeStateError(f"canonical watchlist validation failed: {exc}") from exc

    tracker_path = paths.perf_tracker_file()
    try:
        tracker = load_tracker(tracker_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TrackerSchemaError) as exc:
        raise RuntimeStateError(f"perf_tracker validation failed: {exc}") from exc
    try:
        current = current_prospective_tracker(tracker, paths)
        current_watchlists = current_prospective_watchlists(paths)
    except (ValueError, TrackerSchemaError, WatchlistSchemaError) as exc:
        raise RuntimeStateError(f"current prospective tracker identity is invalid: {exc}") from exc
    if require_current_tracker and not current_watchlists:
        raise RuntimeStateError("current prospective canonical watchlist is missing")
    if require_current_tracker and not current.get("signals"):
        raise RuntimeStateError("current prospective tracker is empty")

    shadow_path = root / "shadow_monitor" / "b_shadow_monitor.json"
    if shadow_path.exists():
        try:
            load_store(shadow_path.parent, missing_ok=False)
        except (OSError, ShadowMonitorError) as exc:
            raise RuntimeStateError(f"shadow store validation failed: {exc}") from exc

    checkpoint_count = 0
    if validate_checkpoints:
        for manifest_path in _checkpoint_files(root):
            _validate_checkpoint_manifest(root, manifest_path)
            checkpoint_count += 1

    return {
        "status": RUNTIME_STATE_VALID,
        "data_root": str(root),
        "watchlist_count": len(watchlists),
        "current_watchlist_count": len(current_watchlists),
        "current_tracker_signal_count": len(current.get("signals", {})),
        "tracker": _hash_record(tracker_path),
        "shadow_store": _hash_record(shadow_path) if shadow_path.is_file() else None,
        "checkpoint_count": checkpoint_count,
        "provider_calls": 0,
        "raw_persisted": False,
        "prospective_inputs_persisted": False,
    }


def restore_allowlist(state_root: str | Path, data_root: str | Path) -> dict[str, Any]:
    """Restore only allowlisted files from a state checkout into temp data."""

    state = _resolved(state_root)
    data = _resolved(data_root)
    _assert_separate_trees(state, data)
    state_report = validate_state_tree(state)
    source_data = state / "data"
    copied: list[str] = []
    unchanged: list[str] = []
    for source, relative in allowlisted_data_files(source_data):
        destination = data / relative
        changed = _write_bytes(destination, source.read_bytes(), overwrite=False)
        (copied if changed else unchanged).append(relative.as_posix())
    validation = validate_runtime_data(data)
    return {
        "status": "RUNTIME_STATE_RESTORED",
        "state_root": str(state),
        "data_root": str(data),
        "copied": copied,
        "unchanged": unchanged,
        "source_file_count": len(state_report["files"]),
        "validation": validation,
        "raw_persisted": False,
        "prospective_inputs_persisted": False,
    }


def persist_allowlist(state_root: str | Path, data_root: str | Path) -> dict[str, Any]:
    """Copy only allowlisted production outputs into the state checkout."""

    state = _resolved(state_root)
    data = _resolved(data_root)
    _assert_separate_trees(state, data)
    _read_marker(state)
    source_validation = validate_runtime_data(data)
    destination_data = state / "data"
    copied: list[str] = []
    unchanged: list[str] = []
    for source, relative in allowlisted_data_files(data):
        destination = destination_data / relative
        changed = _write_bytes(destination, source.read_bytes(), overwrite=True)
        (copied if changed else unchanged).append(f"data/{relative.as_posix()}")
    state_validation = validate_state_tree(state)
    restored_validation = validate_runtime_data(destination_data)
    return {
        "status": "RUNTIME_STATE_READY_TO_COMMIT",
        "state_root": str(state),
        "data_root": str(data),
        "copied": copied,
        "unchanged": unchanged,
        "source_validation": source_validation,
        "state_validation": state_validation,
        "restored_validation": restored_validation,
        "raw_persisted": False,
        "prospective_inputs_persisted": False,
    }


def bootstrap_allowlist(state_root: str | Path, data_root: str | Path) -> dict[str, Any]:
    """Bootstrap trusted core state and reuse only valid existing checkpoints.

    A local checkpoint can legitimately be stale when a trusted local tracker
    was advanced after the checkpoint was produced.  Such a checkpoint is
    omitted from the first runtime-state commit instead of being copied as if
    it were a verified success manifest.
    """

    state = _resolved(state_root)
    data = _resolved(data_root)
    _assert_separate_trees(state, data)
    _read_marker(state)
    source_validation = validate_runtime_data(data, validate_checkpoints=False)
    valid_checkpoints: set[Path] = set()
    skipped_checkpoints: dict[str, str] = {}
    for manifest_path in _checkpoint_files(data):
        try:
            _validate_checkpoint_manifest(data, manifest_path)
        except RuntimeStateError as exc:
            skipped_checkpoints[manifest_path.name] = str(exc)[:500]
        else:
            valid_checkpoints.add(manifest_path)

    destination_data = state / "data"
    copied: list[str] = []
    skipped: list[str] = []
    for source, relative in allowlisted_data_files(data):
        if relative.name.startswith("watchlist_") and not _is_formal_b_watchlist(source):
            skipped.append(f"data/{relative.as_posix()}")
            continue
        if relative.parts[:1] == ("checkpoints",) and source not in valid_checkpoints:
            skipped.append(f"data/{relative.as_posix()}")
            continue
        destination = destination_data / relative
        _write_bytes(destination, source.read_bytes(), overwrite=True)
        copied.append(f"data/{relative.as_posix()}")

    state_validation = validate_state_tree(state)
    restored_validation = validate_runtime_data(destination_data)
    return {
        "status": "RUNTIME_STATE_BOOTSTRAPPED",
        "state_root": str(state),
        "data_root": str(data),
        "copied": copied,
        "skipped": skipped,
        "skipped_checkpoints": skipped_checkpoints,
        "source_validation": source_validation,
        "state_validation": state_validation,
        "restored_validation": restored_validation,
        "raw_persisted": False,
        "prospective_inputs_persisted": False,
    }


def completed_run_status(data_root: str | Path, date_value: str | date | datetime) -> dict[str, Any]:
    """Verify the dated watchlist, tracker/report checkpoint, and HTML agree."""

    root = _resolved(data_root)
    list_date, token = _date_parts(date_value)
    paths = DataPaths(root)
    watchlist_path = paths.watchlist_file(token)
    html_path = paths.reports_dir() / f"daily_close_{token}.html"
    manifest_path = paths.root / "checkpoints" / f"daily_checkpoint_{token}.json"
    required = (watchlist_path, html_path, manifest_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return {
            "status": INCOMPLETE_SAME_DAY_STATE,
            "list_date": list_date,
            "missing": missing,
            "reason": "required same-day success files are incomplete",
        }
    try:
        watchlist = load_watchlist(watchlist_path)
        if watchlist.get("date") != list_date:
            raise RuntimeStateError("canonical watchlist date mismatch")
        manifest = _validate_checkpoint_manifest(root, manifest_path)
        tracker = load_tracker(paths.perf_tracker_file())
        current_prospective_tracker(tracker, paths)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RuntimeStateError) as exc:
        return {
            "status": INCOMPLETE_SAME_DAY_STATE,
            "list_date": list_date,
            "missing": [],
            "reason": str(exc)[:1000],
        }
    return {
        "status": ALREADY_COMPLETED,
        "list_date": list_date,
        "watchlist": _hash_record(watchlist_path),
        "tracker": _hash_record(paths.perf_tracker_file()),
        "dated_html": _hash_record(html_path),
        "checkpoint": _hash_record(manifest_path),
        "checkpoint_code_git_sha": manifest.get("code_git_sha"),
        "provider_calls": 0,
    }


def _read_result(path: Path | None) -> Mapping[str, Any] | None:
    if path is None:
        return None
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return None
        value = json.loads(lines[-1])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def build_summary(
    data_root: str | Path,
    date_value: str | date | datetime,
    *,
    status: str | None = None,
    state_commit: str | None = None,
    result: Mapping[str, Any] | None = None,
) -> str:
    """Build a compact, secret-free GitHub Actions job summary."""

    list_date, token = _date_parts(date_value)
    root = _resolved(data_root)
    paths = DataPaths(root)
    watchlist_path = paths.watchlist_file(token)
    watchlist: Mapping[str, Any] | None = None
    if watchlist_path.is_file():
        try:
            loaded = load_watchlist(watchlist_path)
            watchlist = loaded if isinstance(loaded, Mapping) else None
        except (OSError, UnicodeDecodeError, WatchlistSchemaError):
            watchlist = None
    bundle = result.get("daily_close_bundle") if isinstance(result, Mapping) else None
    bundle = bundle if isinstance(bundle, Mapping) else {}
    track = bundle.get("track_perf") if isinstance(bundle.get("track_perf"), Mapping) else {}
    renderer = bundle.get("renderer") if isinstance(bundle.get("renderer"), Mapping) else {}
    shadow = bundle.get("shadow_monitor") if isinstance(bundle.get("shadow_monitor"), Mapping) else {}
    review = track.get("review_coverage") if isinstance(track.get("review_coverage"), Mapping) else {}
    shadow_status = shadow.get("status")
    shadow_epoch = shadow.get("prospective_epoch_start")
    if not shadow_status:
        shadow_path = root / "shadow_monitor" / "b_shadow_monitor.json"
        if shadow_path.is_file():
            try:
                shadow_store = load_store(shadow_path.parent, missing_ok=False)
                shadow_status = (shadow_store or {}).get("status")
                shadow_epoch = ((shadow_store or {}).get("prospective_epoch") or {}).get("start_date")
            except ShadowMonitorError:
                shadow_status = "SHADOW_CAPTURE_INCOMPLETE"
    report_path = paths.reports_dir() / f"daily_close_{token}.html"
    report_status = renderer.get("status") or ("READY" if report_path.is_file() else "—")
    policy = watchlist.get("universe_policy") if watchlist else None
    policy_text = str(policy or "ASHARE_MAIN_BOARD_ONLY_V1")
    universe = (
        f"{policy_display_label(policy)} [{policy_text}]"
        if policy
        else policy_text
    )
    candidates = watchlist.get("candidates", []) if watchlist else []
    candidate_count = len(candidates) if watchlist else "—"
    chinext_count = sum(classify_board(item.get("code")) == BOARD_CHINEXT for item in candidates if isinstance(item, Mapping))
    star_count = sum(classify_board(item.get("code")) == BOARD_STAR for item in candidates if isinstance(item, Mapping))
    watchlist_sha = file_sha256(watchlist_path) if watchlist_path.is_file() else "—"
    tracker_sha = file_sha256(paths.perf_tracker_file()) if paths.perf_tracker_file().is_file() else "—"
    resolved_status = status or (str(result.get("status")) if result else "—")
    review_status = track.get("status") or review.get("status") or "—"
    shadow_status = shadow_status or "—"
    return "\n".join(
        [
            "# A股每日云端运行",
            "",
            f"- Date: {list_date}",
            f"- Status: {resolved_status}",
            f"- Universe: {universe}",
            f"- Candidate count: {candidate_count}",
            f"- ChiNext candidates: {chinext_count if watchlist else '—'}",
            f"- STAR candidates: {star_count if watchlist else '—'}",
            f"- Strategy: {CURRENT_PROSPECTIVE_STRATEGY}",
            f"- Strategy spec SHA: {STRATEGY_SPEC_SHA256}",
            f"- Watchlist SHA: {watchlist_sha}",
            f"- Tracker SHA: {tracker_sha}",
            f"- Review: {review_status}",
            f"- Shadow: {shadow_status}",
            f"- Shadow prospective epoch start: {shadow_epoch or '—'}",
            f"- Report: {report_status}",
            f"- Runtime-state commit: {state_commit or '—'}",
            "- raw persisted: NO",
            "- prospective input persisted: NO",
            "- Final OOS read: NO",
            "",
        ]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    restore = sub.add_parser("restore")
    restore.add_argument("--state-root", type=Path, required=True)
    restore.add_argument("--data-root", type=Path, required=True)

    persist = sub.add_parser("persist")
    persist.add_argument("--state-root", type=Path, required=True)
    persist.add_argument("--data-root", type=Path, required=True)

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--state-root", type=Path, required=True)
    bootstrap.add_argument("--data-root", type=Path, required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--data-root", type=Path, required=True)
    validate.add_argument("--state-root", type=Path, default=None)

    completed = sub.add_parser("check-completed")
    completed.add_argument("--data-root", type=Path, required=True)
    completed.add_argument("--date", required=True)

    paths = sub.add_parser("list")
    paths.add_argument("--state-root", type=Path, required=True)
    paths.add_argument("--paths-only", action="store_true")

    summary = sub.add_parser("summary")
    summary.add_argument("--data-root", type=Path, required=True)
    summary.add_argument("--date", required=True)
    summary.add_argument("--status", default=None)
    summary.add_argument("--state-commit", default=None)
    summary.add_argument("--result-file", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "restore":
            result = restore_allowlist(args.state_root, args.data_root)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "persist":
            result = persist_allowlist(args.state_root, args.data_root)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "bootstrap":
            result = bootstrap_allowlist(args.state_root, args.data_root)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "validate":
            state_report = validate_state_tree(args.state_root) if args.state_root else None
            data_report = validate_runtime_data(args.data_root)
            print(json.dumps({"status": RUNTIME_STATE_VALID, "state": state_report, "data": data_report}, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "check-completed":
            print(json.dumps(completed_run_status(args.data_root, args.date), ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "list":
            report = validate_state_tree(args.state_root)
            if args.paths_only:
                print("\n".join([RUNTIME_STATE_FILE, *report["files"]]))
            else:
                print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "summary":
            result = _read_result(args.result_file)
            print(build_summary(args.data_root, args.date, status=args.status, state_commit=args.state_commit, result=result))
            return 0
        raise RuntimeStateError(f"unsupported command: {args.command}")
    except (OSError, RuntimeStateError, ValueError) as exc:
        print(json.dumps({"status": RUNTIME_STATE_ERROR, "reason": str(exc)[:1500]}, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
