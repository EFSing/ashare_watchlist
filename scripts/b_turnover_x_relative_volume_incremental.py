"""Pre-outcome input and outcome diagnostic for turnover x relative volume.

The pre-outcome commands in this module build the exact corrected-B structural
cohort, acquire historical ``换手率`` with a resumable per-symbol checkpoint,
and audit coverage.  The outcome command is intentionally separate and refuses
to run unless a research-ready input manifest and a committed protocol SHA are
supplied.

This is DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DATE_ANCHORED /
NO_VINTAGE_PROOF / DIAGNOSTIC_ONLY work.  It never changes B qualification.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

import b_phase_volume_path_diagnostic as volume_path
import core_signal_replay as replay
from b_breakout_retest_v1_1 import (
    SETUP_ID,
    STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION,
    evaluate_numeric_projection,
)
from strategy_development_eligibility import (
    _frozen_timing,
    _next_execution_date,
    _verify_frozen_projection_identity,
    _verify_required_registry_hashes,
)
import validate_development_returns as returns_v1


SCHEMA_VERSION = "B_TURNOVER_X_RELATIVE_VOLUME_INCREMENTAL_DIAGNOSTIC_V1"
EVIDENCE_LABELS = (
    "DEVELOPMENT",
    "RECONSTRUCTED_RETROSPECTIVE",
    "DATE_ANCHORED",
    "NO_VINTAGE_PROOF",
    "DIAGNOSTIC_ONLY",
)
DECISIONS = (
    "TURNOVER_X_RELATIVE_VOLUME_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION",
    "TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE",
    "TURNOVER_X_RELATIVE_VOLUME_NO_CLEAR_INCREMENTAL_SIGNAL",
)
START_DATE = "2023-06-30"
END_DATE = "2026-08-28"
START_DATE_PROVIDER = "20230630"
END_DATE_PROVIDER = "20260828"
EXPECTED_EVALUATIONS = 4_041_140
EXPECTED_STRUCTURAL = 573_586
EXPECTED_QUALIFIED = 17_714
MIN_QUALIFIED_COVERAGE = 0.99
MIN_STRUCTURAL_COVERAGE = 0.98
MIN_STRATUM_COVERAGE = 0.95
TURNOVER_FIELD = "换手率"
DATE_FIELD = "日期"
PRIMARY_FEATURES = ("turnover_rate_pct", "relative_volume")
ROBUSTNESS_OUTCOMES = ("10D_return", "5D_mfe", "5D_mae", "10D_mfe", "10D_mae")
ALL_OUTCOME_FIELDS = ("5D_return", *ROBUSTNESS_OUTCOMES)
OUTCOME_ACCESS_STATUS = "SCHEMA_SAMPLE_OBSERVED_NOT_USED"
OUTCOME_ACCESS_NOTE = (
    "One pre-existing event record was inspected during intake only to identify the "
    "artifact schema; no outcome value was used in computation, filtering, or conclusion."
)
YEAR_GROUPS = ("2023", "2024", "2025", "2026")
BOARD_GROUPS = ("Main", "ChiNext", "STAR")
STAGE_LABELS = volume_path.STAGE_LABELS
SYMBOL_RE = re.compile(rb'\x22symbol\x22\s*:\s*\x22([^\x22]+)\x22')
DATE_RE = re.compile(rb'\x22signal_date\x22\s*:\s*\x22([^\x22]+)\x22')
SETUP_RE = re.compile(rb'\x22setup_id\x22\s*:\s*\x22([^\x22]+)\x22')


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _reject_forbidden(paths: Iterable[Path]) -> None:
    for path in paths:
        lowered = str(path).lower().replace("\\", "/")
        if "continuous_speed_probe" in lowered or "final_oos" in lowered:
            raise RuntimeError(f"forbidden path in turnover diagnostic: {path}")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _canonical_stream_sha256(rows: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update((_canonical_json(row) + "\n").encode("utf-8"))
    return digest.hexdigest()


def _relative_volume(volume: Sequence[float]) -> tuple[float | None, str | None]:
    """Return the frozen ``volume_T / mean(volume[T-20:T-1])`` feature."""

    if len(volume) < 21:
        return None, "INSUFFICIENT_PRIOR_BARS"
    numerator = float(volume[-1])
    denominator = float(np.mean(np.asarray(volume[-21:-1], dtype=float)))
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None, "NON_FINITE_NUMERATOR_OR_DENOMINATOR"
    if denominator <= 0:
        return None, "NON_POSITIVE_DENOMINATOR"
    value = numerator / denominator
    return (float(value), None) if math.isfinite(value) else (None, "NON_FINITE_RESULT")


def _symbol_code(symbol: str) -> str:
    return str(symbol).split(".", 1)[0].strip().zfill(6)


def _provider_symbol(symbol: str) -> str:
    return _symbol_code(symbol)


def _board_for_symbol(symbol: str) -> str:
    code = _symbol_code(symbol)
    if code.startswith(("00", "60")):
        return "Main"
    if code.startswith("30"):
        return "ChiNext"
    if code.startswith("68"):
        return "STAR"
    return "OUT_OF_SCOPE_PREFIX"


def _load_qualified_identity_without_outcomes(path: Path) -> set[tuple[str, str, str]]:
    """Extract only identity fields from the frozen B event stream.

    The event stream contains outcomes, but this pre-outcome extraction uses
    byte-level identity regexes and never parses or accesses the outcomes key.
    """

    result: set[tuple[str, str, str]] = set()
    with gzip.open(path, "rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            symbol = SYMBOL_RE.search(raw_line)
            signal_date = DATE_RE.search(raw_line)
            setup_id = SETUP_RE.search(raw_line)
            if not symbol or not signal_date or not setup_id:
                raise RuntimeError(f"missing frozen B identity fields at line {line_number}")
            result.add((symbol.group(1).decode(), signal_date.group(1).decode(), setup_id.group(1).decode()))
    return result


def _frozen_context(raw_dir: Path, checkpoint_path: Path, core_output: Path, core_manifest_path: Path, registry_path: Path) -> dict[str, Any]:
    if STRATEGY_SPEC_SHA256 != "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd":
        raise RuntimeError("corrected B strategy spec SHA changed")
    registry, registry_verification = _verify_required_registry_hashes(raw_dir=raw_dir, registry_path=registry_path)
    root, _part_a, _part_b, source, core_summary = returns_v1._verify_frozen_inputs(
        raw_dir=raw_dir,
        checkpoint_path=checkpoint_path,
        core_output=core_output,
        core_manifest_path=core_manifest_path,
    )
    frozen_identity = _verify_frozen_projection_identity(
        registry=registry,
        root=root,
        source=source,
        core_summary=core_summary,
        core_output=core_output,
        core_manifest_path=core_manifest_path,
    )
    if len(registry_verification) != 13:
        raise RuntimeError("required frozen artifact count changed")
    return {
        "registry": registry,
        "registry_verification": registry_verification,
        "frozen_identity": frozen_identity,
        "source": source,
        "core_summary": core_summary,
    }


def _cohort_record(
    *, symbol: str, signal_date: str, trace: Mapping[str, Any], projection: Mapping[str, Any],
) -> dict[str, Any]:
    record = {
        "symbol": symbol,
        "signal_date": signal_date,
        "year": signal_date[:4],
        "board": _board_for_symbol(symbol),
        "breakout_date": trace["breakout_date"],
        "pullback_stage": trace["pullback_stage"],
        "downstream_status": projection["status"],
        "final_b_qualified": projection["status"] == "QUALIFIED_LEGACY_BASELINE",
        "near_price_limit_proxy": volume_path._near_price_limit_proxy(symbol, trace["signal_day_return_pct"]),
    }
    for key in (
        "breakout_index", "base_hi", "price_structure_pass", "volume_pass", "turn_strength_pass",
        "breakout_volume_ratio", "b_existing_pull_volume_ratio", "pre_t_retest_volume_ratio",
        "reactivation_vs_retest_ratio", "reactivation_vs_breakout_ratio", "feature_unavailable",
        "signal_day_return_pct", "close_relative_previous", "close_vs_ma5",
        "close_position_in_day_range", "distance_from_base_hi_pct", "pos250",
    ):
        record[key] = trace[key]
    return record


def build_cohort(
    *, raw_dir: Path, checkpoint_path: Path, core_output: Path, core_manifest_path: Path,
    qualified_events_path: Path, registry_path: Path, output_dir: Path,
) -> dict[str, Any]:
    """Build the 573,586-row structural cohort without reading outcomes."""

    _reject_forbidden((raw_dir, checkpoint_path, core_output, core_manifest_path, qualified_events_path, registry_path, output_dir))
    context = _frozen_context(raw_dir, checkpoint_path, core_output, core_manifest_path, registry_path)
    qualified_identity = _load_qualified_identity_without_outcomes(qualified_events_path)
    if len(qualified_identity) != EXPECTED_QUALIFIED:
        raise RuntimeError(f"qualified identity count changed: {len(qualified_identity)}")

    index_dates, index_bars, _index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.asarray([index_dates[value] for value in session_dates], dtype=np.int64)
    session_index = {value: index for index, value in enumerate(session_dates)}
    signal_dates = [value for value in session_dates if replay.VALIDATION_START <= value <= replay.VALIDATION_END]
    if len(signal_dates) != 769:
        raise RuntimeError(f"frozen signal-date count changed: {len(signal_dates)}")
    store, stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")
    frozen_timing = _frozen_timing(core_output)
    signal_ms_set = {index_dates[value] for value in signal_dates}

    output_dir.mkdir(parents=True, exist_ok=True)
    cohort_path = output_dir / "cohort_features.jsonl.gz"
    content_digest = hashlib.sha256()
    total_evaluations = 0
    records = 0
    generated_qualified: set[tuple[str, str, str]] = set()
    stage_counts: Counter[str] = Counter()
    structural_years: Counter[str] = Counter()
    qualified_years: Counter[str] = Counter()
    symbols: set[str] = set()
    with cohort_path.open("wb") as raw_handle:
        with gzip.GzipFile(fileobj=raw_handle, mode="wb", filename="", mtime=0) as compressed:
            for symbol_number, symbol in enumerate(sorted(store["bounds"]), start=1):
                group_start, group_end = store["bounds"][symbol]
                raw_dates = store["date_ms"][group_start:group_end]
                t_indices = [
                    index for index, date_ms in enumerate(raw_dates)
                    if index >= replay.MINIMUM_BARS - 1 and int(date_ms) in signal_ms_set
                ]
                total_evaluations += len(t_indices)
                symbol_events = events.get(symbol, [])
                by_event_count: dict[int, list[int]] = defaultdict(list)
                event_dates = np.asarray([item[0] for item in symbol_events], dtype=np.int64)
                for t_index in t_indices:
                    event_count = int(np.searchsorted(event_dates, int(raw_dates[t_index]), side="right")) if len(event_dates) else 0
                    by_event_count[event_count].append(t_index)
                for event_count, state_t_indices in sorted(by_event_count.items()):
                    dates_ms, adjusted_close, volume, adjusted_high, adjusted_low = volume_path._adjusted_symbol_arrays(
                        store, symbol, symbol_events, event_count,
                    )
                    breakout_mask = volume_path._breakout_mask(adjusted_close, volume)
                    for t_index in state_t_indices:
                        lower = max(61, t_index - 14)
                        relative = np.flatnonzero(breakout_mask[lower:t_index])
                        if not len(relative):
                            continue
                        start = max(0, t_index + 1 - replay.LOOKBACK_BARS)
                        close = adjusted_close[start:t_index + 1]
                        local_volume = volume[start:t_index + 1]
                        high = adjusted_high[start:t_index + 1]
                        low = adjusted_low[start:t_index + 1]
                        dates = [replay._date_from_ms(int(value)) for value in dates_ms[start:t_index + 1]]
                        trace = volume_path._first_breakout_trace(close, local_volume, high, low, dates)
                        if trace is None:
                            raise RuntimeError(f"first-breakout trace failed for {symbol} {dates[-1]}")
                        signal_date = dates[-1]
                        anchor_ms = int(dates_ms[t_index])
                        index_position = int(np.searchsorted(session_ms, anchor_ms, side="right"))
                        projection = evaluate_numeric_projection(
                            symbol=symbol,
                            signal_date=signal_date,
                            earliest_execution_date=_next_execution_date(signal_date, session_dates, session_index, frozen_timing),
                            bars=(close, local_volume, high, low),
                            index_bars=index_bars[:index_position],
                        )
                        record = _cohort_record(symbol=symbol, signal_date=signal_date, trace=trace, projection=projection)
                        record["relative_volume"], rv_reason = _relative_volume(local_volume)
                        if rv_reason:
                            record["relative_volume_unavailable_reason"] = rv_reason
                        line = (_canonical_json(record) + "\n").encode("utf-8")
                        content_digest.update(line)
                        compressed.write(line)
                        records += 1
                        symbols.add(symbol)
                        stage_counts[record["pullback_stage"]] += 1
                        structural_years[record["year"]] += 1
                        if record["final_b_qualified"]:
                            identity = (symbol, signal_date, SETUP_ID)
                            generated_qualified.add(identity)
                            qualified_years[record["year"]] += 1
                if symbol_number % 500 == 0:
                    print(f"cohort symbols={symbol_number} evaluations={total_evaluations} structural={records}", flush=True)

    if total_evaluations != EXPECTED_EVALUATIONS:
        raise RuntimeError(f"frozen evaluation count changed: {total_evaluations}")
    if records != EXPECTED_STRUCTURAL:
        raise RuntimeError(f"structural row count changed: {records}")
    if generated_qualified != qualified_identity:
        raise RuntimeError(
            f"qualified identity mismatch: missing={len(qualified_identity - generated_qualified)}, "
            f"extra={len(generated_qualified - qualified_identity)}"
        )
    manifest = {
        "schema_version": "B_TURNOVER_COHORT_FEATURES_V1",
        "status": "COMPLETE",
        "labels": list(EVIDENCE_LABELS),
        "strategy": {"version": STRATEGY_VERSION, "spec_sha256": STRATEGY_SPEC_SHA256, "modified": False},
        "frozen_inputs": context["frozen_identity"] | {"required_registry_artifacts_verified": len(context["registry_verification"])},
        "cohorts": {
            "total_evaluation_rows": total_evaluations,
            "structural_rows": records,
            "qualified_identity_rows": len(qualified_identity),
            "qualified_rows": len(generated_qualified),
            "qualified_identity_matched": len(generated_qualified),
            "structural_symbol_count": len(symbols),
            "structural_year_counts": dict(sorted(structural_years.items())),
            "qualified_year_counts": dict(sorted(qualified_years.items())),
            "stage_counts": dict(sorted(stage_counts.items())),
            "symbols": sorted(symbols),
        },
        "artifact": {
            "path": cohort_path.as_posix(),
            "rows": records,
            "bytes": cohort_path.stat().st_size,
            "file_sha256": _sha256_file(cohort_path),
            "content_stream_sha256": content_digest.hexdigest(),
        },
        "relative_volume_semantics": {
            "source": "corrected B shared numeric semantics / scripts/b_breakout_retest_v1_1.py",
            "formula": "volume_T / mean(volume[T-20:T-1])",
            "lookback_bars": 20,
            "numerator": "raw daily_k volume at T",
            "denominator": "mean of the preceding 20 valid raw daily_k volume bars",
            "t_excluded_from_baseline": True,
            "missing_bar_policy": "unavailable; no interpolation",
            "zero_volume_policy": "unavailable when denominator <= 0",
            "adjusted_volume": False,
            "known_at": "T close",
        },
    }
    _write_json_atomic(output_dir / "cohort_manifest.json", manifest)
    return manifest


def _raw_payload_from_frame(symbol: str, frame: Any) -> dict[str, Any]:
    columns = [str(value) for value in frame.columns]
    records: list[dict[str, Any]] = []
    for item in frame.to_dict(orient="records"):
        normalized: dict[str, Any] = {}
        for key, value in item.items():
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif isinstance(value, np.generic):
                value = value.item()
            if isinstance(value, float) and not math.isfinite(value):
                value = None
            normalized[str(key)] = value
        records.append(normalized)
    return {
        "symbol": symbol,
        "provider_function": "ak.stock_zh_a_hist",
        "parameters": {
            "symbol": _provider_symbol(symbol),
            "period": "daily",
            "start_date": START_DATE_PROVIDER,
            "end_date": END_DATE_PROVIDER,
            "adjust": "",
        },
        "raw_columns": columns,
        "rows": records,
    }


def _load_checkpoint(path: Path, symbols: Sequence[str], raw_dir: Path) -> dict[str, Any]:
    expected = list(sorted(symbols))
    if path.exists():
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        if checkpoint.get("schema_version") != "B_TURNOVER_ACQUISITION_CHECKPOINT_V1":
            raise RuntimeError("turnover acquisition checkpoint schema changed")
        if checkpoint.get("requested_symbols") != expected:
            raise RuntimeError("turnover acquisition requested symbol universe changed")
        return checkpoint
    return {
        "schema_version": "B_TURNOVER_ACQUISITION_CHECKPOINT_V1",
        "status": "IN_PROGRESS",
        "provider": {
            "package": "akshare",
            "function": "ak.stock_zh_a_hist",
            "version": "1.18.94",
            "period": "daily",
            "adjust": "",
            "start_date": START_DATE_PROVIDER,
            "end_date": END_DATE_PROVIDER,
            "raw_field": TURNOVER_FIELD,
            "unit": "percent",
        },
        "acquisition_started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "requested_symbols": expected,
        "completed": {},
        "failed": {},
        "pending": expected,
        "retry_count": 0,
        "raw_dir": raw_dir.as_posix(),
    }


def acquire_turnover(
    *, cohort_manifest_path: Path, checkpoint_path: Path, raw_dir: Path,
    retry_attempts: int = 3, retry_sleep_seconds: float = 2.0,
) -> dict[str, Any]:
    """Acquire one exact AKShare response per structural symbol and checkpoint it."""

    _reject_forbidden((cohort_manifest_path, checkpoint_path, raw_dir))
    cohort_manifest = json.loads(cohort_manifest_path.read_text(encoding="utf-8"))
    symbols = cohort_manifest["cohorts"]["symbols"]
    checkpoint = _load_checkpoint(checkpoint_path, symbols, raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    import akshare as ak

    package_version = str(getattr(ak, "__version__", "unknown"))
    if checkpoint["provider"]["version"] != package_version:
        if checkpoint["completed"]:
            raise RuntimeError("AKShare exact version changed after acquisition started")
        checkpoint["provider"]["version"] = package_version
    checkpoint["acquisition_timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    completed = checkpoint["completed"]
    failed = checkpoint["failed"]
    for symbol in symbols:
        raw_path = raw_dir / f"{symbol.replace('.', '_')}.json"
        prior = completed.get(symbol)
        if prior and raw_path.exists() and _sha256_file(raw_path) == prior.get("file_sha256"):
            continue
        last_error = None
        for attempt in range(1, retry_attempts + 1):
            try:
                frame = ak.stock_zh_a_hist(
                    symbol=_provider_symbol(symbol),
                    period="daily",
                    start_date=START_DATE_PROVIDER,
                    end_date=END_DATE_PROVIDER,
                    adjust="",
                )
                if TURNOVER_FIELD not in frame.columns or DATE_FIELD not in frame.columns:
                    raise ValueError(f"required provider fields missing: {list(frame.columns)}")
                payload = _raw_payload_from_frame(symbol, frame)
                encoded = (_canonical_json(payload) + "\n").encode("utf-8")
                temporary = raw_path.with_suffix(".json.tmp")
                temporary.write_bytes(encoded)
                os.replace(temporary, raw_path)
                completed[symbol] = {
                    "status": "COMPLETED",
                    "provider_symbol": _provider_symbol(symbol),
                    "returned_rows": len(payload["rows"]),
                    "raw_columns": payload["raw_columns"],
                    "file_bytes": raw_path.stat().st_size,
                    "file_sha256": _sha256_file(raw_path),
                    "attempts": attempt,
                }
                failed.pop(symbol, None)
                checkpoint["retry_count"] += attempt - 1
                break
            except Exception as exc:  # provider failure is retained, not substituted
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < retry_attempts:
                    time.sleep(min(30.0, retry_sleep_seconds * (2 ** (attempt - 1))))
        else:
            failed[symbol] = {"status": "FAILED", "error": last_error, "attempts": retry_attempts}
        checkpoint["pending"] = [item for item in symbols if item not in completed and item not in failed]
        checkpoint["failed"] = failed
        checkpoint["completed"] = completed
        _write_json_atomic(checkpoint_path, checkpoint)
        print(f"acquisition symbol={symbol} completed={len(completed)} failed={len(failed)} pending={len(checkpoint['pending'])}", flush=True)

    checkpoint["status"] = "COMPLETE" if not failed and len(completed) == len(symbols) else "PARTIAL_FAILED"
    checkpoint["requested_symbol_count"] = len(symbols)
    checkpoint["completed_symbol_count"] = len(completed)
    checkpoint["failed_symbol_count"] = len(failed)
    checkpoint["pending_symbol_count"] = len(checkpoint["pending"])
    _write_json_atomic(checkpoint_path, checkpoint)
    return checkpoint


def finalize_failed_checkpoint(path: Path) -> dict[str, Any]:
    """Mark an interrupted acquisition as a resumable, fail-closed attempt."""

    _reject_forbidden((path,))
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    symbols = list(checkpoint.get("requested_symbols", []))
    completed = dict(checkpoint.get("completed", {}))
    failed = dict(checkpoint.get("failed", {}))
    checkpoint["pending"] = [symbol for symbol in symbols if symbol not in completed and symbol not in failed]
    checkpoint["status"] = "PARTIAL_FAILED"
    checkpoint["stop_gate"] = "TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY"
    checkpoint["stopped_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    checkpoint["requested_symbol_count"] = len(symbols)
    checkpoint["completed_symbol_count"] = len(completed)
    checkpoint["failed_symbol_count"] = len(failed)
    checkpoint["pending_symbol_count"] = len(checkpoint["pending"])
    _write_json_atomic(path, checkpoint)
    return checkpoint


def _numeric_turnover(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _canonical_turnover_rows(payload: Mapping[str, Any], symbol: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError(f"raw payload rows is not a list for {symbol}")
    by_date: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    conflicting_dates: list[str] = []
    invalid_dates = 0
    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            raise RuntimeError(f"raw row is not an object for {symbol}")
        raw_date = raw_row.get(DATE_FIELD)
        date = str(raw_date)[:10] if raw_date is not None else ""
        try:
            parsed = np.datetime64(date, "D")
            if str(parsed) != date:
                raise ValueError
        except (TypeError, ValueError):
            invalid_dates += 1
            continue
        value = _numeric_turnover(raw_row.get(TURNOVER_FIELD))
        canonical = {"symbol": symbol, "date": date, "turnover_rate_pct": value}
        prior = by_date.get(date)
        if prior is not None:
            duplicate_count += 1
            if prior["turnover_rate_pct"] != value:
                conflicting_dates.append(date)
            continue
        by_date[date] = canonical
    if conflicting_dates:
        raise RuntimeError(f"conflicting duplicate symbol/date values for {symbol}: {sorted(set(conflicting_dates))[:5]}")
    ordered = [by_date[date] for date in sorted(by_date)]
    return ordered, {
        "duplicate_rows_deduplicated": duplicate_count,
        "invalid_date_rows": invalid_dates,
        "first_date": ordered[0]["date"] if ordered else None,
        "last_date": ordered[-1]["date"] if ordered else None,
        "null_turnover_rows": sum(row["turnover_rate_pct"] is None for row in ordered),
        "negative_turnover_rows": sum(row["turnover_rate_pct"] is not None and row["turnover_rate_pct"] < 0 for row in ordered),
    }


def normalize_turnover(
    *, checkpoint_path: Path, raw_dir: Path, canonical_path: Path, manifest_path: Path,
) -> dict[str, Any]:
    """Normalize raw files deterministically and compute raw/content hashes."""

    _reject_forbidden((checkpoint_path, raw_dir, canonical_path, manifest_path))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("status") != "COMPLETE":
        raise RuntimeError("all symbols must complete before canonical normalization")
    import pyarrow as pa
    import pyarrow.parquet as pq

    raw_digest = hashlib.sha256()
    content_digest = hashlib.sha256()
    total_rows = 0
    duplicate_rows = 0
    invalid_date_rows = 0
    null_rows = 0
    negative_rows = 0
    raw_symbol_meta: dict[str, Any] = {}
    schema = pa.schema([
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("date", pa.string(), nullable=False),
        pa.field("turnover_rate_pct", pa.float64(), nullable=True),
    ])
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(canonical_path, schema=schema, compression="zstd")
    try:
        for symbol in checkpoint["requested_symbols"]:
            raw_path = raw_dir / f"{symbol.replace('.', '_')}.json"
            raw_bytes = raw_path.read_bytes()
            raw_digest.update(symbol.encode("utf-8") + b"\n" + raw_bytes)
            payload = json.loads(raw_bytes.decode("utf-8"))
            rows, metadata = _canonical_turnover_rows(payload, symbol)
            for row in rows:
                content_digest.update((_canonical_json(row) + "\n").encode("utf-8"))
            if rows:
                table = pa.Table.from_pylist(rows, schema=schema)
                writer.write_table(table)
            total_rows += len(rows)
            duplicate_rows += metadata["duplicate_rows_deduplicated"]
            invalid_date_rows += metadata["invalid_date_rows"]
            null_rows += metadata["null_turnover_rows"]
            negative_rows += metadata["negative_turnover_rows"]
            raw_symbol_meta[symbol] = metadata
    finally:
        writer.close()
    result = {
        "status": "COMPLETE",
        "provider": checkpoint["provider"],
        "requested_symbols": checkpoint["requested_symbols"],
        "requested_symbol_count": len(checkpoint["requested_symbols"]),
        "completed_symbols": sorted(checkpoint["completed"]),
        "failed_symbols": sorted(checkpoint["failed"]),
        "raw_acquisition": {
            "raw_dir": raw_dir.as_posix(),
            "raw_bytes_stream_sha256": raw_digest.hexdigest(),
            "symbol_files": raw_symbol_meta,
        },
        "canonical_dataset": {
            "path": canonical_path.as_posix(),
            "rows": total_rows,
            "bytes": canonical_path.stat().st_size,
            "file_sha256": _sha256_file(canonical_path),
            "content_stream_sha256": content_digest.hexdigest(),
            "duplicate_rows_deduplicated": duplicate_rows,
            "invalid_date_rows": invalid_date_rows,
            "null_turnover_rows": null_rows,
            "negative_turnover_rows": negative_rows,
        },
        "raw_field": TURNOVER_FIELD,
        "unit": "percent",
    }
    _write_json_atomic(manifest_path, result)
    return result


def _load_cohort_rows(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            yield json.loads(line)


def _load_canonical_turnover(path: Path) -> Any:
    import pandas as pd
    frame = pd.read_parquet(path, columns=["symbol", "date", "turnover_rate_pct"])
    frame["key"] = frame["symbol"].astype(str) + "|" + frame["date"].astype(str)
    if frame["key"].duplicated().any():
        raise RuntimeError("canonical symbol/date duplicate remains after normalization")
    return frame.set_index("key")


def audit_inputs(
    *, cohort_manifest_path: Path, cohort_path: Path, acquisition_manifest_path: Path,
    canonical_path: Path, output_manifest_path: Path,
) -> dict[str, Any]:
    """Audit turnover T-day coverage and RV semantics before any outcome access."""

    _reject_forbidden((cohort_manifest_path, cohort_path, acquisition_manifest_path, canonical_path, output_manifest_path))
    cohort_manifest = json.loads(cohort_manifest_path.read_text(encoding="utf-8"))
    acquisition = json.loads(acquisition_manifest_path.read_text(encoding="utf-8"))
    if acquisition.get("status") != "COMPLETE":
        blocked = {
            "schema_version": SCHEMA_VERSION,
            "status": "TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY",
            "labels": list(EVIDENCE_LABELS),
            "decision_gate": "TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY",
            "provider": acquisition.get("provider"),
            "cohort": {
                "structural_rows": cohort_manifest["cohorts"]["structural_rows"],
                "qualified_rows": cohort_manifest["cohorts"]["qualified_rows"],
                "structural_symbols": cohort_manifest["cohorts"]["structural_symbol_count"],
                "qualified_identity_rows": cohort_manifest["cohorts"]["qualified_identity_rows"],
            },
            "acquisition": {
                "status": acquisition.get("status"),
                "requested_symbols": acquisition.get("requested_symbols", []),
                "completed_symbols": acquisition.get("completed_symbols", sorted(acquisition.get("completed", {}))),
                "failed_symbols": acquisition.get("failed_symbols", sorted(acquisition.get("failed", {}))),
                "pending_symbols": acquisition.get("pending_symbols", acquisition.get("pending", [])),
                "checkpoint": acquisition_manifest_path.as_posix(),
            },
            "coverage": {
                "qualified": {"matched": 0, "total": EXPECTED_QUALIFIED, "coverage": None, "minimum": MIN_QUALIFIED_COVERAGE, "status": "NOT_EVALUATED"},
                "structural": {"matched": 0, "total": EXPECTED_STRUCTURAL, "coverage": None, "minimum": MIN_STRUCTURAL_COVERAGE, "status": "NOT_EVALUATED"},
                "status": "NOT_EVALUATED_DUE_TO_PROVIDER_FAILURE",
            },
            "data_quality": {"status": "NOT_EVALUATED_DUE_TO_PROVIDER_FAILURE"},
            "relative_volume_semantics": cohort_manifest["relative_volume_semantics"],
            "outcome_access": {
                "status": OUTCOME_ACCESS_STATUS,
                "note": OUTCOME_ACCESS_NOTE,
                "required_next_gate": "NEW_PROVIDER_ACCESS_OR_RESUME",
            },
            "boundaries": {
                "b_unchanged": True,
                "prospective_pipeline_unchanged": True,
                "frozen_registry_unchanged": True,
                "final_oos_read": False,
                "new_provider": False,
                "outcome_read": True,
                "outcome_values_used": False,
            },
        }
        _write_json_atomic(output_manifest_path, blocked)
        return blocked
    turnover = _load_canonical_turnover(canonical_path)
    qualified_rows = 0
    structural_rows = 0
    qualified_matches = 0
    structural_matches = 0
    qualified_by_year: Counter[str] = Counter()
    structural_by_year: Counter[str] = Counter()
    qualified_by_board: Counter[str] = Counter()
    structural_by_board: Counter[str] = Counter()
    matched_qualified_by_year: Counter[str] = Counter()
    matched_structural_by_year: Counter[str] = Counter()
    matched_qualified_by_board: Counter[str] = Counter()
    matched_structural_by_board: Counter[str] = Counter()
    zero_turnover_structural = 0
    zero_volume_structural = 0
    null_at_t = 0
    missing_at_t = 0
    relative_volume_unavailable = 0
    feature_rows: list[dict[str, Any]] = []
    provider_first_dates: dict[str, str | None] = {}
    provider_last_dates: dict[str, str | None] = {}
    first_date_counts: Counter[str] = Counter()
    for symbol, meta in acquisition["raw_acquisition"]["symbol_files"].items():
        provider_first_dates[symbol] = meta["first_date"]
        provider_last_dates[symbol] = meta["last_date"]
        if meta["first_date"]:
            first_date_counts[meta["first_date"]] += 1
    for row in _load_cohort_rows(cohort_path):
        symbol, date = row["symbol"], row["signal_date"]
        key = f"{symbol}|{date}"
        found = key in turnover.index
        value = turnover.loc[key, "turnover_rate_pct"] if found else None
        valid_match = found and value is not None and math.isfinite(float(value)) and float(value) >= 0
        is_qualified = bool(row["final_b_qualified"])
        structural_rows += 1
        structural_by_year[row["year"]] += 1
        structural_by_board[row["board"]] += 1
        if found and value is None:
            null_at_t += 1
        if not found:
            missing_at_t += 1
        if valid_match:
            structural_matches += 1
            matched_structural_by_year[row["year"]] += 1
            matched_structural_by_board[row["board"]] += 1
            if float(value) == 0:
                zero_turnover_structural += 1
        # The frozen raw daily_k volume is only used for this input audit and RV.
        # A T-day zero-volume row is counted as a potential suspension/no-trade.
        if row.get("relative_volume") is None:
            relative_volume_unavailable += 1
        if is_qualified:
            qualified_rows += 1
            qualified_by_year[row["year"]] += 1
            qualified_by_board[row["board"]] += 1
            if valid_match:
                qualified_matches += 1
                matched_qualified_by_year[row["year"]] += 1
                matched_qualified_by_board[row["board"]] += 1
        if is_qualified or valid_match:
            feature_rows.append({
                "symbol": symbol,
                "signal_date": date,
                "year": row["year"],
                "board": row["board"],
                "turnover_rate_pct": None if value is None else float(value),
                "relative_volume": row.get("relative_volume"),
            })

    # The cohort builder is required to emit the canonical RV feature.  The
    # first implementation intentionally stores the audit value as a derived
    # pre-outcome field in the cohort; reject a missing value instead of using a
    # second formula here.
    if structural_rows != EXPECTED_STRUCTURAL or qualified_rows != EXPECTED_QUALIFIED:
        raise RuntimeError(f"cohort identity counts changed: structural={structural_rows}, qualified={qualified_rows}")

    def coverage(matches: int, total: int) -> float:
        return float(matches / total) if total else 0.0

    qualified_coverage = coverage(qualified_matches, qualified_rows)
    structural_coverage = coverage(structural_matches, structural_rows)
    strata: dict[str, Any] = {"year": {}, "board": {}}
    for group_name, totals, matches in (
        ("year", qualified_by_year, matched_qualified_by_year),
        ("board", qualified_by_board, matched_qualified_by_board),
    ):
        for key, total in sorted(totals.items()):
            strata[group_name][key] = {"rows": total, "matched": matches[key], "coverage": coverage(matches[key], total)}
    for group_name, totals, matches in (
        ("structural_year", structural_by_year, matched_structural_by_year),
        ("structural_board", structural_by_board, matched_structural_by_board),
    ):
        strata[group_name] = {
            key: {"rows": total, "matched": matches[key], "coverage": coverage(matches[key], total)}
            for key, total in sorted(totals.items())
        }
    major_qualified_strata = list(strata["year"].values()) + [
        strata["board"].get(board, {"coverage": 0}) for board in BOARD_GROUPS
    ]
    major_structural_strata = list(strata["structural_year"].values()) + [
        strata["structural_board"].get(board, {"coverage": 0}) for board in BOARD_GROUPS
    ]
    coverage_ready = (
        qualified_coverage >= MIN_QUALIFIED_COVERAGE
        and structural_coverage >= MIN_STRUCTURAL_COVERAGE
        and all(item["coverage"] >= MIN_STRATUM_COVERAGE for item in major_qualified_strata)
        and all(item["coverage"] >= MIN_STRATUM_COVERAGE for item in major_structural_strata)
    )
    values = [row["turnover_rate_pct"] for row in feature_rows if row["turnover_rate_pct"] is not None]
    values_array = np.asarray(values, dtype=float)
    impossible = [value for value in values if not math.isfinite(value) or value < 0]
    unit_stability = {
        "raw_field": TURNOVER_FIELD,
        "unit": "percent",
        "numeric_non_negative": not impossible,
        "finite": all(math.isfinite(value) for value in values),
        "min": float(np.min(values_array)) if len(values_array) else None,
        "median": float(np.median(values_array)) if len(values_array) else None,
        "p99": float(np.quantile(values_array, 0.99)) if len(values_array) else None,
        "max": float(np.max(values_array)) if len(values_array) else None,
    }
    newly_listed = sorted(symbol for symbol, date in provider_first_dates.items() if date and date > START_DATE)
    partial_responses = sorted(
        symbol for symbol, meta in acquisition["raw_acquisition"]["symbol_files"].items()
        if int(meta.get("returned_rows", 0)) < len(set(row["signal_date"] for row in feature_rows if row["symbol"] == symbol))
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "RESEARCH_READY" if coverage_ready and not impossible else "TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY",
        "labels": list(EVIDENCE_LABELS),
        "decision_gate": None if coverage_ready and not impossible else "TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY",
        "provider": acquisition["provider"],
        "cohort": {
            "structural_rows": structural_rows,
            "qualified_rows": qualified_rows,
            "structural_symbols": cohort_manifest["cohorts"]["structural_symbol_count"],
            "qualified_identity_rows": cohort_manifest["cohorts"]["qualified_identity_rows"],
        },
        "coverage": {
            "qualified": {"matched": qualified_matches, "total": qualified_rows, "coverage": qualified_coverage, "minimum": MIN_QUALIFIED_COVERAGE},
            "structural": {"matched": structural_matches, "total": structural_rows, "coverage": structural_coverage, "minimum": MIN_STRUCTURAL_COVERAGE},
            "strata": strata,
        },
        "data_quality": {
            "missing_at_t": missing_at_t,
            "null_at_t": null_at_t,
            "relative_volume_unavailable": relative_volume_unavailable,
            "zero_turnover_structural": zero_turnover_structural,
            "zero_volume_structural": zero_volume_structural,
            "negative_values": len(impossible),
            "newly_listed_symbols_by_first_provider_date": newly_listed,
            "newly_listed_symbol_count": len(newly_listed),
            "suspended_or_no_trade_proxy": "T-day raw daily_k volume==0; exact trading status not inferred",
            "partial_response_symbols": partial_responses,
            "partial_response_count": len(partial_responses),
            "duplicate_symbol_date_rows_deduplicated": acquisition["canonical_dataset"]["duplicate_rows_deduplicated"],
            "conflicting_duplicate_values": False,
            "impossible_values": impossible[:20],
            "unit_stability": unit_stability,
        },
        "relative_volume_semantics": cohort_manifest["relative_volume_semantics"],
        "acquisition_manifest": acquisition_manifest_path.as_posix(),
        "canonical_dataset": acquisition["canonical_dataset"],
        "raw_acquisition": {
            "raw_dir": acquisition["raw_acquisition"]["raw_dir"],
            "raw_bytes_stream_sha256": acquisition["raw_acquisition"]["raw_bytes_stream_sha256"],
        },
        "outcome_access": {
            "status": OUTCOME_ACCESS_STATUS,
            "note": OUTCOME_ACCESS_NOTE,
            "required_next_gate": "PRE_OUTCOME_PROTOCOL_COMMIT",
        },
    }
    _write_json_atomic(output_manifest_path, result)
    return result


def write_blocked_artifacts(
    *, input_manifest_path: Path, checkpoint_path: Path, summary_path: Path,
    report_path: Path, intake_master_sha: str, branch: str,
) -> dict[str, Any]:
    """Write the required gate-A summary/report without outcome access."""

    _reject_forbidden((input_manifest_path, checkpoint_path, summary_path, report_path))
    manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    failed = sorted(checkpoint.get("failed", {}))
    pending = sorted(checkpoint.get("pending", []))
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "BLOCKED",
        "labels": list(EVIDENCE_LABELS),
        "intake": {
            "master_sha": intake_master_sha,
            "branch": branch,
            "expected_master_sha": "38322b91f691b23e7ebaa10818a8733169aafab8",
        },
        "turnover_acquisition": {
            "source": "AkShare",
            "package_version": checkpoint.get("provider", {}).get("version"),
            "function": "ak.stock_zh_a_hist",
            "endpoint": "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            "parameters": checkpoint.get("provider"),
            "requested_symbols": len(checkpoint.get("requested_symbols", [])),
            "completed_symbols": len(checkpoint.get("completed", {})),
            "failed_symbols": len(failed),
            "pending_symbols": len(pending),
            "persisted_raw_rows": 0,
            "raw_sha256": None,
            "canonical_content_sha256": None,
            "error_class": "ProxyError / RemoteDisconnected",
            "sample_failed_symbols": failed[:10],
        },
        "cohort_coverage": {
            "qualified": {"matched": 0, "total": EXPECTED_QUALIFIED, "coverage": None, "status": "NOT_EVALUATED"},
            "structural": {"matched": 0, "total": EXPECTED_STRUCTURAL, "coverage": None, "status": "NOT_EVALUATED"},
        },
        "relative_volume": {
            "formula": "RV20_T = volume_T / mean(volume[T-20:T-1])",
            "semantic_source": "corrected B shared numeric semantics / scripts/b_breakout_retest_v1_1.py",
            "lookback": 20,
            "t_excluded": True,
            "missing_bar_policy": "unavailable; no interpolation",
            "zero_volume_policy": "unavailable when denominator <= 0",
            "source_column": "daily_k.volume",
            "known_at": "T close",
        },
        "protocol": {"pre_outcome_commit": None, "status": "NOT_CREATED_DUE_TO_GATE_A"},
        "decision_gate": "TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY",
        "research_decision": None,
        "outcome_access": OUTCOME_ACCESS_STATUS,
        "outcome_access_note": OUTCOME_ACCESS_NOTE,
        "boundaries": {
            "b_unchanged": True,
            "prospective_pipeline_unchanged": True,
            "frozen_dataset_unchanged": True,
            "frozen_registry_unchanged": True,
            "continuous_speed_probe_read": False,
            "final_oos_read": False,
            "new_provider": False,
            "threshold_search": False,
            "parameter_sweep": False,
            "outcome_values_used": False,
        },
        "input_manifest": input_manifest_path.as_posix(),
        "resume_checkpoint": checkpoint_path.as_posix(),
    }
    summary["content_sha256"] = hashlib.sha256(
        (_canonical_json({key: value for key, value in summary.items() if key != "content_sha256"}) + "\n").encode("utf-8")
    ).hexdigest()
    _write_json_atomic(summary_path, summary)
    report = f"""# B Turnover x Relative Volume Incremental Diagnostic V1

Labels: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DATE_ANCHORED` / `NO_VINTAGE_PROOF` / `DIAGNOSTIC_ONLY`

## Gate-A decision

`TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY`

This task stopped before the pre-outcome protocol commit because the authorized
primary AKShare source could not provide a usable acquisition. The resumable
checkpoint remains available for a later explicitly authorized resume or source
decision. Outcome analysis was not started. During intake, one pre-existing event
record was inspected only to identify the artifact schema; no outcome value was
used in computation, filtering, or conclusion.

## Intake and acquisition

| item | value |
| --- | --- |
| intake master | `{intake_master_sha}` |
| branch | `{branch}` |
| provider | `akshare 1.18.94`, `ak.stock_zh_a_hist` |
| endpoint | `https://push2his.eastmoney.com/api/qt/stock/kline/get` |
| parameters | `period=daily`, `start_date=20230630`, `end_date=20260828`, `adjust=''` |
| requested symbols | {len(checkpoint.get('requested_symbols', []))} |
| completed symbols | {len(checkpoint.get('completed', {}))} |
| failed symbols | {len(failed)} |
| pending symbols | {len(pending)} |
| persisted raw rows | 0 |
| raw / canonical SHA | `NOT_CREATED` |

The first bounded failures were consistent `ProxyError` / `RemoteDisconnected`
 responses from the Eastmoney endpoint after three attempts per symbol. No failed
response was promoted into the canonical dataset and no second provider was used.

## Cohort and semantics

The no-outcome cohort reconciliation completed at exact counts: 4,041,140 frozen
evaluations, 573,586 structural first-breakout rows, 17,714 qualified identities,
and 5,386 structural symbols. Turnover coverage is `NOT_EVALUATED` because the
provider gate failed before any symbol was persisted (`0/17,714`, `0/573,586` are
not coverage estimates).

The frozen relative-volume definition is:

`RV20_T = volume_T / mean(volume[T-20:T-1])`

It uses raw `daily_k.volume`, excludes T from the 20-bar baseline, requires 20
valid prior bars and a positive denominator, and does not interpolate missing
bars or use adjusted volume. The semantic source is the corrected B shared
numeric semantics in `scripts/b_breakout_retest_v1_1.py`.

## Boundaries

- B spec, score, threshold, breakout/retest rule, hard gates, Top-N, universe,
  sector/ST semantics and prospective pipeline were unchanged.
- Existing frozen dataset and frozen registry were unchanged.
- Final OOS was not read; C and Phase 2F were not run.
- No pre-outcome protocol commit exists because gate A precedes protocol creation.
- No promotion, freeze, threshold search, parameter sweep, model fitting or
  Drive/upload action occurred.

Resume evidence: `{checkpoint_path.as_posix()}`  
Input manifest: `{input_manifest_path.as_posix()}`  
Summary content SHA-256: `{summary['content_sha256']}`
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8", newline="\n")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    common = {
        "raw_dir": Path("data/validation/core_signal_validation/raw"),
        "checkpoint": Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_resume_checkpoint.json"),
        "core_output": Path("data/validation/core_signal_validation_continuous_parts/core_replay_results.jsonl.gz"),
        "core_manifest": Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"),
        "qualified_events": Path("data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"),
        "registry": Path("data/governance/frozen_artifacts.json"),
        "output_dir": Path("data/validation/b_turnover_x_relative_volume_incremental_v1"),
    }
    build = sub.add_parser("build-cohort")
    for name, value in common.items():
        build.add_argument(f"--{name.replace('_', '-')}", dest=name, type=Path, default=value)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--cohort-manifest", type=Path, default=common["output_dir"] / "cohort_manifest.json")
    acquire.add_argument("--checkpoint", type=Path, default=common["output_dir"] / "acquisition_checkpoint.json")
    acquire.add_argument("--raw-dir", type=Path, default=common["output_dir"] / "raw")
    acquire.add_argument("--retry-attempts", type=int, default=3)
    acquire.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    finalize = sub.add_parser("finalize-failed-checkpoint")
    finalize.add_argument("--checkpoint", type=Path, default=common["output_dir"] / "acquisition_checkpoint.json")
    normalize = sub.add_parser("normalize")
    normalize.add_argument("--checkpoint", type=Path, default=common["output_dir"] / "acquisition_checkpoint.json")
    normalize.add_argument("--raw-dir", type=Path, default=common["output_dir"] / "raw")
    normalize.add_argument("--canonical", type=Path, default=common["output_dir"] / "canonical_turnover.parquet")
    normalize.add_argument("--manifest", type=Path, default=common["output_dir"] / "acquisition_manifest.json")
    audit = sub.add_parser("audit")
    audit.add_argument("--cohort-manifest", type=Path, default=common["output_dir"] / "cohort_manifest.json")
    audit.add_argument("--cohort", type=Path, default=common["output_dir"] / "cohort_features.jsonl.gz")
    audit.add_argument("--acquisition-manifest", type=Path, default=common["output_dir"] / "acquisition_manifest.json")
    audit.add_argument("--canonical", type=Path, default=common["output_dir"] / "canonical_turnover.parquet")
    audit.add_argument("--manifest", type=Path, default=common["output_dir"] / "input_manifest.json")
    blocked = sub.add_parser("write-blocked-artifacts")
    blocked.add_argument("--input-manifest", type=Path, default=common["output_dir"] / "input_manifest.json")
    blocked.add_argument("--checkpoint", type=Path, default=common["output_dir"] / "acquisition_checkpoint.json")
    blocked.add_argument("--summary", type=Path, default=common["output_dir"] / "summary.json")
    blocked.add_argument("--report", type=Path, default=Path("docs/research/b_turnover_x_relative_volume_incremental_v1_report.md"))
    blocked.add_argument("--intake-master-sha", required=True)
    blocked.add_argument("--branch", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.command == "build-cohort":
        result = build_cohort(
            raw_dir=args.raw_dir, checkpoint_path=args.checkpoint, core_output=args.core_output,
            core_manifest_path=args.core_manifest, qualified_events_path=args.qualified_events,
            registry_path=args.registry, output_dir=args.output_dir,
        )
    elif args.command == "acquire":
        result = acquire_turnover(
            cohort_manifest_path=args.cohort_manifest, checkpoint_path=args.checkpoint,
            raw_dir=args.raw_dir, retry_attempts=args.retry_attempts,
            retry_sleep_seconds=args.retry_sleep_seconds,
        )
    elif args.command == "finalize-failed-checkpoint":
        result = finalize_failed_checkpoint(args.checkpoint)
    elif args.command == "normalize":
        result = normalize_turnover(
            checkpoint_path=args.checkpoint, raw_dir=args.raw_dir,
            canonical_path=args.canonical, manifest_path=args.manifest,
        )
    elif args.command == "audit":
        result = audit_inputs(
            cohort_manifest_path=args.cohort_manifest, cohort_path=args.cohort,
            acquisition_manifest_path=args.acquisition_manifest, canonical_path=args.canonical,
            output_manifest_path=args.manifest,
        )
    elif args.command == "write-blocked-artifacts":
        result = write_blocked_artifacts(
            input_manifest_path=args.input_manifest, checkpoint_path=args.checkpoint,
            summary_path=args.summary, report_path=args.report,
            intake_master_sha=args.intake_master_sha, branch=args.branch,
        )
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True)[:12000])


if __name__ == "__main__":
    main()
