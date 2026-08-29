"""Create a resumable checkpoint from interrupted core replay streams.

This utility never evaluates strategy logic.  It only compares rows already
written by a replay worker with the frozen T-day candidate counts, preserves
the interrupted stream, and emits a clean stream containing complete dates.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import core_signal_replay as replay  # noqa: E402


CHECKPOINT_SCHEMA = "CORE_SIGNAL_VALIDATION_RESUME_CHECKPOINT_V1"


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_rows(path: Path, *, tolerate_truncated: bool = False) -> Iterator[dict[str, Any]]:
    """Yield valid JSON rows and allow a truncated gzip tail to be reported."""

    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    break
                if not isinstance(row, dict):
                    raise RuntimeError(f"non-object replay row in {path}")
                yield row
    except EOFError:
        if not tolerate_truncated:
            raise


def _scan_partial(path: Path) -> dict[str, Any]:
    date_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    first_date: str | None = None
    last_date: str | None = None
    row_count = 0
    gzip_readable = True
    gzip_error: str | None = None
    try:
        for row in _iter_rows(path):
            signal_date = str(row.get("signal_date", ""))
            if not signal_date:
                raise RuntimeError(f"replay row lacks signal_date in {path}")
            if first_date is None:
                first_date = signal_date
            last_date = signal_date
            date_counts[signal_date] += 1
            status_counts[str(row.get("status", ""))] += 1
            row_count += 1
    except (EOFError, gzip.BadGzipFile, OSError) as exc:
        gzip_readable = False
        gzip_error = f"{type(exc).__name__}: {exc}"
    return {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "gzip_readable": gzip_readable,
        "gzip_error": gzip_error,
        "rows_read": row_count,
        "first_signal_date": first_date,
        "last_signal_date": last_date,
        "observed_date_counts": dict(sorted(date_counts.items())),
        "observed_status_counts": dict(sorted(status_counts.items())),
    }


def _date_ranges(values: list[str]) -> list[dict[str, Any]]:
    if not values:
        return []
    ranges: list[dict[str, Any]] = []
    start = previous = values[0]
    count = 1
    for current in values[1:]:
        if current <= previous:
            raise RuntimeError("signal dates are not strictly increasing")
        # These are ranges in the frozen XSHG-session sequence, so weekends
        # and exchange holidays do not split a range.
        if date.fromisoformat(current).toordinal() - date.fromisoformat(previous).toordinal() == 1:
            count += 1
        else:
            ranges.append({"start": start, "end": previous, "count": count})
            start = current
            count = 1
        previous = current
    ranges.append({"start": start, "end": previous, "count": count})
    return ranges


def _clean_completed_stream(source_path: Path, output_path: Path, completed_dates: set[str]) -> dict[str, Any] | None:
    if not completed_dates:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with output_path.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as output:
                for row in _iter_rows(source_path, tolerate_truncated=True):
                    if row["signal_date"] not in completed_dates:
                        continue
                    output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                    rows += 1
    summary = replay._stream_summary(output_path)
    return {
        "path": output_path.as_posix(),
        "bytes": output_path.stat().st_size,
        "sha256": _file_sha256(output_path),
        "rows": rows,
        "projection_stream_sha256": summary["projection_stream_sha256"],
        "status_counts": summary["status_counts"],
        "per_date": summary["per_date"],
    }


def _checkpoint_part(
    *,
    raw_dir: Path,
    part_dir: Path,
    partition_start: str,
    partition_end: str,
    expected_by_date: dict[str, int],
    source_metadata: dict[str, Any],
) -> dict[str, Any]:
    partial_path = part_dir / "core_replay_results.jsonl.gz"
    if not partial_path.exists() or partial_path.stat().st_size == 0:
        scan = {
            "path": partial_path.as_posix(),
            "bytes": 0 if not partial_path.exists() else partial_path.stat().st_size,
            "sha256": None if not partial_path.exists() else _file_sha256(partial_path),
            "gzip_readable": False,
            "gzip_error": "no replay rows were durably written",
            "rows_read": 0,
            "first_signal_date": None,
            "last_signal_date": None,
            "observed_date_counts": {},
            "observed_status_counts": {},
        }
    else:
        scan = _scan_partial(partial_path)

    partition_dates = [
        signal_date for signal_date in expected_by_date
        if partition_start <= signal_date <= partition_end
    ]
    observed = scan["observed_date_counts"]
    completed_dates: list[str] = []
    for signal_date in partition_dates:
        if observed.get(signal_date, 0) != expected_by_date[signal_date]:
            break
        completed_dates.append(signal_date)
    completed_set = set(completed_dates)
    pending_dates = partition_dates[len(completed_dates):]
    partial_current_date = pending_dates[0] if pending_dates and observed.get(pending_dates[0], 0) else None
    completed_output = part_dir / "core_replay_results.completed.jsonl.gz"
    completed_artifact = _clean_completed_stream(partial_path, completed_output, completed_set) if completed_set else None
    if completed_artifact is None and completed_output.exists():
        completed_output.unlink()

    manifest_path = part_dir / "core_signal_validation_manifest.json"
    frozen_manifest = ROOT / "data" / "validation" / "core_signal_validation" / "core_signal_validation_manifest.json"
    resume_start = pending_dates[0] if pending_dates else None
    resume_output_dir = part_dir.with_name(part_dir.name + "_resume")
    command = None
    if resume_start is not None:
        command = (
            "python scripts/core_signal_replay.py "
            f"--raw-dir {raw_dir.as_posix()} "
            f"--output-dir {resume_output_dir.as_posix()} "
            "--schedule continuous --engine formula "
            f"--start-date {resume_start} --end-date {partition_end}"
        )
    checkpoint: dict[str, Any] = {
        "schema_version": CHECKPOINT_SCHEMA,
        "validation_layer": replay.CORE_SIGNAL_VALIDATION,
        "dataset_version": replay.CONTINUOUS_DATASET_VERSION,
        "schedule": "continuous_xshg_sessions_within_frozen_validation_interval",
        "sector_semantics": {
            "historical_membership_included": False,
            "sector_score_status": "UNVERIFIED",
            "sector_report_status": "UNVERIFIED",
            "taxonomy_substitution": False,
        },
        "forbidden_scope": {
            "final_oos_read": False,
            "return_metrics_computed": False,
            "strategy_validation_started": False,
        },
        "partition": {
            "requested_start": partition_start,
            "requested_end": partition_end,
            "actual_signal_dates_start": partition_dates[0] if partition_dates else None,
            "actual_signal_dates_end": partition_dates[-1] if partition_dates else None,
        },
        "progress": {
            "completed_signal_dates": completed_dates,
            "completed_date_count": len(completed_dates),
            "completed_start": completed_dates[0] if completed_dates else None,
            "completed_end": completed_dates[-1] if completed_dates else None,
            "last_completed_trade_date": completed_dates[-1] if completed_dates else None,
            "partial_current_date": partial_current_date,
            "pending_signal_dates": pending_dates,
            "pending_ranges": _date_ranges(pending_dates),
            "expected_candidate_evaluations_completed": sum(expected_by_date[d] for d in completed_dates),
            "observed_rows_in_interrupted_stream": scan["rows_read"],
        },
        "expected_candidate_count_by_date": {d: expected_by_date[d] for d in partition_dates},
        "interrupted_output": scan,
        "completed_output": completed_artifact,
        "manifest": {
            "part_manifest_status": "ABSENT_UNTIL_PART_IS_COMPLETE" if not manifest_path.exists() else "PRESENT",
            "part_manifest": None if not manifest_path.exists() else {
                "path": manifest_path.as_posix(),
                "bytes": manifest_path.stat().st_size,
                "sha256": _file_sha256(manifest_path),
            },
            "frozen_14_day_manifest": None if not frozen_manifest.exists() else {
                "path": frozen_manifest.as_posix(),
                "bytes": frozen_manifest.stat().st_size,
                "sha256": _file_sha256(frozen_manifest),
            },
        },
        "source": {
            "raw_dir": raw_dir.as_posix(),
            "content_sha256": source_metadata["content_sha256"],
            "files": source_metadata["files"],
        },
        "resume": {
            "required_start_date": resume_start,
            "output_dir": resume_output_dir.as_posix(),
            "command": command,
            "merge_completed_output_first": None if completed_artifact is None else completed_artifact["path"],
            "merge_instruction": (
                "After resume, merge the completed output followed by the resume output; then run the full "
                "continuous manifest builder only after every expected signal date is present."
            ),
            "requires_matching_raw_input_hash": source_metadata["content_sha256"],
        },
        "checkpoint_status": "PAUSED_INCOMPLETE_CONTINUOUS_REPLAY",
    }
    checkpoint["checkpoint_sha256"] = _sha256_json(checkpoint)
    checkpoint_path = part_dir / "core_signal_validation_resume_checkpoint.json"
    with checkpoint_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return checkpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--parts-root", type=Path, required=True)
    args = parser.parse_args()

    index_dates, _, _ = replay._load_index(args.raw_dir)
    stock_store, _ = replay._load_stock_store(args.raw_dir / "daily_k.parquet")
    all_signal_dates = replay._continuous_signal_dates(index_dates)
    coverage = replay._coverage_by_date(stock_store, all_signal_dates, index_dates)
    expected_by_date = {key: value["evaluable_symbol_count"] for key, value in coverage.items()}
    source_metadata = replay._source_metadata(args.raw_dir)
    part_checkpoints = [
        _checkpoint_part(
            raw_dir=args.raw_dir,
            part_dir=args.parts_root / "part_a",
            partition_start="2023-06-30",
            partition_end="2024-12-31",
            expected_by_date=expected_by_date,
            source_metadata=source_metadata,
        ),
        _checkpoint_part(
            raw_dir=args.raw_dir,
            part_dir=args.parts_root / "part_b",
            partition_start="2025-01-01",
            partition_end="2026-08-28",
            expected_by_date=expected_by_date,
            source_metadata=source_metadata,
        ),
    ]
    part_refs = []
    for part_checkpoint in part_checkpoints:
        part_path = Path(part_checkpoint["partition"]["requested_start"] == "2023-06-30" and args.parts_root / "part_a" or args.parts_root / "part_b") / "core_signal_validation_resume_checkpoint.json"
        progress = part_checkpoint["progress"]
        part_refs.append(
            {
                "path": part_path.as_posix(),
                "bytes": part_path.stat().st_size,
                "sha256": _file_sha256(part_path),
                "checkpoint_sha256": part_checkpoint["checkpoint_sha256"],
                "partition": part_checkpoint["partition"],
                "last_completed_trade_date": progress["last_completed_trade_date"],
                "completed_date_count": progress["completed_date_count"],
                "completed_candidate_evaluations": progress["expected_candidate_evaluations_completed"],
                "partial_current_date": progress["partial_current_date"],
                "pending_date_count": len(progress["pending_signal_dates"]),
                "resume": part_checkpoint["resume"],
                "completed_output": part_checkpoint["completed_output"],
                "interrupted_output": part_checkpoint["interrupted_output"],
            }
        )
    results = {
        "schema_version": CHECKPOINT_SCHEMA,
        "dataset_version": replay.CONTINUOUS_DATASET_VERSION,
        "signal_date_count": len(all_signal_dates),
        "signal_dates_start": all_signal_dates[0],
        "signal_dates_end": all_signal_dates[-1],
        "source_content_sha256": source_metadata["content_sha256"],
        "sector_score_status": "UNVERIFIED",
        "full_legacy_output_validation": "BLOCKED_HISTORICAL_SINA_MEMBERSHIP",
        "return_metrics_computed": False,
        "parts": part_refs,
    }
    results["checkpoint_sha256"] = _sha256_json(results)
    root_path = args.parts_root / "core_signal_validation_resume_checkpoint.json"
    with root_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "path": root_path.as_posix(),
        "bytes": root_path.stat().st_size,
        "sha256": _file_sha256(root_path),
        "checkpoint_sha256": results["checkpoint_sha256"],
        "signal_date_count": results["signal_date_count"],
        "parts": [
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "last_completed_trade_date": item["last_completed_trade_date"],
                "completed_date_count": item["completed_date_count"],
                "partial_current_date": item["partial_current_date"],
                "pending_date_count": item["pending_date_count"],
            }
            for item in part_refs
        ],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
