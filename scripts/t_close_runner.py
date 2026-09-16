"""One-shot T-close acquisition and development-candidate runner.

The runner has one write order: immutable source evidence first, then the
complete generation-input package, then the existing B evaluator's canonical
watchlist lifecycle.  It does not alter strategy rules or publish to an
external service.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from data_paths import DATA_ROOT_ENV, DataPaths
from development_candidate import (
    B_STRATEGY_BINDING,
    DevelopmentCandidateStore,
    RUN_ALREADY_CURRENT,
    RUN_NO_CANDIDATES,
    RUN_SUCCESS,
)
from live_acquisition import (
    AUTHORIZED_WEEKEND_BACKFILL,
    HITHINK_API_KEY_ENV,
    LiveAcquisitionError,
    _validate_close_window,
    acquire_live_generation_inputs,
    persist_live_input_package,
)
from trading_calendar import CalendarUnavailable, default_calendar
from upload_daily_checkpoint import (
    CLOUD_CHECKPOINT_FAILED,
    CheckpointError,
    prepare_local_checkpoint,
    upload_checkpoint,
)


_BJT = timezone(timedelta(hours=8))
RUNNABLE_STATUSES = {RUN_SUCCESS, RUN_ALREADY_CURRENT, RUN_NO_CANDIDATES}
T_CLOSE_SUCCESS_STATUS = "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED"

# The desktop app can inject its authenticated Drive adapter here. The
# standalone runner deliberately has no credentials or second Drive SDK.
DAILY_CLOUD_CHECKPOINT_CLIENT: Any | None = None
DAILY_CLOUD_ROOT_FOLDER_ID_ENV = "ASHARE_DAILY_CLOUD_ROOT_FOLDER_ID"
DISABLE_DRIVE_CHECKPOINT_ENV = "ASHARE_DISABLE_DRIVE_CHECKPOINT"
DRIVE_CHECKPOINT_DISABLED = "DRIVE_CHECKPOINT_DISABLED_FOR_CLOUD"


def _bounded_process_detail(completed: subprocess.CompletedProcess[str]) -> str:
    detail = "\n".join(part.strip() for part in (completed.stdout or "", completed.stderr or "") if part.strip())
    return detail[:2000] or f"process exited with code {completed.returncode}"


def _daily_cloud_checkpoint(as_of_date: str, data_root: Path, *, tracker_failure: str | None) -> dict[str, Any]:
    """Prepare the local checkpoint and optionally use the injected Drive adapter."""

    if tracker_failure:
        return {
            "status": CLOUD_CHECKPOINT_FAILED,
            "reason": "TRACKER_NOT_READY",
            "detail": tracker_failure,
            "message": "[CLOUD] FAILED TRACKER_NOT_READY",
        }
    try:
        prepared = prepare_local_checkpoint(as_of_date, data_root=data_root)
    except (CheckpointError, OSError, ValueError) as exc:
        reason = str(exc)[:1000]
        return {
            "status": CLOUD_CHECKPOINT_FAILED,
            "reason": reason,
            "message": f"[CLOUD] FAILED {reason}",
        }

    if os.environ.get(DISABLE_DRIVE_CHECKPOINT_ENV, "").strip() == "1":
        return {
            "status": DRIVE_CHECKPOINT_DISABLED,
            "reason": "explicit cloud deployment mode; local manifest retained",
            "manifest_path": prepared["manifest_path"],
            "manifest_sha256": prepared["persist"]["sha256"],
            "message": "[CLOUD] DRIVE CHECKPOINT DISABLED",
        }

    root_folder_id = os.environ.get(DAILY_CLOUD_ROOT_FOLDER_ID_ENV, "").strip()
    if DAILY_CLOUD_CHECKPOINT_CLIENT is None or not root_folder_id:
        reason = "DRIVE_CONNECTOR_NOT_CONFIGURED"
        return {
            "status": CLOUD_CHECKPOINT_FAILED,
            "reason": reason,
            "manifest_path": prepared["manifest_path"],
            "manifest_sha256": prepared["persist"]["sha256"],
            "message": f"[CLOUD] FAILED {reason}",
        }
    try:
        result = upload_checkpoint(
            prepared["manifest"],
            data_root=data_root,
            client=DAILY_CLOUD_CHECKPOINT_CLIENT,
            root_folder_id=root_folder_id,
            manifest_path=Path(prepared["manifest_path"]),
        )
    except (CheckpointError, OSError, ValueError) as exc:
        reason = str(exc)[:1000]
        return {
            "status": CLOUD_CHECKPOINT_FAILED,
            "reason": reason,
            "manifest_path": prepared["manifest_path"],
            "manifest_sha256": prepared["persist"]["sha256"],
            "message": f"[CLOUD] FAILED {reason}",
        }
    result["manifest_path"] = prepared["manifest_path"]
    result["manifest_sha256"] = prepared["persist"]["sha256"]
    result["message"] = "[CLOUD] VERIFIED"
    return result


def _daily_shadow_update(as_of_date: str, data_root: Path) -> dict[str, Any]:
    """Update observational shadow outcomes without making it a report gate."""

    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment[DATA_ROOT_ENV] = str(data_root)
    command = [
        sys.executable,
        str(project_root / "scripts" / "b_shadow_monitor.py"),
        "update",
        "--date",
        str(as_of_date),
        "--data-root",
        str(data_root),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {"status": "SHADOW_CAPTURE_INCOMPLETE", "detail": f"launch failed: {type(exc).__name__}: {exc}"}
    detail = _bounded_process_detail(completed)
    if completed.returncode == 0:
        try:
            parsed = json.loads((completed.stdout or "").strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            parsed = {"status": "SHADOW_CAPTURE_INCOMPLETE", "detail": detail}
        return parsed if isinstance(parsed, dict) else {"status": "SHADOW_CAPTURE_INCOMPLETE", "detail": detail}
    return {"status": "SHADOW_CAPTURE_INCOMPLETE", "detail": detail, "exit_code": completed.returncode}


def _run_daily_close_reporting(as_of_date: str, data_root: Path) -> dict[str, Any]:
    """Run tracker then renderer after a successful canonical watchlist write.

    The tracker is intentionally allowed to fail without suppressing the
    canonical-list HTML delivery.  Its exact bounded failure detail is passed
    to the renderer so the report remains actionable instead of silently
    presenting stale review state as current.
    """

    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment[DATA_ROOT_ENV] = str(data_root)
    python = sys.executable
    tracker_command = [
        python,
        str(project_root / "scripts" / "track_perf.py"),
        "all",
        "--date",
        str(as_of_date),
    ]
    try:
        tracker_run = subprocess.run(
            tracker_command,
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        tracker_run = None
        tracker_failure = f"track_perf launch failed: {type(exc).__name__}: {exc}"
    else:
        tracker_failure = None if tracker_run.returncode == 0 else (
            f"track_perf exit {tracker_run.returncode}: {_bounded_process_detail(tracker_run)}"
        )

    coverage: dict[str, Any] | None = None
    tracker_path = data_root / "perf_tracker.json"
    if tracker_path.exists():
        try:
            tracker_payload = json.loads(tracker_path.read_text(encoding="utf-8"))
            raw_coverage = tracker_payload.get("review_coverage")
            normalized_as_of = str(as_of_date).replace("-", "")
            coverage_date = str(raw_coverage.get("report_date", "")).replace("-", "") if isinstance(raw_coverage, dict) else ""
            if isinstance(raw_coverage, dict) and coverage_date == normalized_as_of:
                coverage = raw_coverage
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            coverage = None

    shadow_monitor = _daily_shadow_update(as_of_date, data_root)

    renderer_command = [
        python,
        str(project_root / "scripts" / "render_daily_close_html.py"),
        "--date",
        str(as_of_date).replace("-", ""),
    ]
    if tracker_failure:
        renderer_command.extend(["--review-failure", tracker_failure])
    try:
        renderer_run = subprocess.run(
            renderer_command,
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {
            "status": "REPORT_FAILED",
            "track_perf": {
                "status": "FAILED" if tracker_failure else "SUCCESS",
                "detail": tracker_failure,
                "exit_code": tracker_run.returncode if tracker_run is not None else None,
            },
            "renderer": {"status": "LAUNCH_FAILED", "detail": f"{type(exc).__name__}: {exc}"},
        }

    renderer_detail = _bounded_process_detail(renderer_run)
    if renderer_run.returncode != 0:
        bundle_status = "REPORT_FAILED"
    elif tracker_failure:
        bundle_status = "REVIEW_FAILED_REPORT_READY"
    elif coverage and coverage.get("status") == "REVIEW_OBSERVATION_INCOMPLETE":
        bundle_status = "REVIEW_OBSERVATION_INCOMPLETE_REPORT_READY"
    else:
        bundle_status = "READY"
    cloud_checkpoint = (
        _daily_cloud_checkpoint(as_of_date, data_root, tracker_failure=tracker_failure)
        if renderer_run.returncode == 0
        else {
            "status": CLOUD_CHECKPOINT_FAILED,
            "reason": "HTML_NOT_READY",
            "message": "[CLOUD] FAILED HTML_NOT_READY",
        }
    )
    return {
        "status": bundle_status,
        "shadow_monitor": shadow_monitor,
        "track_perf": {
            "status": "FAILED" if tracker_failure else "SUCCESS",
            "detail": tracker_failure or _bounded_process_detail(tracker_run),
            "exit_code": tracker_run.returncode if tracker_run is not None else None,
            "review_coverage": coverage,
        },
        "renderer": {
            "status": "SUCCESS" if renderer_run.returncode == 0 else "FAILED",
            "detail": renderer_detail,
            "exit_code": renderer_run.returncode,
        },
        "cloud_checkpoint": cloud_checkpoint,
        "dated_html": str(data_root / "reports" / f"daily_close_{str(as_of_date).replace('-', '')}.html"),
        "latest_html": str(data_root / "reports" / "latest.html"),
    }


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN_ORIGIN"
    return completed.stdout.strip() or "UNKNOWN_ORIGIN"


def _package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "UNKNOWN_ORIGIN"


def _check_writable(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=root, prefix=".tclose-preflight-", suffix=".tmp"):
        pass


def _preflight(
    as_of_date: str,
    data_root: Path,
    evidence_root: Path,
    *,
    allow_weekend_backfill: bool = False,
    now_bjt: datetime | None = None,
) -> dict[str, Any]:
    calendar = default_calendar()
    now_bjt = now_bjt or datetime.now(_BJT)
    target_date = date.fromisoformat(str(as_of_date).replace("/", "-")).isoformat()
    actual_acquisition_date = now_bjt.date().isoformat()
    weekend_backfill = actual_acquisition_date != target_date
    acquisition_timing = (
        AUTHORIZED_WEEKEND_BACKFILL
        if weekend_backfill and allow_weekend_backfill
        else "SAME_CALENDAR_DATE"
    )

    package_versions = {
        "requests": _package_version("requests"),
        "akshare": _package_version("akshare"),
        "exchange_calendars": _package_version("exchange-calendars"),
    }
    packages_ready = all(value != "UNKNOWN_ORIGIN" for value in package_versions.values())
    credential_ready = bool(os.environ.get(HITHINK_API_KEY_ENV, "").strip())
    _check_writable(data_root)
    _check_writable(evidence_root)

    try:
        is_session = calendar.is_trading_day(target_date)
    except CalendarUnavailable as exc:
        return {
            "status": "CALENDAR_UNAVAILABLE",
            "as_of_date": target_date,
            "target_session": target_date,
            "actual_acquisition_date": actual_acquisition_date,
            "now_bjt": now_bjt.isoformat(),
            "acquisition_timing": acquisition_timing,
            "provider_calls": "NOT_RUN",
            "xshg_session": "UNKNOWN",
            "credential_context": "READY" if credential_ready else "MISSING_HITHINK_FINANCE_API_KEY",
            "runtime_packages": "READY" if packages_ready else "NOT_READY",
            "detail": str(exc)[:1000],
            "packages": package_versions,
        }

    if not is_session:
        return {
            "status": "SKIPPED_NON_TRADING_DAY",
            "as_of_date": target_date,
            "target_session": target_date,
            "actual_acquisition_date": actual_acquisition_date,
            "now_bjt": now_bjt.isoformat(),
            "acquisition_timing": acquisition_timing,
            "provider_calls": "NOT_RUN",
            "xshg_session": "NO",
            "session_close_passed": "NOT_APPLICABLE",
            "data_root_writable": True,
            "evidence_root_writable": True,
            "credential_context": "READY" if credential_ready else "MISSING_HITHINK_FINANCE_API_KEY",
            "runtime_packages": "READY" if packages_ready else "NOT_READY",
            "python": sys.executable,
            "code_git_sha": _git_sha(),
            "data_root": str(data_root),
            "evidence_root": str(evidence_root),
            "packages": package_versions,
        }
    try:
        session_close = _validate_close_window(
            target_date,
            now_bjt,
            calendar,
            allow_weekend_backfill=allow_weekend_backfill,
        )
    except LiveAcquisitionError as exc:
        return {
            "status": "CLOSE_WINDOW_NOT_READY",
            "as_of_date": target_date,
            "target_session": target_date,
            "actual_acquisition_date": actual_acquisition_date,
            "now_bjt": now_bjt.isoformat(),
            "acquisition_timing": acquisition_timing,
            "allow_weekend_backfill": allow_weekend_backfill,
            "provider_calls": "NOT_RUN",
            "error_status": exc.status,
            "detail": str(exc)[:1000],
        }
    if weekend_backfill:
        status = "AUTHORIZED_WEEKEND_BACKFILL_READY"
    else:
        status = "PRE_CLOSE_DIAGNOSTIC_READY" if now_bjt < session_close else "POST_CLOSE_DIAGNOSTIC_READY"
    if not packages_ready:
        status = "RUNTIME_PACKAGES_NOT_READY"
    elif not credential_ready:
        status = "SCHEDULED_TASK_CREDENTIAL_CONTEXT_NOT_READY"
    return {
        "status": status,
        "as_of_date": target_date,
        "target_session": target_date,
        "actual_acquisition_date": actual_acquisition_date,
        "session_close_bjt": session_close.isoformat(),
        "now_bjt": now_bjt.isoformat(),
        "acquisition_timing": acquisition_timing,
        "authorization": (
            "explicit user-authorized weekend backfill"
            if weekend_backfill
            else "not_applicable"
        ),
        "provider_calls": "NOT_RUN_BEFORE_T_CLOSE",
        "xshg_session": "YES",
        "session_close_passed": True,
        "data_root_writable": True,
        "evidence_root_writable": True,
        "credential_context": "READY" if credential_ready else "MISSING_HITHINK_FINANCE_API_KEY",
        "runtime_packages": "READY" if packages_ready else "NOT_READY",
        "python": sys.executable,
        "code_git_sha": _git_sha(),
        "data_root": str(data_root),
        "evidence_root": str(evidence_root),
        "packages": package_versions,
    }


def run(
    as_of_date: str,
    data_root: Path,
    evidence_root: Path,
    now_bjt: str | None = None,
    *,
    allow_weekend_backfill: bool = False,
) -> dict[str, Any]:
    code_git_sha = _git_sha()
    package = acquire_live_generation_inputs(
        as_of_date,
        now_bjt=now_bjt,
        allow_weekend_backfill=allow_weekend_backfill,
        evidence_root=evidence_root,
        code_git_sha=code_git_sha,
    )
    persisted = persist_live_input_package(package, data_root)
    candidate = DevelopmentCandidateStore(data_root).generate(
        package.generation_input_manifest,
        names=package.display_names,
        market_env=package.market_env,
        strategy_binding=B_STRATEGY_BINDING,
        input_provenance=package.provenance,
    )
    if candidate.status not in RUNNABLE_STATUSES:
        raise RuntimeError(f"development candidate generation failed: {candidate.status}")
    shadow_monitor: dict[str, Any]
    if candidate.output_path is None:
        shadow_monitor = {
            "status": "SHADOW_CAPTURE_INCOMPLETE",
            "detail": "canonical watchlist output path is unavailable",
        }
    else:
        try:
            from b_shadow_monitor import capture_t_close_signals

            shadow_monitor = capture_t_close_signals(
                watchlist_path=candidate.output_path,
                run_manifest_path=candidate.run_manifest_path,
                generation_input_manifest=package.generation_input_manifest.to_dict(),
                market_env=package.market_env,
                input_package_sha256=persisted.file_sha256,
                store_root=data_root / "shadow_monitor",
            )
        except Exception as exc:
            # Shadow monitoring is observational and must not make a formal
            # canonical output unavailable.  Preserve an auditable marker.
            try:
                from b_shadow_monitor import record_capture_failure

                expected = int(candidate.candidate_count or 0)
                record_capture_failure(
                    data_root / "shadow_monitor",
                    signal_date=package.generation_input_manifest.signal_date,
                    expected=expected,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                pass
            shadow_monitor = {
                "status": "SHADOW_CAPTURE_INCOMPLETE",
                "detail": f"{type(exc).__name__}: {exc}",
            }
    return {
        "status": T_CLOSE_SUCCESS_STATUS,
        "as_of_date": package.generation_input_manifest.signal_date,
        "code_git_sha": code_git_sha,
        "evidence_capture": package.provenance.get("evidence_capture"),
        "input_coverage": package.provenance.get("input_coverage"),
        "input_package": {
            "status": persisted.status,
            "path": str(persisted.path),
            "file_sha256": persisted.file_sha256,
        },
        "watchlist": {
            "status": candidate.status,
            "path": str(candidate.output_path) if candidate.output_path else None,
            "file_sha256": candidate.output_sha256,
            "candidate_count": candidate.candidate_count,
            "run_manifest_path": str(candidate.run_manifest_path),
        },
        "shadow_monitor": shadow_monitor,
        "postprocess": "NOT_CONFIGURED_EXTERNAL_UPLOAD",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of-date", required=True, help="T trading date, YYYY-MM-DD")
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--evidence-root", type=Path, default=None)
    parser.add_argument("--now-bjt", default=None, help="Optional aware timestamp for controlled execution")
    parser.add_argument(
        "--allow-weekend-backfill",
        action="store_true",
        help="Explicitly authorize an immediately-following non-trading-day acquisition for the target session",
    )
    parser.add_argument("--preflight", action="store_true", help="Validate the scheduled execution context without provider calls")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = (args.data_root or DataPaths.from_env().root).expanduser().resolve()
    evidence_root = (args.evidence_root or data_root / "t_close_evidence").expanduser().resolve()
    try:
        result = (
            _preflight(
                args.as_of_date,
                data_root,
                evidence_root,
                allow_weekend_backfill=args.allow_weekend_backfill,
            )
            if args.preflight
            else run(
                args.as_of_date,
                data_root,
                evidence_root,
                args.now_bjt,
                allow_weekend_backfill=args.allow_weekend_backfill,
            )
        )
        if not args.preflight and result.get("status") == T_CLOSE_SUCCESS_STATUS and result.get("watchlist", {}).get("path"):
            result["daily_close_bundle"] = _run_daily_close_reporting(args.as_of_date, data_root)
    except (LiveAcquisitionError, OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "T_CLOSE_RUN_FAILED", "error_type": type(exc).__name__, "error_detail": str(exc)[:1000]},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    bundle = result.get("daily_close_bundle")
    if isinstance(bundle, dict) and bundle.get("status") == "REPORT_FAILED":
        return 1
    return 0 if result.get("status") not in {
        "CALENDAR_CONTEXT_NOT_READY",
        "CLOSE_WINDOW_NOT_READY",
        "SCHEDULED_TASK_CREDENTIAL_CONTEXT_NOT_READY",
        "RUNTIME_PACKAGES_NOT_READY",
        "CALENDAR_UNAVAILABLE",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
