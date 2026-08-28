"""Validate descriptive forward outcomes for the completed development replay."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

import core_signal_replay as replay


HORIZONS = (1, 3, 5, 10)
VALIDATION_STATUS = "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_COMPLETE"
RETROSPECTIVE_STATUS = "RECONSTRUCTED_RETROSPECTIVE"


def _checkpoint_sha256(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("checkpoint_sha256", None)
    canonical = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((canonical + "\n").encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_event_results(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0) as compressed:
            for record in records:
                compressed.write((replay.canonical_json(record) + "\n").encode("utf-8"))
    return {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "rows": len(records),
    }


def _verify_frozen_inputs(
    *,
    raw_dir: Path,
    checkpoint_path: Path,
    core_output: Path,
    core_manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    for path in (raw_dir, checkpoint_path, core_output, core_manifest_path):
        if "final_oos" in str(path).lower():
            raise RuntimeError(f"final OOS path is forbidden: {path}")
    root = _load_json(checkpoint_path)
    if root.get("checkpoint_status") != "COMPLETE_CONTINUOUS_REPLAY":
        raise RuntimeError("continuous core checkpoint is not complete")
    if _checkpoint_sha256(root) != root.get("checkpoint_sha256"):
        raise RuntimeError("root checkpoint hash mismatch")
    if root.get("signal_date_count") != 769 or root.get("return_metrics_computed") is not False:
        raise RuntimeError("core checkpoint is not the frozen 769-date core artifact")

    part_checkpoints = []
    for reference in root["parts"]:
        part_path = checkpoint_path.parent.parent / Path(reference["path"]).name
        if reference["path"].replace("\\", "/").endswith("part_a/core_signal_validation_resume_checkpoint.json"):
            part_path = checkpoint_path.parent / "part_a" / "core_signal_validation_resume_checkpoint.json"
        elif reference["path"].replace("\\", "/").endswith("part_b/core_signal_validation_resume_checkpoint.json"):
            part_path = checkpoint_path.parent / "part_b" / "core_signal_validation_resume_checkpoint.json"
        part = _load_json(part_path)
        if _checkpoint_sha256(part) != part.get("checkpoint_sha256"):
            raise RuntimeError(f"part checkpoint hash mismatch: {part_path}")
        if part["checkpoint_status"] != "COMPLETE_CONTINUOUS_REPLAY":
            raise RuntimeError(f"part checkpoint is not complete: {part_path}")
        if part["progress"]["pending_signal_dates"]:
            raise RuntimeError(f"part checkpoint still has pending dates: {part_path}")
        part_checkpoints.append(part)

    source = replay._source_metadata(raw_dir)
    expected_by_identity = {
        item["logical_identity"]: item
        for item in part_checkpoints[0]["source"]["files"]
    }
    for actual in source["files"]:
        expected = expected_by_identity.get(actual["logical_identity"])
        if expected is None or expected["bytes"] != actual["bytes"] or expected["sha256"] != actual["sha256"]:
            raise RuntimeError(f"RAW_SOURCE_SHA_MISMATCH: {actual['filename']}")
    if source["content_sha256"] != root["source_content_sha256"]:
        raise RuntimeError("canonical raw source hash does not match root checkpoint")
    if any(part["source"]["content_sha256"] != source["content_sha256"] for part in part_checkpoints):
        raise RuntimeError("part checkpoint source hash mismatch")

    if _file_sha256(core_output) != root["completed_output"]["sha256"]:
        raise RuntimeError("completed core output file hash mismatch")
    core_summary = replay._stream_summary(core_output)
    if core_summary["total_candidate_evaluations"] != root["completed_output"]["rows"]:
        raise RuntimeError("completed core output row count mismatch")
    manifest = _load_json(core_manifest_path)
    manifest_hash = manifest.get("manifest_sha256")
    manifest_payload = dict(manifest)
    manifest_payload.pop("manifest_sha256", None)
    if replay.sha256_json(manifest_payload) != manifest_hash:
        raise RuntimeError("continuous core manifest hash mismatch")
    if manifest["provenance"]["raw_inputs"]["content_sha256"] != source["content_sha256"]:
        raise RuntimeError("continuous core manifest source hash mismatch")
    return root, part_checkpoints[0], part_checkpoints[1], source, core_summary


def _stock_window(
    *,
    store: dict[str, Any],
    symbol: str,
    expected_dates_ms: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    bounds = store["bounds"].get(symbol)
    if bounds is None:
        return None
    start, end = bounds
    dates = store["date_ms"][start:end]
    first = int(expected_dates_ms[0])
    last = int(expected_dates_ms[-1])
    left = int(np.searchsorted(dates, first, side="left"))
    right = int(np.searchsorted(dates, last, side="right"))
    observed_dates = dates[left:right]
    if not np.array_equal(observed_dates, expected_dates_ms):
        return None
    return (
        store["close"][start + right - 1],
        store["high"][start + left : start + right],
        store["low"][start + left : start + right],
        store["open"][start + left : start + right],
    )


def _build_event_record(
    *,
    row: dict[str, Any],
    store: dict[str, Any],
    session_dates: list[str],
    session_ms: np.ndarray,
    session_index: dict[str, int],
) -> dict[str, Any]:
    signal_date = row["signal_date"]
    symbol = row["symbol"]
    signal_position = session_index[signal_date]
    execution_position = signal_position + 1
    entry_date = (
        session_dates[execution_position]
        if execution_position < len(session_dates)
        else row["earliest_execution_date"]
    )
    if row["earliest_execution_date"] != entry_date:
        raise RuntimeError(f"T+1 timing mismatch for {symbol} at {signal_date}")
    bounds = store["bounds"].get(symbol)
    entry_open: float | None = None
    entry_available = False
    if entry_date is not None and bounds is not None and execution_position < len(session_ms):
        start, end = bounds
        dates = store["date_ms"][start:end]
        entry_ms = session_ms[execution_position]
        entry_index = int(np.searchsorted(dates, entry_ms, side="left"))
        if entry_index < len(dates) and int(dates[entry_index]) == int(entry_ms):
            entry_open = float(store["open"][start + entry_index])
            entry_available = True

    outcomes: dict[str, dict[str, Any]] = {}
    for horizon in HORIZONS:
        key = f"{horizon}D"
        if not entry_available:
            status = "NO_T_PLUS_1_OPEN"
            if bounds is None:
                status = "SYMBOL_NOT_IN_RAW_STORE"
            outcomes[key] = {
                "status": status,
                "target_date": None,
                "return_pct": None,
                "mfe_pct": None,
                "mae_pct": None,
                "expected_session_count": horizon,
                "observed_session_count": 0,
            }
            continue
        target_position = signal_position + horizon
        if target_position >= len(session_dates):
            outcomes[key] = {
                "status": "INSUFFICIENT_FORWARD_COVERAGE",
                "target_date": None,
                "return_pct": None,
                "mfe_pct": None,
                "mae_pct": None,
                "expected_session_count": horizon,
                "observed_session_count": 0,
            }
            continue
        expected_dates_ms = session_ms[execution_position : target_position + 1]
        window = _stock_window(store=store, symbol=symbol, expected_dates_ms=expected_dates_ms)
        if window is None:
            observed_count = 0
            if bounds is not None:
                start, end = bounds
                dates = store["date_ms"][start:end]
                observed_count = int(
                    np.searchsorted(dates, int(expected_dates_ms[-1]), side="right")
                    - np.searchsorted(dates, int(expected_dates_ms[0]), side="left")
                )
            outcomes[key] = {
                "status": "INCOMPLETE_STOCK_WINDOW",
                "target_date": session_dates[target_position],
                "return_pct": None,
                "mfe_pct": None,
                "mae_pct": None,
                "expected_session_count": horizon,
                "observed_session_count": observed_count,
            }
            continue
        target_close, highs, lows, _ = window
        assert entry_open is not None
        outcomes[key] = {
            "status": "AVAILABLE",
            "target_date": session_dates[target_position],
            "target_close": float(target_close),
            "return_pct": (float(target_close) / entry_open - 1.0) * 100.0,
            "mfe_pct": (float(np.max(highs)) / entry_open - 1.0) * 100.0,
            "mae_pct": (float(np.min(lows)) / entry_open - 1.0) * 100.0,
            "expected_session_count": horizon,
            "observed_session_count": horizon,
        }
    return {
        "as_of_date": row["as_of_date"],
        "signal_date": signal_date,
        "earliest_execution_date": row["earliest_execution_date"],
        "symbol": symbol,
        "setup_id": row["setup_id"],
        "entry_date": entry_date,
        "entry_open": entry_open,
        "outcomes": outcomes,
    }


def _metric_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [float(record["return_pct"]) for record in records]
    mfes = [float(record["mfe_pct"]) for record in records]
    maes = [float(record["mae_pct"]) for record in records]
    positive = [value for value in returns if value > 0]
    non_positive = [value for value in returns if value <= 0]
    positive_rate = len(positive) / len(returns) if returns else None
    mean_return = float(np.mean(returns)) if returns else None
    mean_positive = float(np.mean(positive)) if positive else None
    mean_non_positive = float(np.mean(non_positive)) if non_positive else None
    expectancy = (
        positive_rate * mean_positive + (1.0 - positive_rate) * mean_non_positive
        if positive_rate is not None and mean_positive is not None and mean_non_positive is not None
        else mean_return
    )
    return {
        "sample_count": len(records),
        "positive_count": len(positive),
        "non_positive_count": len(non_positive),
        "positive_rate": positive_rate,
        "mean_return_pct": mean_return,
        "mean_positive_return_pct": mean_positive,
        "mean_non_positive_return_pct": mean_non_positive,
        "expectancy_pct": expectancy,
        "mean_mfe_pct": float(np.mean(mfes)) if mfes else None,
        "median_mfe_pct": float(np.median(mfes)) if mfes else None,
        "mean_mae_pct": float(np.mean(maes)) if maes else None,
        "median_mae_pct": float(np.median(maes)) if maes else None,
        "min_return_pct": min(returns) if returns else None,
        "max_return_pct": max(returns) if returns else None,
    }


def _returns_by_period(records: list[dict[str, Any]], period: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        date_text = record["signal_date"]
        key = date_text[:4] if period == "year" else date_text[:7]
        groups[key].append(record)
    return {key: _metric_summary(groups[key]) for key in sorted(groups)}


def _returns_summary(event_records: list[dict[str, Any]]) -> dict[str, Any]:
    by_horizon: dict[str, Any] = {}
    for horizon in HORIZONS:
        key = f"{horizon}D"
        available = [
            record["outcomes"][key]
            | {"signal_date": record["signal_date"], "symbol": record["symbol"]}
            for record in event_records
            if record["outcomes"][key]["status"] == "AVAILABLE"
        ]
        status_counts = Counter(record["outcomes"][key]["status"] for record in event_records)
        by_horizon[key] = {
            **_metric_summary(available),
            "status_counts": dict(sorted(status_counts.items())),
            "censored_or_unavailable_count": len(event_records) - len(available),
            "by_year": _returns_by_period(available, "year"),
            "by_month": _returns_by_period(available, "month"),
        }
    return by_horizon


def _frequency_summary(
    *,
    candidate_counts: dict[str, int],
    a_match_counts: dict[str, int],
    qualified_counts: dict[str, int],
    qualified_by_symbol: Counter[str],
) -> dict[str, Any]:
    def summarize(dates: list[str]) -> dict[str, Any]:
        candidates = sum(candidate_counts[date_text] for date_text in dates)
        a_matches = sum(a_match_counts[date_text] for date_text in dates)
        qualified = sum(qualified_counts[date_text] for date_text in dates)
        return {
            "signal_date_count": len(dates),
            "candidate_count": candidates,
            "a_match_count": a_matches,
            "qualified_count": qualified,
            "a_match_frequency": a_matches / candidates if candidates else None,
            "qualified_frequency": qualified / candidates if candidates else None,
        }

    dates = sorted(candidate_counts)
    years: dict[str, list[str]] = defaultdict(list)
    months: dict[str, list[str]] = defaultdict(list)
    for date_text in dates:
        years[date_text[:4]].append(date_text)
        months[date_text[:7]].append(date_text)
    total_qualified = sum(qualified_by_symbol.values())
    shares = sorted(
        (count / total_qualified for count in qualified_by_symbol.values()),
        reverse=True,
    ) if total_qualified else []
    return {
        "daily": [
            {"signal_date": date_text, **summarize([date_text])}
            for date_text in dates
        ],
        "by_year": {key: summarize(values) for key, values in sorted(years.items())},
        "by_month": {key: summarize(values) for key, values in sorted(months.items())},
        "qualified_signal_event_count": total_qualified,
        "qualified_unique_symbol_count": len(qualified_by_symbol),
        "top1_symbol_share": shares[0] if shares else None,
        "top5_symbol_share": sum(shares[:5]) if shares else None,
        "qualified_symbol_hhi": sum(share * share for share in shares) if shares else None,
        "top_symbols": [
            {"symbol": symbol, "qualified_count": count}
            for symbol, count in sorted(qualified_by_symbol.items(), key=lambda item: (-item[1], item[0]))[:10]
        ],
    }


def run(
    *,
    raw_dir: Path,
    checkpoint_path: Path,
    core_output: Path,
    core_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    root, part_a, part_b, source, core_summary = _verify_frozen_inputs(
        raw_dir=raw_dir,
        checkpoint_path=checkpoint_path,
        core_output=core_output,
        core_manifest_path=core_manifest_path,
    )
    index_dates, _, index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.array([index_dates[date_text] for date_text in session_dates], dtype=np.int64)
    session_index = {date_text: index for index, date_text in enumerate(session_dates)}
    store, stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")

    candidate_counts: dict[str, int] = Counter()
    a_match_counts: dict[str, int] = Counter()
    qualified_counts: dict[str, int] = Counter()
    qualified_by_symbol: Counter[str] = Counter()
    event_records: list[dict[str, Any]] = []
    with gzip.open(core_output, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            row = json.loads(line)
            signal_date = row["signal_date"]
            candidate_counts[signal_date] += 1
            a_match_counts[signal_date] += int(
                set(replay.A_CONDITIONS).issubset(row["matched_conditions"])
            )
            if row["status"] != replay.QUALIFIED_LEGACY_BASELINE:
                continue
            qualified_counts[signal_date] += 1
            qualified_by_symbol[row["symbol"]] += 1
            event_records.append(
                _build_event_record(
                    row=row,
                    store=store,
                    session_dates=session_dates,
                    session_ms=session_ms,
                    session_index=session_index,
                )
            )

    if len(candidate_counts) != root["signal_date_count"] or sum(candidate_counts.values()) != core_summary["total_candidate_evaluations"]:
        raise RuntimeError("core stream coverage changed during development validation")
    if sum(qualified_counts.values()) != len(event_records):
        raise RuntimeError("qualified event accounting mismatch")

    output_path = output_dir / "development_historical_returns.jsonl.gz"
    event_artifact = _write_event_results(output_path, event_records)
    returns = _returns_summary(event_records)
    frequency = _frequency_summary(
        candidate_counts=candidate_counts,
        a_match_counts=a_match_counts,
        qualified_counts=qualified_counts,
        qualified_by_symbol=qualified_by_symbol,
    )
    payload: dict[str, Any] = {
        "schema_version": "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_V1",
        "validation_layer": "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION",
        "data_partition": "development",
        "status": VALIDATION_STATUS,
        "retrospective_status": RETROSPECTIVE_STATUS,
        "dataset_version": replay.CONTINUOUS_DATASET_VERSION,
        "strategy": {
            "version": replay.STRATEGY_VERSION,
            "spec_sha256": replay.STRATEGY_SPEC_SHA256,
            "strategy_source_modified": False,
            "parameter_changes": False,
            "promotion": False,
        },
        "scope": {
            "signal_date_count": len(candidate_counts),
            "signal_dates_start": min(candidate_counts),
            "signal_dates_end": max(candidate_counts),
            "qualified_signal_count": len(event_records),
            "entry": "T+1 XSHG session open from raw daily-K",
            "return_horizons": [f"{horizon}D" for horizon in HORIZONS],
            "mfe_mae": "maximum high and minimum low from T+1 through each horizon, relative to T+1 open",
            "price_semantics": "raw unadjusted OHLC from daily_k.parquet; no future outcome is fed into signal evaluation",
            "positive_rate": "return_pct > 0",
            "expectancy": "positive_rate*mean_positive_return_pct + non_positive_rate*mean_non_positive_return_pct",
        },
        "provenance": {
            "raw_inputs": source,
            "core_checkpoint": {
                "path": checkpoint_path.as_posix(),
                "bytes": checkpoint_path.stat().st_size,
                "sha256": _file_sha256(checkpoint_path),
                "checkpoint_sha256": root["checkpoint_sha256"],
                "source_content_sha256": root["source_content_sha256"],
            },
            "core_output": {
                "path": core_output.as_posix(),
                "bytes": core_output.stat().st_size,
                "sha256": _file_sha256(core_output),
                "projection_stream_sha256": core_summary["projection_stream_sha256"],
                "rows": core_summary["total_candidate_evaluations"],
            },
            "core_manifest": {
                "path": core_manifest_path.as_posix(),
                "bytes": core_manifest_path.stat().st_size,
                "sha256": _file_sha256(core_manifest_path),
            },
            "raw_data_range": {"start": stock_meta["min_date"], "end": stock_meta["max_date"]},
            "benchmark_rows": index_meta["row_count"],
            "known_at_vintage_proof": False,
            "known_at_limitation": "retrospective dump has observation dates and acquisition hash, but no per-bar historical vintage timestamp",
            "final_oos_read": False,
            "historical_sina_membership_included": False,
            "score_85_status": "UNVERIFIED",
            "full_legacy_output_validation": "BLOCKED_HISTORICAL_SINA_MEMBERSHIP",
        },
        "metrics": returns,
        "frequency_and_concentration": frequency,
        "artifacts": {"event_results": event_artifact},
        "forbidden_scope": {
            "final_oos_read": False,
            "parameter_tuning": False,
            "production_rule_modified": False,
            "promotion": False,
            "full_legacy_output_validation": "BLOCKED_HISTORICAL_SINA_MEMBERSHIP",
        },
    }
    payload["content_sha256"] = replay.sha256_json({
        "source_content_sha256": source["content_sha256"],
        "core_projection_stream_sha256": core_summary["projection_stream_sha256"],
        "event_results_sha256": event_artifact["sha256"],
        "metrics": returns,
        "frequency_and_concentration": frequency,
    })
    payload["manifest_sha256"] = replay.sha256_json(payload)
    manifest_path = output_dir / "development_historical_returns_manifest.json"
    _write_json(manifest_path, payload)
    payload["manifest_file"] = {
        "path": manifest_path.as_posix(),
        "bytes": manifest_path.stat().st_size,
        "sha256": _file_sha256(manifest_path),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--core-output", type=Path, required=True)
    parser.add_argument("--core-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        raw_dir=args.raw_dir,
        checkpoint_path=args.checkpoint,
        core_output=args.core_output,
        core_manifest_path=args.core_manifest,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "status": result["status"],
        "manifest_path": result["manifest_file"]["path"],
        "manifest_sha256": result["manifest_sha256"],
        "content_sha256": result["content_sha256"],
        "qualified_signal_count": result["scope"]["qualified_signal_count"],
        "event_results": result["artifacts"]["event_results"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
