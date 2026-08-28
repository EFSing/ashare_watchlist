"""Finalize a checkpointed continuous core replay without rerunning dates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import core_signal_replay as replay


CHECKPOINT_SCHEMA = "CORE_SIGNAL_VALIDATION_RESUME_CHECKPOINT_V1"


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _output_metadata(path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "rows": summary["total_candidate_evaluations"],
        "projection_stream_sha256": summary["projection_stream_sha256"],
        "status_counts": summary["status_counts"],
        "per_date": summary["per_date"],
    }


def _finalize_part(
    *,
    old_path: Path,
    final_output_path: Path,
    source_metadata: dict[str, Any],
) -> dict[str, Any]:
    old = _load(old_path)
    summary = replay._stream_summary(final_output_path)
    expected = old["expected_candidate_count_by_date"]
    observed = {item["signal_date"]: item["candidate_count"] for item in summary["per_date"]}
    if list(observed) != list(expected) or observed != expected:
        raise RuntimeError(f"final output coverage does not match checkpoint expectations: {old_path}")

    completed_dates = list(expected)
    completed_output = _output_metadata(final_output_path, summary)
    progress = dict(old["progress"])
    progress.update(
        {
            "completed_signal_dates": completed_dates,
            "completed_date_count": len(completed_dates),
            "completed_start": completed_dates[0] if completed_dates else None,
            "completed_end": completed_dates[-1] if completed_dates else None,
            "last_completed_trade_date": completed_dates[-1] if completed_dates else None,
            "partial_current_date": None,
            "pending_signal_dates": [],
            "pending_ranges": [],
            "expected_candidate_evaluations_completed": summary["total_candidate_evaluations"],
        }
    )
    resume = dict(old["resume"])
    resume.update(
        {
            "required_start_date": None,
            "command": None,
            "merge_completed_output_first": completed_output["path"],
            "merge_instruction": "Continuous replay is complete; no resume is required.",
            "requires_matching_raw_input_hash": source_metadata["content_sha256"],
        }
    )
    checkpoint = dict(old)
    checkpoint.update(
        {
            "progress": progress,
            "completed_output": completed_output,
            "source": {
                **old["source"],
                "content_sha256": source_metadata["content_sha256"],
                "files": source_metadata["files"],
            },
            "resume": resume,
            "checkpoint_status": "COMPLETE_CONTINUOUS_REPLAY",
        }
    )
    checkpoint.pop("checkpoint_sha256", None)
    checkpoint["checkpoint_sha256"] = _sha256_json(checkpoint)
    _write_json(old_path, checkpoint)
    return checkpoint


def _part_ref(path: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    progress = checkpoint["progress"]
    return {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "partition": checkpoint["partition"],
        "last_completed_trade_date": progress["last_completed_trade_date"],
        "completed_date_count": progress["completed_date_count"],
        "completed_candidate_evaluations": progress["expected_candidate_evaluations_completed"],
        "partial_current_date": progress["partial_current_date"],
        "pending_date_count": len(progress["pending_signal_dates"]),
        "resume": checkpoint["resume"],
        "completed_output": checkpoint["completed_output"],
        "interrupted_output": checkpoint["interrupted_output"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--parts-root", type=Path, required=True)
    parser.add_argument("--final-output", type=Path, required=True)
    args = parser.parse_args()

    source_metadata = replay._source_metadata(args.raw_dir)
    part_a_path = args.parts_root / "part_a" / "core_signal_validation_resume_checkpoint.json"
    part_b_path = args.parts_root / "part_b" / "core_signal_validation_resume_checkpoint.json"
    part_a = _finalize_part(
        old_path=part_a_path,
        final_output_path=args.parts_root / "part_a_final" / "core_replay_results.jsonl.gz",
        source_metadata=source_metadata,
    )
    part_b = _finalize_part(
        old_path=part_b_path,
        final_output_path=args.parts_root / "part_b_final" / "core_replay_results.jsonl.gz",
        source_metadata=source_metadata,
    )
    final_summary = replay._stream_summary(args.final_output)
    if final_summary["total_candidate_evaluations"] != (
        part_a["progress"]["expected_candidate_evaluations_completed"]
        + part_b["progress"]["expected_candidate_evaluations_completed"]
    ):
        raise RuntimeError("root output candidate count does not equal finalized part counts")
    root = {
        "schema_version": CHECKPOINT_SCHEMA,
        "dataset_version": replay.CONTINUOUS_DATASET_VERSION,
        "signal_date_count": len(final_summary["per_date"]),
        "signal_dates_start": final_summary["per_date"][0]["signal_date"],
        "signal_dates_end": final_summary["per_date"][-1]["signal_date"],
        "source_content_sha256": source_metadata["content_sha256"],
        "sector_score_status": "UNVERIFIED",
        "full_legacy_output_validation": "BLOCKED_HISTORICAL_SINA_MEMBERSHIP",
        "return_metrics_computed": False,
        "checkpoint_status": "COMPLETE_CONTINUOUS_REPLAY",
        "completed_output": _output_metadata(args.final_output, final_summary),
        "parts": [_part_ref(part_a_path, part_a), _part_ref(part_b_path, part_b)],
    }
    root["checkpoint_sha256"] = _sha256_json(root)
    root_path = args.parts_root / "core_signal_validation_resume_checkpoint.json"
    _write_json(root_path, root)
    print(json.dumps({
        "path": root_path.as_posix(),
        "sha256": _file_sha256(root_path),
        "checkpoint_sha256": root["checkpoint_sha256"],
        "source_content_sha256": root["source_content_sha256"],
        "signal_date_count": root["signal_date_count"],
        "candidate_evaluations": root["completed_output"]["rows"],
        "parts": [
            {
                "checkpoint_sha256": checkpoint["checkpoint_sha256"],
                "completed_date_count": checkpoint["progress"]["completed_date_count"],
                "last_completed_trade_date": checkpoint["progress"]["last_completed_trade_date"],
                "pending_date_count": len(checkpoint["progress"]["pending_signal_dates"]),
            }
            for checkpoint in (part_a, part_b)
        ],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
