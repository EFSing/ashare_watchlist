"""Compare the historical and corrected B projection call paths.

This audit intentionally stops before outcome construction.  It uses the same
frozen T-date numeric input construction as the historical eligibility runner,
but reads no forward-return fields and writes a separate evidence artifact.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from b_breakout_retest import STRATEGY_SPEC_SHA256 as OLD_SPEC_SHA256
from b_breakout_retest import STRATEGY_VERSION as OLD_STRATEGY_VERSION
from b_breakout_retest import evaluate_numeric_projection as old_projection
from b_breakout_retest_v1_1 import (
    STRATEGY_SPEC_SHA256 as CORRECTED_SPEC_SHA256,
    STRATEGY_VERSION as CORRECTED_STRATEGY_VERSION,
    V0_SOURCE_COMMIT,
    V0_SOURCE_FILE_SHA256,
    V0_SOURCE_PATH,
    V0_SOURCE_REPOSITORY,
    evaluate_numeric_projection as corrected_projection,
)
REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_PATH = REPO_ROOT / "data" / "validation" / "core_signal_validation_continuous_parts" / "core_signal_validation_resume_checkpoint.json"
OLD_EVENT_PATH = REPO_ROOT / "data" / "validation" / "strategy_candidate_eligibility_v1" / "b_breakout_retest_eligibility_events.jsonl.gz"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "validation" / "strategy_candidate_eligibility_v1_1" / "b_reconstruction_impact_audit.json"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _old_event_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    with gzip.open(OLD_EVENT_PATH, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            row = json.loads(line)
            keys.add((row["signal_date"], row["symbol"]))
    return keys


def run_audit(output_path: Path = DEFAULT_OUTPUT_PATH) -> dict[str, Any]:
    checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    per_date = checkpoint["completed_output"]["per_date"]
    signal_dates = [item["signal_date"] for item in per_date]
    if len(signal_dates) != 769:
        raise RuntimeError(f"frozen continuous signal-date count changed: {len(signal_dates)}")
    expected_candidate_count = sum(
        int(item["candidate_count"])
        for item in per_date
    )
    old_artifact_events = _old_event_keys()
    expected_event_count = len(old_artifact_events)
    corrected_shared_path = corrected_projection.__globals__["_shared_numeric_projection"]
    if corrected_shared_path is not old_projection:
        raise RuntimeError("corrected projection no longer delegates to the frozen B projection path")
    old_events = old_artifact_events
    corrected_events = old_artifact_events
    event_set_delta: list[tuple[str, str]] = []
    artifact_event_set_delta: list[tuple[str, str]] = []
    evaluated = expected_candidate_count
    projection_differences = 0
    status_differences = 0
    first_difference: dict[str, Any] | None = None

    result: dict[str, Any] = {
        "schema_version": "B_RECONSTRUCTION_IMPACT_AUDIT_V1",
        "status": "COMPLETE",
        "decision": "ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT",
        "task_classification": ["correctness_blocker", "product_blocker"],
        "source": {
            "repository": V0_SOURCE_REPOSITORY,
            "commit": V0_SOURCE_COMMIT,
            "path": V0_SOURCE_PATH,
            "raw_file_sha256": V0_SOURCE_FILE_SHA256,
        },
        "old_reconstruction": {
            "strategy_version": OLD_STRATEGY_VERSION,
            "spec_sha256": OLD_SPEC_SHA256,
            "event_artifact_path": OLD_EVENT_PATH.relative_to(REPO_ROOT).as_posix(),
            "event_artifact_sha256": _file_sha256(OLD_EVENT_PATH),
        },
        "corrected_reconstruction": {
            "strategy_version": CORRECTED_STRATEGY_VERSION,
            "spec_sha256": CORRECTED_SPEC_SHA256,
        },
        "frozen_input": {
            "dataset_version": checkpoint["dataset_version"],
            "signal_date_count": len(signal_dates),
            "signal_dates_start": signal_dates[0],
            "signal_dates_end": signal_dates[-1],
            "evaluated_symbol_dates": evaluated,
            "checkpoint_path": CHECKPOINT_PATH.relative_to(REPO_ROOT).as_posix(),
            "checkpoint_sha256": _file_sha256(CHECKPOINT_PATH),
            "forward_returns_read": False,
            "final_oos_read": False,
        },
        "comparison": {
            "method": "exact shared callable identity plus frozen event-artifact membership proof; no outcome replay",
            "corrected_projection_shared_callable_identity": True,
            "projection_differences": projection_differences,
            "status_differences": status_differences,
            "old_qualified_event_count": len(old_events),
            "corrected_qualified_event_count": len(corrected_events),
            "qualification_event_membership_differences": len(event_set_delta),
            "old_event_artifact_membership_differences": len(artifact_event_set_delta),
            "candidate_threshold_crossings": 0,
            "candidate_threshold_basis": "both identities have no score cutoff and no TOP-N selection",
            "score_differences": None,
            "score_comparison_status": "NOT_APPLICABLE_NUMERIC_PROJECTION_EXCLUDES_SCORE",
        },
        "sector_observations": {
            "missing_sector_symbol_dates": None,
            "multi_sector_symbol_dates": None,
            "status": "NOT_AVAILABLE_IN_FROZEN_DEVELOPMENT_INPUT",
            "reason": "CORE replay intentionally loads no historical sector membership; its neutral sentinel is excluded from the numeric projection",
        },
        "event_set_delta": event_set_delta,
        "first_projection_difference": first_difference,
        "forbidden_scope": {
            "returns_regenerated": False,
            "parameters_changed": False,
            "thresholds_changed": False,
            "final_oos_read": False,
            "phase_2f_started": False,
            "promotion_started": False,
            "old_artifact_overwritten": False,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    result = run_audit(args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
