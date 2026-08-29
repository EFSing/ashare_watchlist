"""Validate corporate-action-adjusted DEVELOPMENT forward outcomes.

V1 is an immutable raw-unadjusted diagnostic.  V2 reuses the frozen CORE
projection and frozen corporate-action dump, and adjusts only the ex-post
outcome path.  No future value is available to signal evaluation.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
from typing import Any

import numpy as np

import core_signal_replay as replay
import validate_development_returns as v1


SCHEMA_VERSION = "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_V2"
VALIDATION_LAYER = "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION"
PRICE_SEMANTICS = "CORPORATE_ACTION_ADJUSTED_OUTCOME_PATH_AFFINE_V1"
WITNESS_LIMIT = 10


def _event_payload(event: tuple[int, float, float, float, float]) -> dict[str, Any]:
    ex_date_ms, dividend, bonus, allotment, allotment_price = event
    return {
        "ex_date": replay._date_from_ms(ex_date_ms),
        "dividend_per_share": dividend,
        "per_share_bonus": bonus,
        "allotment_ratio": allotment,
        "allotment_price": allotment_price,
    }


def _crossing_events(
    events: list[tuple[int, float, float, float, float]],
    entry_ms: int,
    target_ms: int,
) -> list[tuple[int, float, float, float, float]]:
    """Events that can change comparability after the T+1 entry open."""

    return [event for event in events if entry_ms < event[0] <= target_ms]


def _adjust_outcome_path(
    *,
    dates_ms: np.ndarray,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    events: list[tuple[int, float, float, float, float]],
    target_ms: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Put a raw entry-to-target OHLC path on the target-date affine basis.

    The strict ``dates_ms < ex_date`` mask is important: an entry open on the
    ex-date is already an ex-date price and must not be transformed again.
    """

    adjusted = [np.array(values, dtype=float, copy=True) for values in (opens, highs, lows, closes)]
    for ex_date_ms, dividend, bonus, allotment, allotment_price in events:
        if ex_date_ms > target_ms:
            break
        mask = dates_ms < ex_date_ms
        if not np.any(mask):
            continue
        denominator = 1.0 + bonus + allotment
        if denominator <= 0 or not np.isfinite(denominator):
            raise RuntimeError("invalid corporate-action denominator in outcome path")
        for values in adjusted:
            values[mask] = (values[mask] - dividend + allotment_price * allotment) / denominator
    return adjusted[0], adjusted[1], adjusted[2], adjusted[3]


def _stock_path(
    *,
    store: dict[str, Any],
    symbol: str,
    expected_dates_ms: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    bounds = store["bounds"].get(symbol)
    if bounds is None:
        return None
    start, end = bounds
    dates = store["date_ms"][start:end]
    left = int(np.searchsorted(dates, int(expected_dates_ms[0]), side="left"))
    right = int(np.searchsorted(dates, int(expected_dates_ms[-1]), side="right"))
    if not np.array_equal(dates[left:right], expected_dates_ms):
        return None
    absolute_left, absolute_right = start + left, start + right
    return (
        store["date_ms"][absolute_left:absolute_right],
        store["open"][absolute_left:absolute_right],
        store["high"][absolute_left:absolute_right],
        store["low"][absolute_left:absolute_right],
        store["close"][absolute_left:absolute_right],
    )


def _unavailable_outcome(status: str, target_date: str | None, horizon: int, observed: int = 0) -> dict[str, Any]:
    return {
        "status": status,
        "target_date": target_date,
        "return_pct": None,
        "mfe_pct": None,
        "mae_pct": None,
        "expected_session_count": horizon,
        "observed_session_count": observed,
        "corporate_action_crossing": False,
        "corporate_action_count": 0,
        "corporate_actions": [],
    }


def _build_event_record(
    *,
    row: dict[str, Any],
    store: dict[str, Any],
    events: dict[str, list[tuple[int, float, float, float, float]]],
    session_dates: list[str],
    session_ms: np.ndarray,
    session_index: dict[str, int],
) -> dict[str, Any]:
    signal_date = row["signal_date"]
    symbol = row["symbol"]
    signal_position = session_index[signal_date]
    execution_position = signal_position + 1
    entry_date = session_dates[execution_position] if execution_position < len(session_dates) else row["earliest_execution_date"]
    if row["earliest_execution_date"] != entry_date:
        raise RuntimeError(f"T+1 timing mismatch for {symbol} at {signal_date}")

    bounds = store["bounds"].get(symbol)
    entry_available = False
    if bounds is not None and execution_position < len(session_ms):
        start, end = bounds
        symbol_dates = store["date_ms"][start:end]
        entry_index = int(np.searchsorted(symbol_dates, int(session_ms[execution_position]), side="left"))
        entry_available = entry_index < len(symbol_dates) and int(symbol_dates[entry_index]) == int(session_ms[execution_position])

    outcomes: dict[str, dict[str, Any]] = {}
    for horizon in v1.HORIZONS:
        key = f"{horizon}D"
        target_position = signal_position + horizon
        if not entry_available:
            status = "SYMBOL_NOT_IN_RAW_STORE" if bounds is None else "NO_T_PLUS_1_OPEN"
            outcomes[key] = _unavailable_outcome(status, None, horizon)
            continue
        if target_position >= len(session_dates):
            outcomes[key] = _unavailable_outcome("INSUFFICIENT_FORWARD_COVERAGE", None, horizon)
            continue
        expected_dates_ms = session_ms[execution_position : target_position + 1]
        path = _stock_path(store=store, symbol=symbol, expected_dates_ms=expected_dates_ms)
        if path is None:
            bounds = store["bounds"].get(symbol)
            if bounds is None:
                outcomes[key] = _unavailable_outcome("SYMBOL_NOT_IN_RAW_STORE", session_dates[target_position], horizon)
                continue
            start, end = bounds
            dates = store["date_ms"][start:end]
            observed = int(
                np.searchsorted(dates, int(expected_dates_ms[-1]), side="right")
                - np.searchsorted(dates, int(expected_dates_ms[0]), side="left")
            )
            outcomes[key] = _unavailable_outcome("INCOMPLETE_STOCK_WINDOW", session_dates[target_position], horizon, observed)
            continue

        dates_ms, opens, highs, lows, closes = path
        symbol_events = events.get(symbol, [])
        adjusted_open, adjusted_high, adjusted_low, adjusted_close = _adjust_outcome_path(
            dates_ms=dates_ms,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            events=symbol_events,
            target_ms=int(expected_dates_ms[-1]),
        )
        crossing = _crossing_events(symbol_events, int(expected_dates_ms[0]), int(expected_dates_ms[-1]))
        entry_open = float(adjusted_open[0])
        target_close = float(adjusted_close[-1])
        outcomes[key] = {
            "status": "AVAILABLE",
            "target_date": session_dates[target_position],
            "entry_open_adjusted": entry_open,
            "target_close_adjusted": target_close,
            "return_pct": (target_close / entry_open - 1.0) * 100.0,
            "mfe_pct": (float(np.max(adjusted_high)) / entry_open - 1.0) * 100.0,
            "mae_pct": (float(np.min(adjusted_low)) / entry_open - 1.0) * 100.0,
            "expected_session_count": horizon,
            "observed_session_count": horizon,
            "corporate_action_crossing": bool(crossing),
            "corporate_action_count": len(crossing),
            "corporate_actions": [_event_payload(event) for event in crossing],
        }
    return {
        "as_of_date": row["as_of_date"],
        "signal_date": signal_date,
        "earliest_execution_date": row["earliest_execution_date"],
        "symbol": symbol,
        "setup_id": row["setup_id"],
        "entry_date": entry_date,
        "outcomes": outcomes,
    }


def _load_v1_records(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return [json.loads(line) for line in handle]


def _record_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return record["symbol"], record["signal_date"], record["setup_id"]


def _metric_delta(raw: dict[str, Any], adjusted: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "positive_rate",
        "mean_return_pct",
        "expectancy_pct",
        "mean_mfe_pct",
        "median_mfe_pct",
        "mean_mae_pct",
        "median_mae_pct",
    )
    return {
        field: (adjusted[field] - raw[field] if raw[field] is not None and adjusted[field] is not None else None)
        for field in fields
    }


def _difference_audit(v1_records: list[dict[str, Any]], v2_records: list[dict[str, Any]]) -> dict[str, Any]:
    raw_by_key = {_record_key(record): record for record in v1_records}
    adjusted_by_key = {_record_key(record): record for record in v2_records}
    if len(raw_by_key) != len(v1_records) or raw_by_key.keys() != adjusted_by_key.keys():
        raise RuntimeError("V1/V2 event identity mismatch")

    by_horizon: dict[str, Any] = {}
    for horizon in v1.HORIZONS:
        horizon_key = f"{horizon}D"
        raw_available: list[dict[str, Any]] = []
        adjusted_available: list[dict[str, Any]] = []
        witnesses: list[dict[str, Any]] = []
        crossing_count = 0
        for key in sorted(raw_by_key):
            raw_record, adjusted_record = raw_by_key[key], adjusted_by_key[key]
            raw_outcome = raw_record["outcomes"][horizon_key]
            adjusted_outcome = adjusted_record["outcomes"][horizon_key]
            if raw_outcome["status"] != adjusted_outcome["status"]:
                raise RuntimeError(f"V1/V2 availability mismatch: {key} {horizon_key}")
            if adjusted_outcome["status"] != "AVAILABLE":
                continue
            raw_available.append(raw_outcome)
            adjusted_available.append(adjusted_outcome)
            if adjusted_outcome["corporate_action_crossing"]:
                crossing_count += 1
                metric_deltas = {
                    name: adjusted_outcome[name] - raw_outcome[name]
                    for name in ("return_pct", "mfe_pct", "mae_pct")
                }
                witnesses.append({
                    "symbol": adjusted_record["symbol"],
                    "signal_date": adjusted_record["signal_date"],
                    "entry_date": adjusted_record["entry_date"],
                    "target_date": adjusted_outcome["target_date"],
                    "horizon": horizon_key,
                    "corporate_actions": adjusted_outcome["corporate_actions"],
                    "raw": {name: raw_outcome[name] for name in ("return_pct", "mfe_pct", "mae_pct")},
                    "adjusted": {name: adjusted_outcome[name] for name in ("return_pct", "mfe_pct", "mae_pct")},
                    "delta": metric_deltas,
                })
        raw_metrics = v1._metric_summary(raw_available)
        adjusted_metrics = v1._metric_summary(adjusted_available)
        witnesses.sort(
            key=lambda item: (-max(abs(value) for value in item["delta"].values()), item["symbol"], item["signal_date"])
        )
        available_count = len(adjusted_available)
        by_horizon[horizon_key] = {
            "available_sample_count": available_count,
            "corporate_action_crossing_sample_count": crossing_count,
            "corporate_action_crossing_sample_share": crossing_count / available_count if available_count else None,
            "raw_v1": raw_metrics,
            "adjusted_v2": adjusted_metrics,
            "adjusted_minus_raw_delta": _metric_delta(raw_metrics, adjusted_metrics),
            "largest_difference_witnesses": witnesses[:WITNESS_LIMIT],
        }
    return {
        "schema_version": "DEVELOPMENT_HISTORICAL_RETURNS_V1_V2_DIFFERENCE_AUDIT_V1",
        "comparison": "V1_RAW_UNADJUSTED_DIAGNOSTIC_VS_V2_CORPORATE_ACTION_ADJUSTED_PRIMARY",
        "event_identity_count": len(v2_records),
        "by_horizon": by_horizon,
    }


def run(
    *,
    raw_dir: Path,
    checkpoint_path: Path,
    core_output: Path,
    core_manifest_path: Path,
    v1_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    root, _part_a, _part_b, source, core_summary = v1._verify_frozen_inputs(
        raw_dir=raw_dir,
        checkpoint_path=checkpoint_path,
        core_output=core_output,
        core_manifest_path=core_manifest_path,
    )
    v1_manifest = v1._load_json(v1_manifest_path)
    if v1_manifest.get("schema_version") != "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_V1":
        raise RuntimeError("historical raw diagnostic is not V1")
    v1_manifest_hash = v1_manifest.get("manifest_sha256")
    v1_payload = dict(v1_manifest)
    v1_payload.pop("manifest_sha256", None)
    if replay.sha256_json(v1_payload) != v1_manifest_hash:
        raise RuntimeError("V1 manifest hash mismatch")
    v1_event_path = v1_manifest_path.parents[4] / Path(v1_manifest["artifacts"]["event_results"]["path"])
    if v1._file_sha256(v1_event_path) != v1_manifest["artifacts"]["event_results"]["sha256"]:
        raise RuntimeError("V1 event artifact hash mismatch")

    index_dates, _, index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.array([index_dates[date_text] for date_text in session_dates], dtype=np.int64)
    session_index = {date_text: index for index, date_text in enumerate(session_dates)}
    store, stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")

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
            a_match_counts[signal_date] += int(set(replay.A_CONDITIONS).issubset(row["matched_conditions"]))
            if row["status"] != replay.QUALIFIED_LEGACY_BASELINE:
                continue
            qualified_counts[signal_date] += 1
            qualified_by_symbol[row["symbol"]] += 1
            event_records.append(_build_event_record(
                row=row,
                store=store,
                events=events,
                session_dates=session_dates,
                session_ms=session_ms,
                session_index=session_index,
            ))

    if len(candidate_counts) != root["signal_date_count"] or sum(candidate_counts.values()) != core_summary["total_candidate_evaluations"]:
        raise RuntimeError("core stream coverage changed during V2 outcome validation")
    if sum(qualified_counts.values()) != len(event_records):
        raise RuntimeError("qualified event accounting mismatch")

    output_dir.mkdir(parents=True, exist_ok=True)
    event_path = output_dir / "development_historical_returns_v2.jsonl.gz"
    event_artifact = v1._write_event_results(event_path, event_records)
    returns = v1._returns_summary(event_records)
    frequency = v1._frequency_summary(
        candidate_counts=candidate_counts,
        a_match_counts=a_match_counts,
        qualified_counts=qualified_counts,
        qualified_by_symbol=qualified_by_symbol,
    )
    v1_records = _load_v1_records(v1_event_path)
    audit = _difference_audit(v1_records, event_records)
    audit["v1_manifest_sha256"] = v1_manifest_hash
    audit["v1_event_results_sha256"] = v1_manifest["artifacts"]["event_results"]["sha256"]
    audit["v2_event_results_sha256"] = event_artifact["sha256"]
    audit["audit_sha256"] = replay.sha256_json(audit)
    audit_path = output_dir / "development_historical_returns_v1_v2_audit.json"
    v1._write_json(audit_path, audit)
    audit_artifact = {
        "path": audit_path.as_posix(),
        "bytes": audit_path.stat().st_size,
        "sha256": v1._file_sha256(audit_path),
        "audit_sha256": audit["audit_sha256"],
    }

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "validation_layer": VALIDATION_LAYER,
        "data_partition": "development",
        "status": v1.VALIDATION_STATUS,
        "retrospective_status": v1.RETROSPECTIVE_STATUS,
        "dataset_version": replay.CONTINUOUS_DATASET_VERSION,
        "result_role": "PRIMARY_DEVELOPMENT_OUTCOME_MEASUREMENT",
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
            "entry": "T+1 XSHG session open",
            "return_horizons": [f"{horizon}D" for horizon in v1.HORIZONS],
            "mfe_mae": "adjusted maximum high and minimum low from T+1 through each horizon, relative to adjusted T+1 open",
            "price_semantics": PRICE_SEMANTICS,
            "affine_formula": "(price - dividend_per_share + allotment_price*allotment_ratio)/(1 + per_share_bonus + allotment_ratio)",
            "event_filter": "entry_date < ex_date <= target_date; ex_date == entry_date is not applied to entry open",
            "event_order": "ascending ex_date",
            "future_information_boundary": "future corporate actions are used only for ex-post outcome measurement and never fed into signal evaluation",
            "positive_rate": "return_pct > 0",
            "expectancy": "positive_rate*mean_positive_return_pct + non_positive_rate*mean_non_positive_return_pct",
        },
        "provenance": {
            "raw_inputs": source,
            "adjustment_events": event_meta,
            "core_checkpoint": {
                "path": checkpoint_path.as_posix(),
                "bytes": checkpoint_path.stat().st_size,
                "sha256": v1._file_sha256(checkpoint_path),
                "checkpoint_sha256": root["checkpoint_sha256"],
                "source_content_sha256": root["source_content_sha256"],
            },
            "core_output": {
                "path": core_output.as_posix(),
                "bytes": core_output.stat().st_size,
                "sha256": v1._file_sha256(core_output),
                "projection_stream_sha256": core_summary["projection_stream_sha256"],
                "rows": core_summary["total_candidate_evaluations"],
                "replayed_for_v2": False,
            },
            "core_manifest": {
                "path": core_manifest_path.as_posix(),
                "bytes": core_manifest_path.stat().st_size,
                "sha256": v1._file_sha256(core_manifest_path),
            },
            "v1_raw_diagnostic": {
                "preserved": True,
                "role": "HISTORICAL_RAW_UNADJUSTED_DIAGNOSTIC_NOT_CORRECTNESS_PRIMARY",
                "manifest_path": v1_manifest_path.as_posix(),
                "manifest_file_sha256": v1._file_sha256(v1_manifest_path),
                "manifest_sha256": v1_manifest_hash,
                "event_results_path": v1_event_path.as_posix(),
                "event_results_sha256": v1_manifest["artifacts"]["event_results"]["sha256"],
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
        "difference_audit": audit["by_horizon"],
        "artifacts": {"event_results": event_artifact, "v1_v2_difference_audit": audit_artifact},
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
        "v1_event_results_sha256": v1_manifest["artifacts"]["event_results"]["sha256"],
        "v2_event_results_sha256": event_artifact["sha256"],
        "difference_audit_sha256": audit["audit_sha256"],
        "metrics": returns,
        "frequency_and_concentration": frequency,
    })
    payload["manifest_sha256"] = replay.sha256_json(payload)
    manifest_path = output_dir / "development_historical_returns_v2_manifest.json"
    v1._write_json(manifest_path, payload)
    payload["manifest_file"] = {
        "path": manifest_path.as_posix(),
        "bytes": manifest_path.stat().st_size,
        "sha256": v1._file_sha256(manifest_path),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--core-output", type=Path, required=True)
    parser.add_argument("--core-manifest", type=Path, required=True)
    parser.add_argument("--v1-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        raw_dir=args.raw_dir,
        checkpoint_path=args.checkpoint,
        core_output=args.core_output,
        core_manifest_path=args.core_manifest,
        v1_manifest_path=args.v1_manifest,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "status": result["status"],
        "manifest_path": result["manifest_file"]["path"],
        "manifest_sha256": result["manifest_sha256"],
        "content_sha256": result["content_sha256"],
        "qualified_signal_count": result["scope"]["qualified_signal_count"],
        "event_results": result["artifacts"]["event_results"],
        "difference_audit": result["artifacts"]["v1_v2_difference_audit"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
