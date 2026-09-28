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
from c_daily_watchlist import (
    C_DATA_PENDING,
    C_DELIVERY_STATUSES,
    C_FAILED,
    C_NOT_RUN,
    C_SUCCESS_NO_MATCH,
    C_SUCCESS_WITH_MATCHES,
    C_TIMEOUT,
    compose_delivery_html,
    render_unavailable_section,
    write_report,
)
from c_prospective_capture import _safe_output_root
from daily_report_delivery import DeliveryError, delivery_receipt_path, load_delivery_receipt
from c_daily_watchlist import publish_report
from cloud_runtime_state import allowlisted_data_files, validate_state_tree

C_EXECUTION_TIMEOUT_SECONDS = 360
C_TAIL_BUDGET_SECONDS = 600
JOB_TIMEOUT_SECONDS = 7200
B_RESERVE_SECONDS = 300
DELIVERY_REPORT_KIND = "B_PLUS_C_PRESENTATION_V1"


def time_budget_status(started_at: datetime, now: datetime, schedule_cron: str = "",
                       *, b_complete_for_target_date: bool = False) -> dict[str, Any]:
    """Reserve ten minutes for C and five for B's next run or job termination.

    The pre-delivery path calls this after the six canonical B gates and runtime-state
    push, so C may use the bounded window without weakening B. The hard job deadline,
    600 s C budget and 300 s reserve stay unchanged; post-delivery only publishes the
    already-prepared C result and does not run this check.
    """
    start = started_at.astimezone(timezone.utc)
    current = now.astimezone(timezone.utc)
    elapsed = (current - start).total_seconds()
    if elapsed < 0 or elapsed + C_TAIL_BUDGET_SECONDS + B_RESERVE_SECONDS >= JOB_TIMEOUT_SECONDS:
        return {"status": "C_NOT_STARTED_TIME_BUDGET", "reason": "JOB_DEADLINE",
                "b_complete_for_target_date": b_complete_for_target_date}
    dates = [current.date() + timedelta(days=offset) for offset in range(8)]
    upcoming = [datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).replace(hour=hour, minute=17)
                for day in dates if day.weekday() < 5 for hour in (9, 10)]
    next_run = min(item for item in upcoming if item > current)
    if not b_complete_for_target_date:
        if current + timedelta(seconds=C_TAIL_BUDGET_SECONDS + B_RESERVE_SECONDS) >= next_run:
            return {"status": "C_NOT_STARTED_TIME_BUDGET", "reason": "NEXT_B_SCHEDULE",
                    "b_complete_for_target_date": b_complete_for_target_date}
        # The primary B run may finish after its retry was queued under the shared lock.
        if schedule_cron == "17 9 * * 1-5" and current.hour >= 10:
            return {"status": "C_NOT_STARTED_TIME_BUDGET", "reason": "PRIMARY_OVERLAPS_RETRY",
                    "b_complete_for_target_date": b_complete_for_target_date}
        if not schedule_cron and current.weekday() < 5 and (
            (current.hour == 9 and current.minute < 47)
            or current.hour == 10
            or (current.hour == 11 and current.minute < 17)
        ):
            return {"status": "C_NOT_STARTED_TIME_BUDGET", "reason": "MANUAL_NEAR_B_SCHEDULE",
                    "b_complete_for_target_date": b_complete_for_target_date}
    return {"status": "C_BUDGET_READY", "remaining_job_seconds": int(JOB_TIMEOUT_SECONDS - elapsed),
            "next_b_schedule_utc": next_run.isoformat(), "c_tail_budget_seconds": C_TAIL_BUDGET_SECONDS,
            "b_complete_for_target_date": b_complete_for_target_date}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _formal_result_gate(result: Mapping[str, Any]) -> bool:
    bundle = result.get("daily_close_bundle") or {}
    if (result.get("status") != "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED"
            or result.get("acquisition_timing") == "AUTHORIZED_WEEKEND_BACKFILL"
            or bundle.get("status") not in {"READY", "REVIEW_OBSERVATION_INCOMPLETE_REPORT_READY"}
            or (bundle.get("track_perf") or {}).get("status") != "SUCCESS"
            or (bundle.get("renderer") or {}).get("status") != "SUCCESS"
            or (bundle.get("cloud_checkpoint") or {}).get("status") != "DRIVE_CHECKPOINT_DISABLED_FOR_CLOUD"):
        return False
    return True


def _same_bytes(left: Path, right: Path) -> bool:
    try:
        return left.is_file() and right.is_file() and _sha(left) == _sha(right)
    except OSError:
        return False


def _state_has_formal_identity(data_root: Path, state_root: Path) -> bool:
    """Require the post-push runtime-state tree to contain the exact B allowlist."""

    try:
        if not state_root.is_dir() or not (state_root / "data").is_dir():
            return False
        for source, relative in allowlisted_data_files(data_root):
            # The delivery receipt is written only after the user-facing
            # attachment succeeds.  It is therefore not part of the
            # pre-delivery Formal B identity gate.
            if relative.parts and relative.parts[0] == "delivery":
                continue
            if not _same_bytes(source, state_root / "data" / relative):
                return False
    except (OSError, ValueError):
        return False
    return True


def b_formal_is_complete(result: Mapping[str, Any], data_root: Path, state_root: Path) -> bool:
    """Verify Formal B and its canonical runtime-state persistence, before delivery."""

    if not _formal_result_gate(result):
        return False
    bundle = result.get("daily_close_bundle") or {}
    watchlist = result.get("watchlist") or {}
    package = result.get("input_package") or {}
    try:
        package_path = Path(package["path"])
        watchlist_path = Path(watchlist["path"])
        report_path = Path(bundle["dated_html"])
        if (not package_path.is_file() or _sha(package_path) != package["file_sha256"]
                or not watchlist_path.is_file() or _sha(watchlist_path) != watchlist["file_sha256"]
                or not report_path.is_file() or report_path.parent != data_root / "reports"
                or not _state_has_formal_identity(data_root, state_root)):
            return False
    except (KeyError, OSError, TypeError, ValueError):
        return False
    return True


def b_is_complete(result: Mapping[str, Any], delivery: Mapping[str, Any], data_root: Path,
                  state_root: Path) -> bool:
    """Verify Formal B plus the persisted delivery receipt, after delivery."""

    if not b_formal_is_complete(result, data_root, state_root):
        return False
    bundle = result.get("daily_close_bundle") or {}
    try:
        report_path = Path(bundle["dated_html"])
        receipt_path = delivery_receipt_path(data_root, result["as_of_date"])
        persisted_receipt = state_root / "data" / "delivery" / receipt_path.name
        receipt = load_delivery_receipt(data_root, result["as_of_date"])
        if (delivery.get("status") not in {"DELIVERY_SUCCESS", "ALREADY_DELIVERED"}
                or delivery.get("receipt_status") != "PERSISTED"
                or not receipt
                or receipt["report_sha256"] != _sha(report_path)
                or not persisted_receipt.is_file()
                or persisted_receipt.read_bytes() != receipt_path.read_bytes()):
            return False
    except (DeliveryError, KeyError, OSError, TypeError, ValueError):
        return False
    return True


def run(result: Mapping[str, Any], delivery: Mapping[str, Any], *,
        data_root: Path, state_root: Path, evidence_root: Path, report_root: Path) -> dict[str, Any]:
    del delivery
    if not b_formal_is_complete(result, data_root, state_root):
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
        return {"status": "C_DAILY_RESEARCH_REPORT_READY", "c_status": report["c_status"],
                "observation": consumed, "report": report}
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


def _c_delivery_status(c_result: Mapping[str, Any] | None) -> str:
    value = c_result if isinstance(c_result, Mapping) else {}
    raw = str(value.get("status") or "")
    if raw == "C_DAILY_RESEARCH_REPORT_READY":
        report = value.get("report") if isinstance(value.get("report"), Mapping) else {}
        status = str(value.get("c_status") or report.get("c_status") or "")
        return status if status in C_DELIVERY_STATUSES else C_FAILED
    if raw in {"C_TIMEOUT_B_UNCHANGED", "C_TIMEOUT", "C_TAIL_PROCESS"}:
        return C_TIMEOUT
    if raw in {"C_NOT_RUN", "C_NOT_STARTED_TIME_BUDGET", "C_NOT_STARTED_C_RESULT_UNAVAILABLE",
               "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"}:
        return C_NOT_RUN
    if raw.startswith("C_FAILED") or raw in {"C_REPORT_PUBLISH_FAILED_B_UNCHANGED", "C_DELIVERY_PREPARATION_FAILED"}:
        return C_FAILED
    return C_FAILED


def _c_section(c_result: Mapping[str, Any] | None, c_status: str) -> str | None:
    if c_status not in {C_SUCCESS_WITH_MATCHES, C_SUCCESS_NO_MATCH, C_DATA_PENDING}:
        return None
    value = c_result if isinstance(c_result, Mapping) else {}
    report = value.get("report") if isinstance(value.get("report"), Mapping) else {}
    section_path = Path(str(report.get("section_path") or ""))
    try:
        section = section_path.read_text(encoding="utf-8")
        if report.get("section_sha256") and _sha(section_path) != report["section_sha256"]:
            return None
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return section


def build_composite_delivery(
    result: Mapping[str, Any],
    c_result: Mapping[str, Any] | None,
    *,
    delivery_root: Path,
) -> dict[str, Any]:
    """Create the presentation-only B+C HTML while preserving the canonical B file."""

    bundle = result.get("daily_close_bundle") or {}
    formal_path = Path(str(bundle["dated_html"]))
    formal_bytes = formal_path.read_bytes()
    formal_sha = _sha(formal_path)
    c_status = _c_delivery_status(c_result)
    section = _c_section(c_result, c_status)
    if section is None:
        section = render_unavailable_section(str(result["as_of_date"]), c_status)
    composite = compose_delivery_html(formal_bytes, section)
    delivery_root.mkdir(parents=True, exist_ok=True)
    token = str(result["as_of_date"]).replace("-", "")
    delivery_path = delivery_root / f"delivery_daily_{token}.html"
    delivery_path.write_bytes(composite)
    if _sha(formal_path) != formal_sha:
        raise RuntimeError("B_FORMAL_BYTES_CHANGED")
    return {
        "status": "C_DELIVERY_READY",
        "c_status": c_status,
        "formal_report_sha256": formal_sha,
        "delivery_report_kind": DELIVERY_REPORT_KIND,
        "delivery_report_path": str(delivery_path),
        "delivery_report_sha256": _sha(delivery_path),
    }


def prepare_delivery(
    *,
    b_result: Path,
    data_root: Path,
    state_root: Path,
    evidence_root: Path,
    report_root: Path,
    delivery_root: Path,
    started_at: datetime,
    schedule_cron: str = "",
    now: datetime | None = None,
    c_enabled: bool = True,
) -> dict[str, Any]:
    """Compute C once, then always prepare a user-facing B+C/fallback presentation."""

    try:
        result = json.loads(b_result.read_text(encoding="utf-8").splitlines()[-1])
    except (OSError, IndexError, ValueError) as exc:
        return {"status": "C_DELIVERY_PREPARATION_FAILED", "reason": type(exc).__name__}
    if not b_formal_is_complete(result, data_root, state_root):
        return {"status": "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"}

    c_result: dict[str, Any]
    if not c_enabled:
        c_result = {"status": C_NOT_RUN, "reason": "FEATURE_DISABLED"}
    else:
        budget = time_budget_status(
            started_at,
            now or datetime.now(timezone.utc),
            schedule_cron,
            b_complete_for_target_date=True,
        )
        if budget["status"] != "C_BUDGET_READY":
            c_result = {"status": C_NOT_RUN, "reason": budget.get("reason", "TIME_BUDGET")}
        else:
            try:
                # Keep the C execution bounded in a child process.  The child
                # receives the same frozen B result and durable roots; the
                # parent only consumes its JSON result and then builds the
                # fallback/composite presentation.
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--b-result", str(b_result),
                    "--delivery-result", str(b_result),
                    "--data-root", str(data_root),
                    "--state-root", str(state_root),
                    "--evidence-root", str(evidence_root),
                    "--report-root", str(report_root),
                ]
                c_result = _run_c_child(command)
            except subprocess.TimeoutExpired:
                c_result = {"status": "C_TIMEOUT_B_UNCHANGED"}
            except Exception as exc:  # C is fail-soft after the canonical B push.
                c_result = {"status": "C_FAILED_B_UNCHANGED", "reason": type(exc).__name__}

    try:
        prepared = build_composite_delivery(result, c_result, delivery_root=delivery_root)
    except Exception as exc:
        return {"status": "C_DELIVERY_PREPARATION_FAILED", "c_status": _c_delivery_status(c_result),
                "reason": type(exc).__name__}
    prepared["c_result"] = c_result
    return prepared


def prepare_fallback_delivery(*, report_date: str, formal_report_path: Path,
                               delivery_root: Path) -> dict[str, Any]:
    """Build the explicit C_NOT_RUN presentation for an already-complete B retry."""

    result = {
        "as_of_date": report_date,
        "daily_close_bundle": {"dated_html": str(formal_report_path)},
    }
    prepared = build_composite_delivery(
        result,
        {"status": C_NOT_RUN, "reason": "ALREADY_COMPLETED_B_NO_C_RESULT"},
        delivery_root=delivery_root,
    )
    prepared["c_result"] = {"status": C_NOT_RUN, "reason": "ALREADY_COMPLETED_B_NO_C_RESULT"}
    return prepared


def post_b(*, b_result: Path, delivery_result: Path, data_root: Path, state_root: Path,
           evidence_root: Path | None = None, report_root: Path | None = None,
           started_at: datetime | None = None,
           prepared_result: Path | None = None,
           schedule_cron: str = "", now: datetime | None = None) -> dict[str, Any]:
    """Publish the already-computed C result; never rerun C after delivery."""
    del evidence_root, report_root, started_at, schedule_cron, now
    try:
        result = json.loads(b_result.read_text(encoding="utf-8").splitlines()[-1])
        delivery = json.loads(delivery_result.read_text(encoding="utf-8").splitlines()[-1])
    except (OSError, IndexError, ValueError) as exc:
        return {"status": "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE", "reason": type(exc).__name__}
    if not b_is_complete(result, delivery, data_root, state_root):
        return {"status": "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"}
    if prepared_result is None:
        return {"status": "C_NOT_STARTED_C_RESULT_UNAVAILABLE"}
    try:
        prepared = json.loads(prepared_result.read_text(encoding="utf-8").splitlines()[-1])
    except (OSError, IndexError, ValueError):
        return {"status": "C_NOT_STARTED_C_RESULT_UNAVAILABLE"}
    c_result = prepared.get("c_result") if isinstance(prepared.get("c_result"), Mapping) else None
    c_status = _c_delivery_status(c_result)
    if c_status not in {C_SUCCESS_WITH_MATCHES, C_SUCCESS_NO_MATCH, C_DATA_PENDING}:
        return {"status": "C_NOT_PUBLISHED_C_UNAVAILABLE", "c_status": c_status}
    report = c_result.get("report") if isinstance(c_result, Mapping) else None
    if not isinstance(report, Mapping) or report.get("status") != "C_DAILY_REPORT_READY":
        return {"status": "C_NOT_PUBLISHED_C_UNAVAILABLE", "c_status": c_status}
    stage = "VERIFY_C_REPORT"
    try:
        published = publish_report(report, state_root)
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
                "package_sha256": report["package_sha256"],
                "html_sha256": published["html_sha256"],
                "manifest_sha256": published["manifest_sha256"],
                "matched_stock_count": published["matched_stock_count"],
                "c_status": c_status}
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyError) as exc:
        return {"status": "C_REPORT_PUBLISH_FAILED_B_UNCHANGED", "stage": stage,
                "reason": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-delivery", action="store_true")
    parser.add_argument("--prepare-fallback", action="store_true")
    parser.add_argument("--post-b", action="store_true")
    parser.add_argument("--enable-c", action="store_true")
    parser.add_argument("--job-started-at-utc")
    parser.add_argument("--schedule-cron", default="")
    parser.add_argument("--b-result", type=Path)
    parser.add_argument("--delivery-result", type=Path)
    parser.add_argument("--prepared-result", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--report-root", type=Path)
    parser.add_argument("--delivery-root", type=Path)
    parser.add_argument("--as-of-date")
    parser.add_argument("--formal-report-path", type=Path)
    args = parser.parse_args()
    if sum(bool(value) for value in (args.prepare_delivery, args.prepare_fallback, args.post_b)) > 1:
        parser.error("--prepare-delivery, --prepare-fallback and --post-b are mutually exclusive")
    if args.prepare_delivery:
        if (not args.b_result or not args.data_root or not args.state_root or not args.job_started_at_utc
                or not args.evidence_root or not args.report_root or not args.delivery_root):
            parser.error("--prepare-delivery requires B result, roots and job start")
        outcome = prepare_delivery(
            b_result=args.b_result,
            data_root=args.data_root,
            state_root=args.state_root,
            evidence_root=args.evidence_root,
            report_root=args.report_root,
            delivery_root=args.delivery_root,
            started_at=datetime.fromisoformat(args.job_started_at_utc.replace("Z", "+00:00")),
            schedule_cron=args.schedule_cron,
            c_enabled=args.enable_c,
        )
    elif args.prepare_fallback:
        if not args.as_of_date or not args.formal_report_path or not args.delivery_root:
            parser.error("--prepare-fallback requires date, formal report and delivery root")
        outcome = prepare_fallback_delivery(
            report_date=args.as_of_date,
            formal_report_path=args.formal_report_path,
            delivery_root=args.delivery_root,
        )
    elif args.post_b:
        if not args.b_result or not args.delivery_result or not args.prepared_result or not args.data_root or not args.state_root:
            parser.error("--post-b requires B/delivery/prepared results and roots")
        outcome = post_b(b_result=args.b_result, delivery_result=args.delivery_result,
                         data_root=args.data_root, state_root=args.state_root,
                         prepared_result=args.prepared_result)
    else:
        if not args.b_result or not args.delivery_result or not args.data_root or not args.state_root or not args.evidence_root or not args.report_root:
            parser.error("C execution requires B/delivery results and roots")
        result = json.loads(args.b_result.read_text(encoding="utf-8").splitlines()[-1])
        delivery = json.loads(args.delivery_result.read_text(encoding="utf-8").splitlines()[-1])
        outcome = run(result, delivery, data_root=args.data_root, state_root=args.state_root,
                      evidence_root=args.evidence_root, report_root=args.report_root)
    print(json.dumps(outcome, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
