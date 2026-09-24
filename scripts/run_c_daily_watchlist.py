"""Run C from a completed B runner's frozen package without a provider call."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from c_b_input_adapter import consume_b_input
from c_daily_watchlist import write_report
from c_prospective_capture import _safe_output_root
from daily_report_delivery import DeliveryError, delivery_receipt_path, load_delivery_receipt
from c_daily_watchlist import publish_report
from cloud_runtime_state import validate_state_tree

C_EXECUTION_TIMEOUT_SECONDS = 360
C_TAIL_BUDGET_SECONDS = 600
JOB_TIMEOUT_SECONDS = 7200
B_RESERVE_SECONDS = 300


def time_budget_status(started_at: datetime, now: datetime, schedule_cron: str = "") -> dict[str, Any]:
    """Reserve ten minutes for C and five for B's next run or job termination."""
    start = started_at.astimezone(timezone.utc)
    current = now.astimezone(timezone.utc)
    elapsed = (current - start).total_seconds()
    if elapsed < 0 or elapsed + C_TAIL_BUDGET_SECONDS + B_RESERVE_SECONDS >= JOB_TIMEOUT_SECONDS:
        return {"status": "C_NOT_STARTED_TIME_BUDGET", "reason": "JOB_DEADLINE"}
    dates = [current.date() + timedelta(days=offset) for offset in range(8)]
    upcoming = [datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).replace(hour=hour, minute=17)
                for day in dates if day.weekday() < 5 for hour in (9, 10)]
    next_run = min(item for item in upcoming if item > current)
    if current + timedelta(seconds=C_TAIL_BUDGET_SECONDS + B_RESERVE_SECONDS) >= next_run:
        return {"status": "C_NOT_STARTED_TIME_BUDGET", "reason": "NEXT_B_SCHEDULE"}
    # The primary B run may finish after its retry was queued under the shared lock.
    if schedule_cron == "17 9 * * 1-5" and current.hour >= 10:
        return {"status": "C_NOT_STARTED_TIME_BUDGET", "reason": "PRIMARY_OVERLAPS_RETRY"}
    if not schedule_cron and current.weekday() < 5 and (
        (current.hour == 9 and current.minute < 47)
        or current.hour == 10
        or (current.hour == 11 and current.minute < 17)
    ):
        return {"status": "C_NOT_STARTED_TIME_BUDGET", "reason": "MANUAL_NEAR_B_SCHEDULE"}
    return {"status": "C_BUDGET_READY", "remaining_job_seconds": int(JOB_TIMEOUT_SECONDS - elapsed),
            "next_b_schedule_utc": next_run.isoformat(), "c_tail_budget_seconds": C_TAIL_BUDGET_SECONDS}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def b_is_complete(result: Mapping[str, Any], delivery: Mapping[str, Any], data_root: Path,
                  state_root: Path) -> bool:
    bundle = result.get("daily_close_bundle") or {}
    watchlist = result.get("watchlist") or {}
    package = result.get("input_package") or {}
    if (result.get("status") != "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED"
            or result.get("acquisition_timing") == "AUTHORIZED_WEEKEND_BACKFILL"
            or bundle.get("status") not in {"READY", "REVIEW_OBSERVATION_INCOMPLETE_REPORT_READY"}
            or (bundle.get("track_perf") or {}).get("status") != "SUCCESS"
            or (bundle.get("renderer") or {}).get("status") != "SUCCESS"
            or (bundle.get("cloud_checkpoint") or {}).get("status") != "DRIVE_CHECKPOINT_DISABLED_FOR_CLOUD"
            or delivery.get("status") not in {"DELIVERY_SUCCESS", "ALREADY_DELIVERED"}
            or delivery.get("receipt_status") != "PERSISTED"):
        return False
    try:
        package_path = Path(package["path"])
        watchlist_path = Path(watchlist["path"])
        report_path = Path(bundle["dated_html"])
        receipt_path = delivery_receipt_path(data_root, result["as_of_date"])
        persisted_receipt = state_root / "data" / "delivery" / receipt_path.name
        receipt = load_delivery_receipt(data_root, result["as_of_date"])
        if (not package_path.is_file() or _sha(package_path) != package["file_sha256"]
                or not watchlist_path.is_file() or _sha(watchlist_path) != watchlist["file_sha256"]
                or not report_path.is_file() or report_path.parent != data_root / "reports"
                or not receipt or receipt["report_sha256"] != _sha(report_path)
                or not persisted_receipt.is_file()
                or persisted_receipt.read_bytes() != receipt_path.read_bytes()):
            return False
    except (DeliveryError, KeyError, OSError, TypeError, ValueError):
        return False
    return True


def run(result: Mapping[str, Any], delivery: Mapping[str, Any], *,
        data_root: Path, state_root: Path, evidence_root: Path, report_root: Path) -> dict[str, Any]:
    if not b_is_complete(result, delivery, data_root, state_root):
        return {"status": "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"}
    package = result["input_package"]
    formal_paths = [Path(package["path"]), Path(result["watchlist"]["path"]),
                    Path(result["daily_close_bundle"]["dated_html"]),
                    data_root / "reports" / "latest.html"]
    before = {str(path): _sha(path) for path in formal_paths if path.is_file()}
    try:
        consumed = consume_b_input(package["path"], target_date=result["as_of_date"],
                                   expected_sha256=package["file_sha256"],
                                   local_runner_input=True, evidence_root=evidence_root)
        record = _safe_output_root() / consumed["record"]
        report = write_report(record, report_root)
        if any(_sha(Path(path)) != digest for path, digest in before.items()):
            raise RuntimeError("B_FORMAL_BYTES_CHANGED")
        return {"status": "C_DAILY_RESEARCH_REPORT_READY", "observation": consumed, "report": report}
    except Exception as exc:
        if any(not Path(path).is_file() or _sha(Path(path)) != digest for path, digest in before.items()):
            return {"status": "C_FAILED_B_MUTATION_DETECTED", "reason": f"{type(exc).__name__}: {exc}"}
        return {"status": "C_FAILED_B_UNCHANGED", "reason": f"{type(exc).__name__}: {exc}"}


def _git(state_root: Path, *args: str, timeout: int = 60) -> bytes:
    completed = subprocess.run(["git", *args], cwd=state_root, check=True,
                               capture_output=True, timeout=timeout)
    return completed.stdout


def _run_c_child(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True, check=True,
                               timeout=C_EXECUTION_TIMEOUT_SECONDS)
    return json.loads(completed.stdout.strip().splitlines()[-1])


def post_b(*, b_result: Path, delivery_result: Path, data_root: Path, state_root: Path,
           evidence_root: Path, report_root: Path, started_at: datetime,
           schedule_cron: str = "", now: datetime | None = None) -> dict[str, Any]:
    """Bound C's work and publish only C paths; every outcome remains independent of B."""
    try:
        result = json.loads(b_result.read_text(encoding="utf-8").splitlines()[-1])
        delivery = json.loads(delivery_result.read_text(encoding="utf-8").splitlines()[-1])
    except (OSError, IndexError, ValueError) as exc:
        return {"status": "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE", "reason": type(exc).__name__}
    if not b_is_complete(result, delivery, data_root, state_root):
        return {"status": "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"}
    budget = time_budget_status(started_at, now or datetime.now(timezone.utc), schedule_cron)
    if budget["status"] != "C_BUDGET_READY":
        return budget
    command = [sys.executable, str(Path(__file__).resolve()),
               "--b-result", str(b_result), "--delivery-result", str(delivery_result),
               "--data-root", str(data_root), "--state-root", str(state_root),
               "--evidence-root", str(evidence_root), "--report-root", str(report_root)]
    try:
        c_result = _run_c_child(command)
    except subprocess.TimeoutExpired:
        return {"status": "C_TIMEOUT_B_UNCHANGED", "timeout_seconds": C_EXECUTION_TIMEOUT_SECONDS}
    except (subprocess.CalledProcessError, IndexError, ValueError):
        return {"status": "C_FAILED_B_UNCHANGED", "reason": "C_PROCESS_FAILED"}
    if c_result.get("status") != "C_DAILY_RESEARCH_REPORT_READY":
        return {"status": c_result.get("status", "C_FAILED_B_UNCHANGED"),
                "reason": "C_OBSERVATION_OR_REPORT_UNAVAILABLE"}
    stage = "VERIFY_C_REPORT"
    try:
        published = publish_report(c_result["report"], state_root)
        validate_state_tree(state_root)
        stage = "STAGE_C_PATHS"
        if _git(state_root, "diff", "--cached", "--name-only").strip():
            raise ValueError("runtime-state already has staged paths")
        _git(state_root, "add", "--", *published["paths"])
        staged = set(_git(state_root, "diff", "--cached", "--name-only").decode().splitlines())
        if not staged.issubset(set(published["paths"])):
            raise ValueError("non-C runtime-state paths staged")
        _git(state_root, "diff", "--cached", "--check")
        stage = "COMMIT_C_REPORT"
        if staged:
            _git(state_root, "config", "user.name", "github-actions[bot]")
            _git(state_root, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
            _git(state_root, "commit", "-m", f"runtime: publish C research report {published['signal_date']}")
            stage = "PUSH_C_REPORT"
            _git(state_root, "push", "origin", "HEAD:runtime-state", timeout=90)
        stage = "REMOTE_READBACK"
        _git(state_root, "fetch", "origin", "runtime-state", timeout=90)
        remote_head = _git(state_root, "rev-parse", "FETCH_HEAD").decode().strip()
        for path in published["paths"]:
            local = (state_root / path).read_bytes()
            remote = _git(state_root, "show", f"FETCH_HEAD:{path}")
            if remote != local:
                raise ValueError("C remote readback SHA mismatch")
        return {"status": "C_DAILY_REPORT_PUBLISHED", "runtime_state_sha": remote_head,
                "paths": published["paths"], "signal_date": published["signal_date"],
                "package_sha256": c_result["report"]["package_sha256"],
                "html_sha256": published["html_sha256"],
                "manifest_sha256": published["manifest_sha256"],
                "matched_stock_count": published["matched_stock_count"],
                "c_budget": budget}
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyError) as exc:
        return {"status": "C_REPORT_PUBLISH_FAILED_B_UNCHANGED", "stage": stage,
                "reason": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--post-b", action="store_true")
    parser.add_argument("--job-started-at-utc")
    parser.add_argument("--schedule-cron", default="")
    parser.add_argument("--b-result", type=Path, required=True)
    parser.add_argument("--delivery-result", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    args = parser.parse_args()
    if args.post_b:
        if not args.job_started_at_utc:
            parser.error("--post-b requires --job-started-at-utc")
        outcome = post_b(b_result=args.b_result, delivery_result=args.delivery_result,
                         data_root=args.data_root, state_root=args.state_root,
                         evidence_root=args.evidence_root, report_root=args.report_root,
                         started_at=datetime.fromisoformat(args.job_started_at_utc.replace("Z", "+00:00")),
                         schedule_cron=args.schedule_cron)
    else:
        result = json.loads(args.b_result.read_text(encoding="utf-8").splitlines()[-1])
        delivery = json.loads(args.delivery_result.read_text(encoding="utf-8").splitlines()[-1])
        outcome = run(result, delivery, data_root=args.data_root, state_root=args.state_root,
                      evidence_root=args.evidence_root, report_root=args.report_root)
    print(json.dumps(outcome, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
