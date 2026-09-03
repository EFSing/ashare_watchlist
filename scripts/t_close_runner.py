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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from data_paths import DataPaths
from development_candidate import (
    DevelopmentCandidateStore,
    RUN_ALREADY_CURRENT,
    RUN_NO_CANDIDATES,
    RUN_SUCCESS,
)
from live_acquisition import (
    HITHINK_API_KEY_ENV,
    LiveAcquisitionError,
    acquire_live_generation_inputs,
    persist_live_input_package,
)
from trading_calendar import CalendarUnavailable, default_calendar


_BJT = timezone(timedelta(hours=8))
RUNNABLE_STATUSES = {RUN_SUCCESS, RUN_ALREADY_CURRENT, RUN_NO_CANDIDATES}


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


def _preflight(as_of_date: str, data_root: Path, evidence_root: Path) -> dict[str, Any]:
    calendar = default_calendar()
    try:
        session_close = calendar.session_close(as_of_date)
    except CalendarUnavailable as exc:
        return {
            "status": "CALENDAR_CONTEXT_NOT_READY",
            "as_of_date": as_of_date,
            "detail": type(exc).__name__,
        }
    _check_writable(data_root)
    _check_writable(evidence_root)
    now_bjt = datetime.now(_BJT)
    credential_ready = bool(os.environ.get(HITHINK_API_KEY_ENV, "").strip())
    status = "PRE_CLOSE_DIAGNOSTIC_READY" if now_bjt < session_close else "POST_CLOSE_DIAGNOSTIC_READY"
    if not credential_ready:
        status = "SCHEDULED_TASK_CREDENTIAL_CONTEXT_NOT_READY"
    return {
        "status": status,
        "as_of_date": as_of_date,
        "session_close_bjt": session_close.isoformat(),
        "now_bjt": now_bjt.isoformat(),
        "provider_calls": "NOT_RUN_BEFORE_T_CLOSE",
        "credential_context": "READY" if credential_ready else "MISSING_HITHINK_FINANCE_API_KEY",
        "python": sys.executable,
        "code_git_sha": _git_sha(),
        "data_root": str(data_root),
        "evidence_root": str(evidence_root),
        "packages": {
            "requests": _package_version("requests"),
            "akshare": _package_version("akshare"),
            "exchange_calendars": _package_version("exchange-calendars"),
        },
    }


def run(as_of_date: str, data_root: Path, evidence_root: Path, now_bjt: str | None = None) -> dict[str, Any]:
    code_git_sha = _git_sha()
    package = acquire_live_generation_inputs(
        as_of_date,
        now_bjt=now_bjt,
        evidence_root=evidence_root,
        code_git_sha=code_git_sha,
    )
    persisted = persist_live_input_package(package, data_root)
    candidate = DevelopmentCandidateStore(data_root).generate(
        package.generation_input_manifest,
        names=package.display_names,
        market_env=package.market_env,
    )
    if candidate.status not in RUNNABLE_STATUSES:
        raise RuntimeError(f"development candidate generation failed: {candidate.status}")
    return {
        "status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED",
        "as_of_date": package.generation_input_manifest.signal_date,
        "code_git_sha": code_git_sha,
        "evidence_capture": package.provenance.get("evidence_capture"),
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
        "postprocess": "NOT_CONFIGURED_EXTERNAL_UPLOAD",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of-date", required=True, help="T trading date, YYYY-MM-DD")
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--evidence-root", type=Path, default=None)
    parser.add_argument("--now-bjt", default=None, help="Optional aware timestamp for controlled execution")
    parser.add_argument("--preflight", action="store_true", help="Validate the scheduled execution context without provider calls")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = (args.data_root or DataPaths.from_env().root).expanduser().resolve()
    evidence_root = (args.evidence_root or data_root / "t_close_evidence").expanduser().resolve()
    try:
        result = (
            _preflight(args.as_of_date, data_root, evidence_root)
            if args.preflight
            else run(args.as_of_date, data_root, evidence_root, args.now_bjt)
        )
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
    return 0 if result.get("status") not in {"CALENDAR_CONTEXT_NOT_READY", "SCHEDULED_TASK_CREDENTIAL_CONTEXT_NOT_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
