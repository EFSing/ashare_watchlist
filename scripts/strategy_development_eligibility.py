"""Run the one pre-registered development eligibility evaluation for B.

The evaluation consumes the existing frozen CORE DEVELOPMENT input package,
reuses its T-close/T+1 construction and corporate-action-adjusted outcome
contract, and writes only candidate-bound research artifacts.  It has no
parameter, threshold, TOP-N, promotion, or Final OOS mode.
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
import validate_development_returns as returns_v1
import validate_development_returns_v2 as returns_v2
from b_breakout_retest import (
    STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION,
    evaluate_numeric_projection,
    evaluate_universe,
)
from generation_contract import IndexManifest, POINT_IN_TIME


SCHEMA_VERSION = "STRATEGY_DEVELOPMENT_ELIGIBILITY_V1"
VALIDATION_LAYER = "STRATEGY_DEVELOPMENT_ELIGIBILITY"
B_MATCH_CONDITIONS = {
    "BREAKOUT_CLOSE_ABOVE_60D_HIGH",
    "BREAKOUT_VOLUME_GE_1_8_PREV_20_MEAN",
    "BREAKOUT_CHG1_GE_3_PCT",
    "PULLBACK_CLOSE_GE_97_PCT_BASE",
    "PULLBACK_WITHIN_PLATFORM_4_PCT",
    "PULLBACK_VOLUME_LT_70_PCT_BREAKOUT",
    "PULLBACK_TURNED_STRONG",
}
ELIGIBILITY_THRESHOLDS = {
    "minimum_total_event_count": 30,
    "minimum_available_events_per_horizon": 30,
    "primary_horizon": "10D",
    "primary_positive_rate_min": 0.50,
    "primary_mean_return_min_exclusive": 0.0,
    "primary_median_return_min_exclusive": 0.0,
    "minimum_robust_year_count": 3,
    "minimum_events_per_robust_year": 10,
    "minimum_positive_mean_year_count": 2,
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_events(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            for record in records:
                compressed.write((replay.canonical_json(record) + "\n").encode("utf-8"))
    return {"path": path.as_posix(), "bytes": path.stat().st_size, "rows": len(records), "sha256": returns_v1._file_sha256(path)}


def _projection(result: Any) -> dict[str, Any]:
    level_plan = None if result.level_plan is None else result.level_plan.to_dict()
    return {
        "as_of_date": result.as_of_date,
        "signal_date": result.signal_date,
        "earliest_execution_date": result.earliest_execution_date,
        "symbol": result.symbol,
        "setup_id": result.setup_id,
        "status": result.status,
        "matched_conditions": list(result.matched_conditions),
        "failed_conditions": list(result.failed_conditions),
        "reject_reasons": list(result.reject_reasons),
        "support": result.support,
        "trigger": result.trigger,
        "stop": result.stop,
        "target": result.target,
        "target_type": result.target_type,
        "risk": result.risk,
        "rr": result.rr,
        "level_plan": level_plan,
    }


def _frozen_timing(core_output: Path) -> dict[str, str]:
    timing: dict[str, str] = {}
    with gzip.open(core_output, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            row = json.loads(line)
            signal_date = row["signal_date"]
            earliest = row["earliest_execution_date"]
            previous = timing.setdefault(signal_date, earliest)
            if previous != earliest:
                raise RuntimeError(f"frozen core timing identity changed at {signal_date}")
    if len(timing) != 769:
        raise RuntimeError(f"frozen core timing coverage changed: {len(timing)}")
    return timing


def _next_execution_date(
    signal_date: str,
    session_dates: list[str],
    session_index: dict[str, int],
    frozen_timing: dict[str, str],
) -> str:
    position = session_index[signal_date]
    if position + 1 >= len(session_dates):
        return frozen_timing[signal_date]
    execution_date = session_dates[position + 1]
    if frozen_timing.get(signal_date) != execution_date:
        raise RuntimeError(f"frozen T+1 timing mismatch at {signal_date}")
    return execution_date


def _add_median_returns(metrics: dict[str, Any], event_records: list[dict[str, Any]]) -> None:
    for horizon in returns_v1.HORIZONS:
        key = f"{horizon}D"
        values = [
            float(record["outcomes"][key]["return_pct"])
            for record in event_records
            if record["outcomes"][key]["status"] == "AVAILABLE"
        ]
        metrics[key]["median_return_pct"] = float(np.median(values)) if values else None


def _year_robustness(metrics: dict[str, Any]) -> dict[str, Any]:
    horizon = ELIGIBILITY_THRESHOLDS["primary_horizon"]
    by_year = metrics[horizon]["by_year"]
    return {
        "horizon": horizon,
        "years": {
            year: {
                "available_event_count": values["sample_count"],
                "positive_rate": values["positive_rate"],
                "mean_return_pct": values["mean_return_pct"],
                "median_return_pct": values.get("median_return_pct"),
            }
            for year, values in by_year.items()
        },
    }


def _fixed_decision(metrics: dict[str, Any], frequency: dict[str, Any], parity: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    primary = metrics[ELIGIBILITY_THRESHOLDS["primary_horizon"]]
    available_by_horizon = {
        key: values["sample_count"]
        for key, values in metrics.items()
    }
    robust_years = [
        values
        for values in _year_robustness(metrics)["years"].values()
        if values["available_event_count"] >= ELIGIBILITY_THRESHOLDS["minimum_events_per_robust_year"]
    ]
    positive_mean_years = [
        values for values in robust_years
        if values["mean_return_pct"] is not None and values["mean_return_pct"] > 0
    ]
    gates = {
        "manifest_parity": bool(parity["all_passed"]),
        "event_count_minimum": frequency["qualified_signal_event_count"] >= ELIGIBILITY_THRESHOLDS["minimum_total_event_count"],
        "available_events_per_horizon": all(
            count >= ELIGIBILITY_THRESHOLDS["minimum_available_events_per_horizon"]
            for count in available_by_horizon.values()
        ),
        "primary_positive_rate": primary["positive_rate"] is not None and primary["positive_rate"] >= ELIGIBILITY_THRESHOLDS["primary_positive_rate_min"],
        "primary_mean_return": primary["mean_return_pct"] is not None and primary["mean_return_pct"] > ELIGIBILITY_THRESHOLDS["primary_mean_return_min_exclusive"],
        "primary_median_return": primary["median_return_pct"] is not None and primary["median_return_pct"] > ELIGIBILITY_THRESHOLDS["primary_median_return_min_exclusive"],
        "year_count": len(robust_years) >= ELIGIBILITY_THRESHOLDS["minimum_robust_year_count"],
        "positive_mean_year_count": len(positive_mean_years) >= ELIGIBILITY_THRESHOLDS["minimum_positive_mean_year_count"],
    }
    decision = (
        "CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES"
        if all(gates.values())
        else "CANDIDATE_REJECTED"
    )
    return decision, {
        "decision": decision,
        "gates": gates,
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "available_events_by_horizon": available_by_horizon,
        "robust_year_count": len(robust_years),
        "positive_mean_year_count": len(positive_mean_years),
    }


def run(
    *,
    raw_dir: Path,
    checkpoint_path: Path,
    core_output: Path,
    core_manifest_path: Path,
    output_dir: Path,
    parity_symbols_per_date: int = 2,
) -> dict[str, Any]:
    if parity_symbols_per_date < 1:
        raise ValueError("parity_symbols_per_date must be positive")
    root, _part_a, _part_b, source, core_summary = returns_v1._verify_frozen_inputs(
        raw_dir=raw_dir,
        checkpoint_path=checkpoint_path,
        core_output=core_output,
        core_manifest_path=core_manifest_path,
    )
    frozen_timing = _frozen_timing(core_output)
    index_dates, index_bars, index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.array([index_dates[value] for value in session_dates], dtype=np.int64)
    session_index = {value: index for index, value in enumerate(session_dates)}
    signal_dates = [
        value for value in session_dates
        if replay.VALIDATION_START <= value <= replay.VALIDATION_END
    ]
    if len(signal_dates) != 769:
        raise RuntimeError(f"frozen continuous signal-date count changed: {len(signal_dates)}")
    store, stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")

    candidate_counts: Counter[str] = Counter()
    b_match_counts: Counter[str] = Counter()
    qualified_counts: Counter[str] = Counter()
    qualified_by_symbol: Counter[str] = Counter()
    event_records: list[dict[str, Any]] = []
    parity_checks: list[dict[str, Any]] = []

    for signal_date in signal_dates:
        anchor_ms = index_dates[signal_date]
        index_position = int(np.searchsorted(session_ms, anchor_ms, side="right"))
        t_index_bars = index_bars[:index_position]
        if len(t_index_bars) < 6 or t_index_bars[-1]["date"] != signal_date:
            raise RuntimeError(f"benchmark coverage/timing failure at {signal_date}")
        eligible_symbols, numeric_bars = replay._numeric_bars_for_date(
            store, signal_date, anchor_ms, events
        )
        if not eligible_symbols:
            raise RuntimeError(f"no eligible symbols at {signal_date}")
        earliest_execution_date = _next_execution_date(
            signal_date, session_dates, session_index, frozen_timing
        )
        projections: dict[str, dict[str, Any]] = {}
        for symbol in eligible_symbols:
            projection = evaluate_numeric_projection(
                symbol=symbol,
                signal_date=signal_date,
                earliest_execution_date=earliest_execution_date,
                bars=numeric_bars[symbol],
                index_bars=t_index_bars,
            )
            projections[symbol] = projection
            candidate_counts[signal_date] += 1
            if B_MATCH_CONDITIONS.issubset(projection["matched_conditions"]):
                b_match_counts[signal_date] += 1
            if projection["status"] == "QUALIFIED_LEGACY_BASELINE":
                qualified_counts[signal_date] += 1
                qualified_by_symbol[symbol] += 1
                event_records.append(returns_v2._build_event_record(
                    row=projection,
                    store=store,
                    events=events,
                    session_dates=session_dates,
                    session_ms=session_ms,
                    session_index=session_index,
                ))

        parity_sample = eligible_symbols[:parity_symbols_per_date]
        sample_bars: dict[str, list[dict[str, Any]]] = {}
        for symbol in parity_sample:
            _symbols, one_symbol_bars = replay._bars_for_date(
                store, signal_date, anchor_ms, events, symbol_filter={symbol}
            )
            sample_bars.update(one_symbol_bars)
        index_manifest = IndexManifest(
            symbol=replay.BENCHMARK_SYMBOL,
            as_of_date=signal_date,
            retrieved_at_bjt=replay.REPLAY_RETRIEVED_AT_BJT,
            bars=t_index_bars,
            provider="HiThink Financial-API",
            adjustment_mode="INDEX_UNADJUSTED_AS_OF",
            source="HiThink historical benchmark index K",
            temporal_semantics=POINT_IN_TIME,
        )
        manifest = replay._manifest_for_chunk(
            signal_date,
            parity_sample,
            sample_bars,
            index_manifest,
            source["content_sha256"],
        )
        manifest_results = {result.symbol: _projection(result) for result in evaluate_universe(manifest)}
        for symbol in parity_sample:
            numeric = projections[symbol]
            manifest_projection = manifest_results[symbol]
            parity_checks.append({
                "signal_date": signal_date,
                "symbol": symbol,
                "input_fingerprint": manifest.input_fingerprint,
                "passed": numeric == manifest_projection,
                "numeric_projection": numeric,
                "manifest_projection": manifest_projection,
            })

    expected_counts = {key: value["evaluable_symbol_count"] for key, value in replay._coverage_by_date(store, signal_dates, index_dates).items()}
    if dict(candidate_counts) != expected_counts:
        raise RuntimeError("B eligibility candidate coverage does not match frozen raw T-day universe")
    if sum(qualified_counts.values()) != len(event_records):
        raise RuntimeError("B eligibility qualified event accounting mismatch")
    parity = {
        "sample_count": len(parity_checks),
        "expected_sample_count": len(signal_dates) * parity_symbols_per_date,
        "all_passed": bool(parity_checks) and all(item["passed"] for item in parity_checks),
        "checks_sha256": replay.sha256_json(parity_checks),
    }
    metrics = returns_v1._returns_summary(event_records)
    _add_median_returns(metrics, event_records)
    frequency = returns_v1._frequency_summary(
        candidate_counts=candidate_counts,
        a_match_counts=b_match_counts,
        qualified_counts=qualified_counts,
        qualified_by_symbol=qualified_by_symbol,
    )
    frequency["match_field"] = "B_BREAKOUT_RETEST_MATCH"
    year_robustness = _year_robustness(metrics)
    decision, decision_audit = _fixed_decision(metrics, frequency, parity)
    output_dir.mkdir(parents=True, exist_ok=True)
    event_artifact = _write_events(output_dir / "b_breakout_retest_eligibility_events.jsonl.gz", event_records)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "validation_layer": VALIDATION_LAYER,
        "data_partition": "development",
        "status": "COMPLETE",
        "retrospective_status": "RECONSTRUCTED_RETROSPECTIVE",
        "dataset_version": replay.CONTINUOUS_DATASET_VERSION,
        "candidate": {
            "version": STRATEGY_VERSION,
            "spec_sha256": STRATEGY_SPEC_SHA256,
            "setup_id": "B_BREAKOUT_RETEST",
            "v0_source_commit": "c8406c393c0b135eafb0aec763576ae869fddcff",
            "v0_source_file_sha256": "6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9",
        },
        "scope": {
            "signal_date_count": len(signal_dates),
            "signal_dates_start": signal_dates[0],
            "signal_dates_end": signal_dates[-1],
            "candidate_evaluation_count": sum(candidate_counts.values()),
            "qualified_signal_event_count": len(event_records),
            "entry": "T+1 XSHG session open",
            "return_horizons": [f"{horizon}D" for horizon in returns_v1.HORIZONS],
            "price_semantics": returns_v2.PRICE_SEMANTICS,
            "mfe_mae": "adjusted maximum high and minimum low from T+1 through each horizon, relative to adjusted T+1 open",
            "future_information_boundary": "future corporate actions used only for ex-post outcome measurement",
        },
        "fixed_protocol": {
            "name": SCHEMA_VERSION,
            "thresholds": ELIGIBILITY_THRESHOLDS,
            "parameter_tuning": False,
            "threshold_search": False,
            "top_n_optimization": False,
            "rule_changed_after_results": False,
        },
        "input_provenance": {
            "raw_inputs": source,
            "raw_data_range": stock_meta | {"benchmark_rows": index_meta["row_count"]},
            "adjustment_events": event_meta,
            "core_checkpoint": {
                "path": checkpoint_path.as_posix(),
                "bytes": checkpoint_path.stat().st_size,
                "sha256": returns_v1._file_sha256(checkpoint_path),
                "checkpoint_sha256": root["checkpoint_sha256"],
                "source_content_sha256": root["source_content_sha256"],
            },
            "core_output": {
                "path": core_output.as_posix(),
                "bytes": core_output.stat().st_size,
                "sha256": returns_v1._file_sha256(core_output),
                "projection_stream_sha256": core_summary["projection_stream_sha256"],
                "rows": core_summary["total_candidate_evaluations"],
            },
            "core_manifest": {
                "path": core_manifest_path.as_posix(),
                "bytes": core_manifest_path.stat().st_size,
                "sha256": returns_v1._file_sha256(core_manifest_path),
            },
            "generation_input_manifest_reused": True,
            "manifest_parity": parity,
            "timing_contract": {
                "signal_uses": "T close only",
                "execution": "T+1 XSHG open",
                "same_bar_execution": False,
                "future_bar_inputs": False,
            },
            "known_at_vintage_proof": False,
            "known_at_limitation": "retrospective dump has observation dates and acquisition hash, but no per-bar historical vintage timestamp",
        },
        "metrics": metrics,
        "signal_concentration": frequency,
        "year_robustness": year_robustness,
        "decision_audit": decision_audit,
        "decision": decision,
        "artifacts": {"event_results": event_artifact},
        "forbidden_scope": {
            "final_oos_read": False,
            "parameter_tuning": False,
            "threshold_search": False,
            "top_n_optimization": False,
            "production_rule_modified": False,
            "promotion": False,
            "full_legacy_output_validation": "BLOCKED_HISTORICAL_SINA_MEMBERSHIP",
        },
    }
    payload["content_sha256"] = replay.sha256_json({
        "candidate": payload["candidate"],
        "raw_source_content_sha256": source["content_sha256"],
        "core_projection_stream_sha256": core_summary["projection_stream_sha256"],
        "event_results_sha256": event_artifact["sha256"],
        "metrics": metrics,
        "signal_concentration": frequency,
        "decision": decision,
    })
    payload["manifest_sha256"] = replay.sha256_json(payload)
    manifest_path = output_dir / "strategy_development_eligibility_manifest.json"
    _write_json(manifest_path, payload)
    payload["manifest_file"] = {
        "path": manifest_path.as_posix(),
        "bytes": manifest_path.stat().st_size,
        "sha256": returns_v1._file_sha256(manifest_path),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--core-output", type=Path, required=True)
    parser.add_argument("--core-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--parity-symbols-per-date", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(run(
        raw_dir=args.raw_dir,
        checkpoint_path=args.checkpoint,
        core_output=args.core_output,
        core_manifest_path=args.core_manifest,
        output_dir=args.output_dir,
        parity_symbols_per_date=args.parity_symbols_per_date,
    ), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
