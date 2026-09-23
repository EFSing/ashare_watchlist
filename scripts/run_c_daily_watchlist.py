"""Run C from a completed B runner's frozen package without a provider call."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from c_b_input_adapter import consume_b_input
from c_daily_watchlist import write_report
from c_prospective_capture import _safe_output_root


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def b_is_complete(result: Mapping[str, Any], delivery: Mapping[str, Any], data_root: Path) -> bool:
    bundle = result.get("daily_close_bundle") or {}
    watchlist = result.get("watchlist") or {}
    package = result.get("input_package") or {}
    if (result.get("status") != "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED"
            or result.get("acquisition_timing") == "AUTHORIZED_WEEKEND_BACKFILL"
            or bundle.get("status") not in {"READY", "REVIEW_OBSERVATION_INCOMPLETE_REPORT_READY"}
            or (bundle.get("track_perf") or {}).get("status") != "SUCCESS"
            or (bundle.get("renderer") or {}).get("status") != "SUCCESS"
            or (bundle.get("cloud_checkpoint") or {}).get("status") != "DRIVE_CHECKPOINT_DISABLED_FOR_CLOUD"
            or delivery.get("status") not in {"DELIVERY_SUCCESS", "ALREADY_DELIVERED"}):
        return False
    try:
        package_path = Path(package["path"])
        watchlist_path = Path(watchlist["path"])
        report_path = Path(bundle["dated_html"])
        if (not package_path.is_file() or _sha(package_path) != package["file_sha256"]
                or not watchlist_path.is_file() or _sha(watchlist_path) != watchlist["file_sha256"]
                or not report_path.is_file() or report_path.parent != data_root / "reports"):
            return False
    except (KeyError, OSError, TypeError):
        return False
    return True


def run(result: Mapping[str, Any], delivery: Mapping[str, Any], *,
        data_root: Path, evidence_root: Path, report_root: Path) -> dict[str, Any]:
    if not b_is_complete(result, delivery, data_root):
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-result", type=Path, required=True)
    parser.add_argument("--delivery-result", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.b_result.read_text(encoding="utf-8").splitlines()[-1])
    delivery = json.loads(args.delivery_result.read_text(encoding="utf-8").splitlines()[-1])
    print(json.dumps(run(result, delivery, data_root=args.data_root,
                         evidence_root=args.evidence_root, report_root=args.report_root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
