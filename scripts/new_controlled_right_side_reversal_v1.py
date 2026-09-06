"""Independent fixed evaluator for NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1.

The signal pass reads only the existing date-anchored T-close replay inputs.
The outcome pass is separate and requires the committed pre-outcome protocol.
This module does not import a production watchlist generator, old D artifacts,
Final OOS data, or the forbidden continuous-speed-probe directory.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

import core_signal_replay as replay
import validate_development_returns_v2 as returns_v2


STRATEGY_VERSION = "NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1"
PROTOCOL_COMMIT = "123ef5299ef94411a0b1cb4ec5745ee2c472979e"
DOWNSIDE_LOOKBACK = 20
DOWNSIDE_QUANTILE = 0.20
RECLAIM_LOOKBACK = 5
BOUNCE_BINS = 5
MIN_SIGNAL_BARS = DOWNSIDE_LOOKBACK + 2
BOOTSTRAP_BLOCK_LENGTH = 20
BOOTSTRAP_REPETITIONS = 5000
BOOTSTRAP_SEED = 20260906
PRIMARY_HORIZON = "10D"
SECONDARY_HORIZON = "5D"
SIGNAL_SCHEMA = "CRSR_SIGNAL_MEMBERSHIP_V1"
SUMMARY_SCHEMA = "CRSR_RESEARCH_SUMMARY_V1"
MANIFEST_SCHEMA = "CRSR_RESEARCH_MANIFEST_V1"
VALID_GROUPS = ("CANDIDATE", "PRIMARY_CONTROL", "FULL_DOWNSIDE_BOUNCE", "GENERIC_RECLAIM", "GENERIC_BOUNCE_CONTROL")
BOARDS = ("Main", "ChiNext", "STAR", "OUT_OF_SCOPE_PREFIX")
EXPECTED_DAILY_K_SHA256 = "61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426"
EXPECTED_ADJUSTMENT_SHA256 = "a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716"
EXPECTED_CORE_OUTPUT_SHA256 = "0d23cf54843920f5fdcc05847e4b78c5d605b05c8793f878b6021c85b3ab0c2f"
EXPECTED_UNIVERSE_ROWS = 4_041_140
EXPECTED_UNIVERSE_IDENTITY_SHA256 = "dbc5d220f24f51a0245d047b88733c961fc4f184d02ef6f5ac0fc795576217b0"
UNAVAILABLE_ENTRY_STATUSES = {"NO_T_PLUS_1_OPEN", "SYMBOL_NOT_IN_RAW_STORE", "INCOMPLETE_STOCK_WINDOW"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _board(symbol: str) -> str:
    code = symbol.split(".", 1)[0]
    if code.startswith(("00", "60")):
        return "Main"
    if code.startswith("30"):
        return "ChiNext"
    if code.startswith("68"):
        return "STAR"
    return "OUT_OF_SCOPE_PREFIX"


def _iter_jsonl_gzip(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _jsonl_gzip_identity(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    rows = 0
    with gzip.open(path, "rb") as handle:
        for line in handle:
            digest.update(line)
            rows += 1
    return {"rows": rows, "bytes": path.stat().st_size, "file_sha256": file_sha256(path), "content_sha256": digest.hexdigest()}


def _write_jsonl_gzip(path: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            for row in rows:
                line = (canonical_json(dict(row)) + "\n").encode("utf-8")
                compressed.write(line)
                digest.update(line)
                count += 1
    return {"path": path.as_posix(), "rows": count, "bytes": path.stat().st_size, "file_sha256": file_sha256(path), "content_sha256": digest.hexdigest()}


def _rank_ascending(values: Mapping[str, float]) -> dict[str, int]:
    ordered = sorted(values.items(), key=lambda item: (float(item[1]), item[0]))
    return {symbol: rank for rank, (symbol, _value) in enumerate(ordered, start=1)}


def _bottom_k(n: int) -> int:
    return int(math.ceil(DOWNSIDE_QUANTILE * n))


def _simple_positive_bounce(close_t: float, close_t_minus_1: float) -> bool:
    return float(close_t) > float(close_t_minus_1)


def _reclaim5(close_t: float, prior_close_high5: float) -> bool:
    return float(close_t) > float(prior_close_high5)


def _bounce_bin(rank: int, baseline_size: int) -> int:
    if rank < 1 or baseline_size < 1 or rank > baseline_size:
        raise ValueError("bounce rank is outside baseline")
    return min(BOUNCE_BINS, ((rank - 1) * BOUNCE_BINS) // baseline_size + 1)


def _moving_block_bootstrap_ci(values: Sequence[float], *, block_length: int = BOOTSTRAP_BLOCK_LENGTH, repetitions: int = BOOTSTRAP_REPETITIONS, seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) == 0 or not np.isfinite(array).all():
        raise ValueError("bootstrap values must be a non-empty finite vector")
    if block_length < 1 or block_length > len(array) or repetitions < 1:
        raise ValueError("invalid moving-block bootstrap parameters")
    starts = np.arange(0, len(array) - block_length + 1, dtype=int)
    rng = np.random.default_rng(seed)
    block_count = int(math.ceil(len(array) / block_length))
    means = np.empty(repetitions, dtype=float)
    for index in range(repetitions):
        selected = rng.choice(starts, size=block_count, replace=True)
        sample = np.concatenate([array[start : start + block_length] for start in selected])[: len(array)]
        means[index] = float(np.mean(sample))
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _rankdata(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(len(array), dtype=float)
    position = 0
    while position < len(order):
        end = position + 1
        while end < len(order) and array[order[end]] == array[order[position]]:
            end += 1
        ranks[order[position:end]] = (position + 1 + end) / 2.0
        position = end
    return ranks


def spearman(values_x: Sequence[float], values_y: Sequence[float]) -> float | None:
    if len(values_x) != len(values_y) or len(values_x) < 2:
        return None
    x, y = _rankdata(values_x), _rankdata(values_y)
    xc, yc = x - np.mean(x), y - np.mean(y)
    denominator = float(np.sqrt(np.sum(xc * xc) * np.sum(yc * yc)))
    return None if denominator == 0 else float(np.sum(xc * yc) / denominator)


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "p25": None, "p75": None}
    array = np.asarray(values, dtype=float)
    return {"n": int(len(array)), "mean": float(np.mean(array)), "median": float(np.median(array)), "p25": float(np.quantile(array, 0.25)), "p75": float(np.quantile(array, 0.75))}


def _summary_stats(values: Sequence[float], state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = _distribution(values)
    result["positive_rate"] = float(np.mean(np.asarray(values) > 0)) if values else None
    if state is not None:
        result.update({
            "event_count": int(state["event_count"]),
            "mfe_mean": float(np.mean(state["mfe"])) if state["mfe"] else None,
            "mfe_median": float(np.median(state["mfe"])) if state["mfe"] else None,
            "mae_mean": float(np.mean(state["mae"])) if state["mae"] else None,
            "mae_median": float(np.median(state["mae"])) if state["mae"] else None,
            "status_counts": dict(sorted(state["status_counts"].items())),
            "reference_entry_available_count": int(state["reference_entry_available_count"]),
            "reference_entry_coverage": (state["reference_entry_available_count"] / state["event_count"] if state["event_count"] else None),
        })
    return result


def _new_state() -> dict[str, Any]:
    return {"event_count": 0, "reference_entry_available_count": 0, "status_counts": Counter(), "returns": [], "mfe": [], "mae": []}


def _reference_entry_available(outcome_record: Mapping[str, Any]) -> bool:
    status = str(outcome_record["outcomes"]["1D"]["status"])
    return status not in UNAVAILABLE_ENTRY_STATUSES


def _update_state(state: dict[str, Any], outcome_record: Mapping[str, Any], horizon: str) -> None:
    outcome = outcome_record["outcomes"][horizon]
    state["event_count"] += 1
    state["reference_entry_available_count"] += int(_reference_entry_available(outcome_record))
    state["status_counts"][str(outcome["status"])] += 1
    if outcome["status"] == "AVAILABLE":
        state["returns"].append(float(outcome["return_pct"]))
        state["mfe"].append(float(outcome["mfe_pct"]))
        state["mae"].append(float(outcome["mae_pct"]))


def _feature_from_bars(closes: Sequence[float], volumes: Sequence[float], highs: Sequence[float], lows: Sequence[float]) -> dict[str, float] | None:
    if len(closes) < MIN_SIGNAL_BARS or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    c = np.asarray(closes, dtype=float)
    hi = np.asarray(highs, dtype=float)
    lo = np.asarray(lows, dtype=float)
    volume = np.asarray(volumes, dtype=float)
    if not np.isfinite(c).all() or not np.isfinite(hi).all() or not np.isfinite(lo).all() or not np.isfinite(volume).all():
        return None
    if (c <= 0).any() or (hi <= 0).any() or (lo <= 0).any() or (volume < 0).any():
        return None
    if len(c[-6:-1]) != RECLAIM_LOOKBACK or len(c[-22:-2]) != DOWNSIDE_LOOKBACK:
        return None
    r20_pre = float(c[-2] / c[-22] - 1.0)
    t_day_return = float(c[-1] / c[-2] - 1.0)
    prior_close_high5 = float(np.max(c[-6:-1]))
    reclaim_margin = float(c[-1] / prior_close_high5 - 1.0)
    prior_realized_volatility = float(np.std((c[-21:-1] / c[-22:-2] - 1.0) * 100.0, ddof=1))
    return {
        "r20_pre": r20_pre,
        "t_day_return": t_day_return,
        "prior_close_high5": prior_close_high5,
        "reclaim_margin": reclaim_margin,
        "close_t": float(c[-1]),
        "close_t_minus_1": float(c[-2]),
        "invalidation_reference": float(np.min(lo[-5:])),
        "prior_realized_volatility20_pct": prior_realized_volatility,
        "median_traded_amount20": float(np.median(volume[-20:])),
    }


def _classify(downside_extreme: bool, simple_bounce: bool, reclaim5: bool) -> tuple[bool, bool, bool]:
    baseline = bool(downside_extreme and simple_bounce)
    candidate = bool(downside_extreme and reclaim5)
    control = bool(baseline and not reclaim5)
    return candidate, control, baseline


def _load_membership(path: Path | None, *, label: str) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    if path is None or not path.exists():
        return set(), {"status": "NOT_AVAILABLE", "label": label, "outcomes_accessed": False}
    if "final_oos" in str(path).lower() or "continuous_speed_probe" in str(path).lower():
        raise RuntimeError("forbidden research input path")
    memberships: set[tuple[str, str]] = set()
    rows = 0
    for record in _iter_jsonl_gzip(path):
        rows += 1
        date = record.get("date", record.get("signal_date"))
        symbol = record.get("symbol")
        if isinstance(date, str) and isinstance(symbol, str):
            memberships.add((date, symbol.lower()))
    return memberships, {"status": "AVAILABLE", "label": label, "logical_path": path.as_posix(), "rows_read_for_signal_membership": rows, "unique_signal_memberships": len(memberships), "file_sha256": file_sha256(path), "outcomes_accessed": False}


def _input_audit(raw_dir: Path, core_manifest_path: Path, core_output_path: Path) -> dict[str, Any]:
    paths = (raw_dir, core_manifest_path, core_output_path)
    if any("final_oos" in str(path).lower() or "continuous_speed_probe" in str(path).lower() for path in paths):
        raise RuntimeError("forbidden research input path")
    manifest = json.loads(core_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "CORE_SIGNAL_VALIDATION_DATASET_MANIFEST_V1":
        raise RuntimeError("CRSR_INPUT_PROVENANCE_CONFLICT: core manifest schema")
    index_dates, _index_bars, index_meta = replay._load_index(raw_dir)
    store, stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")
    signal_dates = replay._continuous_signal_dates(index_dates)
    coverage = replay._coverage_by_date(store, signal_dates, index_dates)
    evaluated = sum(item["evaluable_symbol_count"] for item in coverage.values())
    expected = int(manifest["replay"]["candidate_evaluations"])
    daily_hash = file_sha256(raw_dir / "daily_k.parquet")
    adjustment_hash = file_sha256(raw_dir / "adjustment_factors.parquet")
    core_hash = file_sha256(core_output_path)
    if evaluated != expected or expected != EXPECTED_UNIVERSE_ROWS or daily_hash != EXPECTED_DAILY_K_SHA256 or adjustment_hash != EXPECTED_ADJUSTMENT_SHA256 or core_hash != EXPECTED_CORE_OUTPUT_SHA256:
        raise RuntimeError("CRSR_INPUT_PROVENANCE_CONFLICT: frozen input identity mismatch")
    previous: tuple[str, str] | None = None
    ordered = True
    identity_rows = 0
    identity_digest = hashlib.sha256()
    with gzip.open(core_output_path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            row = json.loads(line)
            key = (str(row["signal_date"]), str(row["symbol"]).lower())
            ordered = ordered and (previous is None or key >= previous)
            previous = key
            identity_digest.update(f"{key[0]}|{key[1]}\n".encode("utf-8"))
            identity_rows += 1
    if not ordered or identity_rows != EXPECTED_UNIVERSE_ROWS or identity_digest.hexdigest() != EXPECTED_UNIVERSE_IDENTITY_SHA256:
        raise RuntimeError("CRSR_HISTORICAL_PIT_UNIVERSE_NOT_AVAILABLE: identity stream mismatch")
    counts = [item["evaluable_symbol_count"] for item in coverage.values()]
    raw_counts = [item["raw_symbol_count_at_T"] for item in coverage.values()]
    return {
        "status": "PASS",
        "historical_pit_universe": {
            "source": "existing continuous replay universe",
            "sessions": len(signal_dates),
            "first_session": signal_dates[0],
            "last_session": signal_dates[-1],
            "candidate_evaluations": expected,
            "per_session_min": min(counts),
            "per_session_max": max(counts),
            "per_session_mean": float(np.mean(counts)),
            "per_session_median": float(np.median(counts)),
            "raw_t_day_min": min(raw_counts),
            "raw_t_day_max": max(raw_counts),
            "semantics": manifest["universe_semantics"],
            "identity_source_sha256": identity_digest.hexdigest(),
            "identity_stream_sorted": True,
            "listing_handling": "T-day raw row plus >=120 valid bars; no current backfill",
            "missing_history_handling": "symbol-date exclusion; no interpolation or session deletion",
            "board_identity": "Main=00/60; ChiNext=30; STAR=68; other prefixes retained and reported separately",
        },
        "signal_price_basis": {
            "semantics": manifest["adjustment_semantics"],
            "daily_k_sha256": daily_hash,
            "adjustment_factors_sha256": adjustment_hash,
            "known_at_vintage_proof": manifest["provenance"]["known_at_vintage_proof"],
            "future_events_excluded": True,
            "ohlc_fields": ["open", "high", "low", "close"],
            "corporate_action_check": "validated T-anchor affine transform; positive finite OHLC; duplicate-free keys",
        },
        "calendar": {"benchmark_rows": index_meta["row_count"], "benchmark_files": index_meta["files"], "schedule": manifest["signal_date_schedule"], "timezone": "Asia/Shanghai", "window_unit": "completed XSHG signal sessions"},
        "raw_stock_meta": stock_meta,
        "adjustment_event_meta": event_meta,
        "core_output_sha256": core_hash,
        "final_oos_read": False,
        "forbidden_directory_touched": False,
    }


def _date_distribution(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    return _distribution([float(row[field]) for row in rows if row.get(field) is not None and _finite(row[field])])


def _group_concentration(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["symbol"]) for row in rows)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    total = sum(counts.values())
    return {"unique_symbols": len(counts), "top1_share": ordered[0][1] / total if ordered else None, "top5_share": sum(count for _symbol, count in ordered[:5]) / total if total else None, "top10": [{"symbol": symbol, "events": count} for symbol, count in ordered[:10]]}


def _overlap(candidate_pairs: set[tuple[str, str]], memberships: set[tuple[str, str]], source: Mapping[str, Any], label: str) -> dict[str, Any]:
    candidate_dates = {date for date, _symbol in candidate_pairs}
    in_scope = {pair for pair in memberships if pair[0] in candidate_dates}
    exact = len(candidate_pairs & in_scope)
    return {"label": label, "source": dict(source), "same_date_overlap": len(candidate_dates & {date for date, _symbol in in_scope}), "same_symbol_date_overlap": exact, "candidate_share_overlapping_counterpart": exact / len(candidate_pairs) if candidate_pairs else None, "counterpart_share_overlapping_candidate": exact / len(in_scope) if in_scope else None, "counterpart_memberships_in_research_dates": len(in_scope)}


def _shared_bin_dates(rows_by_date: Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]], left_key: str, right_key: str, bin_key: str = "bounce_bin") -> set[str]:
    result: set[str] = set()
    for date, groups in rows_by_date.items():
        left_bins = {row.get(bin_key) for row in groups.get(left_key, []) if row.get(bin_key) is not None}
        right_bins = {row.get(bin_key) for row in groups.get(right_key, []) if row.get(bin_key) is not None}
        if left_bins & right_bins:
            result.add(date)
    return result


def _signal_pass(*, raw_dir: Path, core_manifest_path: Path, core_output_path: Path, b_membership_path: Path | None, rs_membership_path: Path | None, vcb_membership_path: Path | None, signal_path: Path, audit_path: Path) -> dict[str, Any]:
    audit = _input_audit(raw_dir, core_manifest_path, core_output_path)
    index_dates, _index_bars, _index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_position = {date: index for index, date in enumerate(session_dates)}
    signal_dates = [date for date in session_dates if replay.VALIDATION_START <= date <= replay.VALIDATION_END]
    store, _stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")
    memberships = {}
    b_memberships, b_source = _load_membership(b_membership_path, label="B")
    rs_memberships, rs_source = _load_membership(rs_membership_path, label="RS")
    vcb_memberships, vcb_source = _load_membership(vcb_membership_path, label="VCB")
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    content_digest = hashlib.sha256()
    per_date: dict[str, dict[str, Any]] = {}
    signal_rows = 0
    valid_r20_count = 0
    insufficient_history_count = 0
    invalid_signal_input_count = 0
    total_downside_extreme = 0
    total_baseline = 0
    candidate_pairs: set[tuple[str, str]] = set()
    control_pairs: set[tuple[str, str]] = set()
    with signal_path.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0) as compressed:
            for date_index, signal_date in enumerate(signal_dates):
                anchor_ms = index_dates[signal_date]
                eligible_symbols, numeric_bars = replay._numeric_bars_for_date(store, signal_date, anchor_ms, events)
                features: dict[str, dict[str, Any]] = {}
                r20_values: dict[str, float] = {}
                for symbol in sorted(eligible_symbols):
                    closes, volume, highs, lows = numeric_bars[symbol]
                    feature = _feature_from_bars(closes, volume, highs, lows)
                    if feature is None:
                        reason = "INSUFFICIENT_SIGNAL_HISTORY" if len(closes) < MIN_SIGNAL_BARS else "INVALID_SIGNAL_INPUT"
                        features[symbol] = {"eligibility": "EXCLUDED", "exclusion_reason": reason}
                        if reason == "INSUFFICIENT_SIGNAL_HISTORY":
                            insufficient_history_count += 1
                        else:
                            invalid_signal_input_count += 1
                    else:
                        features[symbol] = {"eligibility": "VALID_SIGNAL_INPUT", "exclusion_reason": None, **feature}
                        r20_values[symbol] = feature["r20_pre"]
                ranks = _rank_ascending(r20_values)
                bottom_k = _bottom_k(len(r20_values))
                rows: list[dict[str, Any]] = []
                groups: dict[str, list[dict[str, Any]]] = {"CANDIDATE": [], "PRIMARY_CONTROL": [], "FULL_DOWNSIDE_BOUNCE": [], "GENERIC_RECLAIM": [], "GENERIC_BOUNCE_CONTROL": []}
                for symbol in sorted(eligible_symbols):
                    feature = features[symbol]
                    valid = feature["eligibility"] == "VALID_SIGNAL_INPUT"
                    r20 = feature.get("r20_pre")
                    downside = bool(valid and ranks.get(symbol, 0) <= bottom_k and float(r20) < 0)
                    simple_bounce = bool(valid and _simple_positive_bounce(feature["close_t"], feature["close_t_minus_1"]))
                    reclaim5 = bool(valid and _reclaim5(feature["close_t"], feature["prior_close_high5"]))
                    candidate, control, baseline = _classify(downside, simple_bounce, reclaim5)
                    non_downside = bool(valid and not downside)
                    generic_reclaim = bool(non_downside and reclaim5)
                    generic_control = bool(non_downside and simple_bounce and not reclaim5)
                    row = {
                        "date": signal_date,
                        "symbol": symbol,
                        "board": _board(symbol),
                        "earliest_execution_date": session_dates[session_position[signal_date] + 1] if session_position[signal_date] + 1 < len(session_dates) else None,
                        "eligibility": feature["eligibility"],
                        "exclusion_reason": feature["exclusion_reason"],
                        "r20_pre": r20,
                        "r20_pre_rank": ranks.get(symbol),
                        "bottom_k": bottom_k if valid else None,
                        "downside_extreme": downside,
                        "prior_close_high5": feature.get("prior_close_high5"),
                        "close_t_minus_1": feature.get("close_t_minus_1"),
                        "close_t": feature.get("close_t"),
                        "t_day_return": feature.get("t_day_return"),
                        "simple_positive_bounce": simple_bounce,
                        "reclaim5": reclaim5,
                        "reclaim_margin": feature.get("reclaim_margin"),
                        "candidate": candidate,
                        "primary_control": control,
                        "downside_bounce_baseline": baseline,
                        "non_downside": non_downside,
                        "non_downside_generic_reclaim": generic_reclaim,
                        "non_downside_generic_control": generic_control,
                        "bounce_bin": None,
                        "non_downside_bounce_bin": None,
                        "invalidation_reference": feature.get("invalidation_reference"),
                        "prior_realized_volatility20_pct": feature.get("prior_realized_volatility20_pct"),
                        "median_traded_amount20": feature.get("median_traded_amount20"),
                    }
                    rows.append(row)
                    if baseline:
                        groups["FULL_DOWNSIDE_BOUNCE"].append(row)
                    if candidate:
                        groups["CANDIDATE"].append(row)
                        candidate_pairs.add((signal_date, symbol))
                    if control:
                        groups["PRIMARY_CONTROL"].append(row)
                        control_pairs.add((signal_date, symbol))
                    if generic_reclaim:
                        groups["GENERIC_RECLAIM"].append(row)
                    if generic_control:
                        groups["GENERIC_BOUNCE_CONTROL"].append(row)
                baseline_rows = sorted(groups["FULL_DOWNSIDE_BOUNCE"], key=lambda row: (float(row["t_day_return"]), row["symbol"]))
                for rank, row in enumerate(baseline_rows, start=1):
                    row["bounce_bin"] = _bounce_bin(rank, len(baseline_rows))
                generic_baseline = sorted([row for row in rows if row["non_downside"] and row["simple_positive_bounce"]], key=lambda row: (float(row["t_day_return"]), row["symbol"]))
                for rank, row in enumerate(generic_baseline, start=1):
                    row["non_downside_bounce_bin"] = _bounce_bin(rank, len(generic_baseline))
                for row in rows:
                    line = (canonical_json(row) + "\n").encode("utf-8")
                    compressed.write(line)
                    content_digest.update(line)
                    signal_rows += 1
                valid_r20_count += len(r20_values)
                total_downside_extreme += sum(int(row["downside_extreme"]) for row in rows)
                total_baseline += len(baseline_rows)
                per_date[signal_date] = {
                    "signal_date": signal_date,
                    "eligible_n": len(eligible_symbols),
                    "valid_r20_pre_n": len(r20_values),
                    "insufficient_history_n": sum(int(item["exclusion_reason"] == "INSUFFICIENT_SIGNAL_HISTORY") for item in features.values()),
                    "invalid_signal_input_n": sum(int(item["exclusion_reason"] == "INVALID_SIGNAL_INPUT") for item in features.values()),
                    "downside_extreme_n": sum(int(row["downside_extreme"]) for row in rows),
                    "downside_bounce_baseline_n": len(baseline_rows),
                    "candidate_n": len(groups["CANDIDATE"]),
                    "primary_control_n": len(groups["PRIMARY_CONTROL"]),
                    "generic_reclaim_n": len(groups["GENERIC_RECLAIM"]),
                    "generic_control_n": len(groups["GENERIC_BOUNCE_CONTROL"]),
                    "candidate_rows": groups["CANDIDATE"],
                    "control_rows": groups["PRIMARY_CONTROL"],
                    "baseline_rows": baseline_rows,
                    "generic_reclaim_rows": groups["GENERIC_RECLAIM"],
                    "generic_control_rows": groups["GENERIC_BOUNCE_CONTROL"],
                }
                if date_index % 100 == 0:
                    print(f"signal pass {date_index + 1}/{len(signal_dates)} {signal_date}", flush=True)
    candidate_dates = {date for date, _symbol in candidate_pairs}
    control_dates = {date for date, _symbol in control_pairs}
    rows_by_date = {date: {key: values for key, values in (("CANDIDATE", item["candidate_rows"]), ("PRIMARY_CONTROL", item["control_rows"]), ("GENERIC_RECLAIM", item["generic_reclaim_rows"]), ("GENERIC_BOUNCE_CONTROL", item["generic_control_rows"]))} for date, item in per_date.items()}
    shared_downside_dates = _shared_bin_dates(rows_by_date, "CANDIDATE", "PRIMARY_CONTROL")
    generic_rows_by_date = {date: {"GENERIC_RECLAIM": values["GENERIC_RECLAIM"], "GENERIC_BOUNCE_CONTROL": values["GENERIC_BOUNCE_CONTROL"]} for date, values in rows_by_date.items()}
    shared_generic_dates = _shared_bin_dates(generic_rows_by_date, "GENERIC_RECLAIM", "GENERIC_BOUNCE_CONTROL", "non_downside_bounce_bin")
    grouped_rows = {
        "CANDIDATE": [row for item in per_date.values() for row in item["candidate_rows"]],
        "PRIMARY_CONTROL": [row for item in per_date.values() for row in item["control_rows"]],
        "FULL_DOWNSIDE_BOUNCE": [row for item in per_date.values() for row in item["baseline_rows"]],
        "GENERIC_RECLAIM": [row for item in per_date.values() for row in item["generic_reclaim_rows"]],
        "GENERIC_BOUNCE_CONTROL": [row for item in per_date.values() for row in item["generic_control_rows"]],
    }
    year_counts = {group: dict(sorted(Counter(row["date"][:4] for row in rows).items())) for group, rows in grouped_rows.items()}
    board_counts = {group: dict(sorted(Counter(row["board"] for row in rows).items())) for group, rows in grouped_rows.items()}
    signal_only = {
        "sessions": len(per_date),
        "first_session": min(per_date),
        "last_session": max(per_date),
        "eligible_symbol_dates": signal_rows,
        "valid_r20_pre_count": valid_r20_count,
        "insufficient_history_count": insufficient_history_count,
        "invalid_signal_input_count": invalid_signal_input_count,
        "downside_extreme_count": total_downside_extreme,
        "downside_bounce_baseline_count": total_baseline,
        "candidate_count": len(candidate_pairs),
        "primary_control_count": len(control_pairs),
        "generic_reclaim_count": len(grouped_rows["GENERIC_RECLAIM"]),
        "generic_control_count": len(grouped_rows["GENERIC_BOUNCE_CONTROL"]),
        "candidate_active_dates": len(candidate_dates),
        "control_active_dates": len(control_dates),
        "dates_both_groups_present": len(candidate_dates & control_dates),
        "shared_bounce_bin_dates": len(shared_downside_dates),
        "generic_shared_bounce_bin_dates": len(shared_generic_dates),
        "mean_candidate_n_per_date": float(np.mean([item["candidate_n"] for item in per_date.values()])),
        "median_candidate_n_per_date": float(np.median([item["candidate_n"] for item in per_date.values()])),
        "mean_control_n_per_date": float(np.mean([item["primary_control_n"] for item in per_date.values()])),
        "median_control_n_per_date": float(np.median([item["primary_control_n"] for item in per_date.values()])),
        "unique_candidate_symbols": len({row["symbol"] for row in grouped_rows["CANDIDATE"]}),
        "unique_control_symbols": len({row["symbol"] for row in grouped_rows["PRIMARY_CONTROL"]}),
        "year_counts": year_counts,
        "board_counts": board_counts,
        "concentration": {group: _group_concentration(rows) for group, rows in grouped_rows.items()},
        "reclaim_margin_distribution": {group: _date_distribution(rows, "reclaim_margin") for group, rows in grouped_rows.items() if group in ("CANDIDATE", "PRIMARY_CONTROL", "FULL_DOWNSIDE_BOUNCE")},
        "t_day_return_distribution_before_stratification": {group: _date_distribution(rows, "t_day_return") for group, rows in grouped_rows.items() if group in ("CANDIDATE", "PRIMARY_CONTROL", "FULL_DOWNSIDE_BOUNCE", "GENERIC_RECLAIM", "GENERIC_BOUNCE_CONTROL")},
        "prior_r20_distribution": {group: _date_distribution(rows, "r20_pre") for group, rows in grouped_rows.items() if group in ("CANDIDATE", "PRIMARY_CONTROL", "FULL_DOWNSIDE_BOUNCE")},
        "prior_realized_volatility_distribution": {group: _date_distribution(rows, "prior_realized_volatility20_pct") for group, rows in grouped_rows.items()},
        "traded_amount_distribution": {group: _date_distribution(rows, "median_traded_amount20") for group, rows in grouped_rows.items()},
        "sample_gate": {
            "candidate_events_min": 500,
            "primary_control_events_min": 1000,
            "both_group_active_dates_min": 200,
            "shared_bounce_bin_dates_min": 200,
            "status": "PASS" if len(candidate_pairs) >= 500 and len(control_pairs) >= 1000 and len(candidate_dates & control_dates) >= 200 and len(shared_downside_dates) >= 200 else "CRSR_SIGNAL_CONSTRUCTION_NOT_RESEARCH_READY",
        },
    }
    if signal_only["sample_gate"]["status"] != "PASS":
        raise RuntimeError(signal_only["sample_gate"]["status"])
    signal_artifact = {"logical_path": "local-only/new_controlled_right_side_reversal_v1_signal_membership.jsonl.gz", "rows": signal_rows, "bytes": signal_path.stat().st_size, "file_sha256": file_sha256(signal_path), "content_sha256": content_digest.hexdigest(), "sort": "date ascending, symbol ascending"}
    overlap = {
        "B": _overlap(candidate_pairs, b_memberships, b_source, "B"),
        "RS": _overlap(candidate_pairs, rs_memberships, rs_source, "RS"),
        "VCB": _overlap(candidate_pairs, vcb_memberships, vcb_source, "VCB"),
    }
    signal_summary = {"schema_version": SIGNAL_SCHEMA, "strategy": STRATEGY_VERSION, "protocol_commit_sha": PROTOCOL_COMMIT, "input_audit": audit, "signal_only": signal_only, "signal_artifact": signal_artifact, "signal_overlap": overlap, "final_oos_read": False, "forbidden_directory_touched": False}
    write_json(audit_path, signal_summary)
    return {"audit": audit, "per_date": per_date, "signal_only": signal_only, "signal_artifact": signal_artifact, "signal_overlap": overlap, "signal_summary": signal_summary}


def _reuse_signal_pass(signal_path: Path, audit_path: Path) -> dict[str, Any]:
    signal_summary = json.loads(audit_path.read_text(encoding="utf-8"))
    artifact = signal_summary["signal_artifact"]
    actual = _jsonl_gzip_identity(signal_path)
    if actual != {key: artifact[key] for key in ("rows", "bytes", "file_sha256", "content_sha256")}:
        raise RuntimeError("CRSR_SIGNAL_ARTIFACT_IDENTITY_MISMATCH")
    per_date: dict[str, dict[str, Any]] = {}
    with gzip.open(signal_path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            row = json.loads(line)
            if not any(row.get(key) for key in ("candidate", "primary_control", "non_downside_generic_reclaim", "non_downside_generic_control")):
                continue
            date = row["date"]
            entry = per_date.setdefault(date, {"signal_date": date, "candidate_rows": [], "control_rows": [], "baseline_rows": [], "generic_reclaim_rows": [], "generic_control_rows": []})
            if row.get("candidate"):
                entry["candidate_rows"].append(row)
                entry["baseline_rows"].append(row)
            elif row.get("primary_control"):
                entry["control_rows"].append(row)
                entry["baseline_rows"].append(row)
            if row.get("non_downside_generic_reclaim"):
                entry["generic_reclaim_rows"].append(row)
            if row.get("non_downside_generic_control"):
                entry["generic_control_rows"].append(row)
    return {"audit": signal_summary["input_audit"], "per_date": per_date, "signal_only": signal_summary["signal_only"], "signal_artifact": artifact, "signal_overlap": signal_summary["signal_overlap"], "signal_summary": signal_summary}


def _outcome_record(row: Mapping[str, Any], store: dict[str, Any], events: dict[str, list[tuple[int, float, float, float, float]]], session_dates: list[str], session_ms: np.ndarray, session_index: dict[str, int]) -> dict[str, Any]:
    record = returns_v2._build_event_record(row={"as_of_date": row["date"], "signal_date": row["date"], "earliest_execution_date": row["earliest_execution_date"], "symbol": row["symbol"], "setup_id": STRATEGY_VERSION}, store=store, events=events, session_dates=session_dates, session_ms=session_ms, session_index=session_index)
    record["reference_execution"] = "T+1 XSHG open"
    record["reference_execution_not_actual_fill"] = True
    return record


def _available_return(row_outcome: Mapping[str, Any], horizon: str) -> float | None:
    value = row_outcome["outcomes"][horizon]
    return float(value["return_pct"]) if value["status"] == "AVAILABLE" else None


def _stratified_spread(groups: Mapping[str, Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]], left: str, right: str, horizon: str, bin_key: str = "bounce_bin") -> dict[str, Any]:
    by_bin: dict[int, dict[str, list[float]]] = defaultdict(lambda: {"left": [], "right": []})
    for row, outcome in groups.get(left, []):
        value = _available_return(outcome, horizon)
        if value is not None and row.get(bin_key) is not None:
            by_bin[int(row[bin_key])]["left"].append(value)
    for row, outcome in groups.get(right, []):
        value = _available_return(outcome, horizon)
        if value is not None and row.get(bin_key) is not None:
            by_bin[int(row[bin_key])]["right"].append(value)
    bins: dict[str, Any] = {}
    spreads: list[float] = []
    for bin_number in sorted(by_bin):
        values = by_bin[bin_number]
        if values["left"] and values["right"]:
            left_mean = float(np.mean(values["left"]))
            right_mean = float(np.mean(values["right"]))
            spread = left_mean - right_mean
            spreads.append(spread)
            bins[str(bin_number)] = {"left_n": len(values["left"]), "right_n": len(values["right"]), "left_mean": left_mean, "right_mean": right_mean, "spread": spread}
    return {"spread": float(np.mean(spreads)) if spreads else None, "valid_shared_bins": len(spreads), "bins": bins}


def _raw_spread(groups: Mapping[str, Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]], left: str, right: str, horizon: str) -> dict[str, Any]:
    left_values = [value for row, outcome in groups.get(left, []) if (value := _available_return(outcome, horizon)) is not None]
    right_values = [value for row, outcome in groups.get(right, []) if (value := _available_return(outcome, horizon)) is not None]
    left_mean = float(np.mean(left_values)) if left_values else None
    right_mean = float(np.mean(right_values)) if right_values else None
    return {"left_n": len(left_values), "right_n": len(right_values), "left_mean": left_mean, "right_mean": right_mean, "spread": left_mean - right_mean if left_mean is not None and right_mean is not None else None}


def _update_board_state(board_states: dict[str, dict[str, dict[str, dict[str, Any]]]], board: str, group: str, outcome_record: Mapping[str, Any]) -> None:
    for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON):
        _update_state(board_states[board][group][horizon], outcome_record, horizon)


def _cooldown_retain(events: Sequence[tuple[str, str, str]], session_index: Mapping[str, int], cooldown_sessions: int = 10) -> list[tuple[str, str, str]]:
    retained: list[tuple[str, str, str]] = []
    last_by_symbol: dict[str, int] = {}
    for date, symbol, classification in sorted(events, key=lambda item: (item[0], item[1])):
        index = session_index[date]
        last = last_by_symbol.get(symbol)
        if last is None or index - last > cooldown_sessions:
            retained.append((date, symbol, classification))
            last_by_symbol[symbol] = index
    return retained


def _year_summary(daily_rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for year in ("2023", "2024", "2025", "2026"):
        values = [float(row[field]) for row in daily_rows if str(row["date"]).startswith(year) and row.get(field) is not None]
        result[year] = {"dates": len(values), "mean_spread": float(np.mean(values)) if values else None, "median_spread": float(np.median(values)) if values else None, "positive_date_rate": float(np.mean(np.asarray(values) > 0)) if values else None, "sign_positive": bool(np.mean(values) > 0) if values else None}
    return result


def _monthly_concentration(daily_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter()
    for row in daily_rows:
        if row.get("primary_stratified_10D") is not None:
            counts[str(row["date"])[:7]] += 1
    return {month: {"valid_primary_dates": count} for month, count in sorted(counts.items())}


def _process_outcomes(*, signal: dict[str, Any], raw_dir: Path, outcome_path: Path) -> dict[str, Any]:
    index_dates, _index_bars, _index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.asarray([index_dates[date] for date in session_dates], dtype=np.int64)
    session_index = {date: index for index, date in enumerate(session_dates)}
    store, _stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")
    state_groups = ("CANDIDATE", "PRIMARY_CONTROL", "FULL_DOWNSIDE_BOUNCE", "GENERIC_RECLAIM", "GENERIC_BOUNCE_CONTROL")
    states = {group: {horizon: _new_state() for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for group in state_groups}
    board_states = {board: {group: {horizon: _new_state() for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for group in state_groups} for board in BOARDS}
    daily_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    primary_outcome_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    continuous_rows: list[dict[str, Any]] = []
    raw_events: list[tuple[str, str, str]] = []
    for date in sorted(signal["per_date"]):
        item = signal["per_date"][date]
        grouped_rows = {"CANDIDATE": item["candidate_rows"], "PRIMARY_CONTROL": item["control_rows"], "FULL_DOWNSIDE_BOUNCE": item["baseline_rows"], "GENERIC_RECLAIM": item["generic_reclaim_rows"], "GENERIC_BOUNCE_CONTROL": item["generic_control_rows"]}
        grouped_outcomes: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {group: [] for group in state_groups}
        seen_pairs: set[tuple[str, str]] = set()
        for group in ("CANDIDATE", "PRIMARY_CONTROL", "GENERIC_RECLAIM", "GENERIC_BOUNCE_CONTROL"):
            for row in grouped_rows[group]:
                pair = (date, row["symbol"])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                outcome = _outcome_record(row, store, events, session_dates, session_ms, session_index)
                primary_outcome_by_pair[pair] = outcome
                detail_rows.append({"signal": row, "outcome": outcome})
                grouped_outcomes[group].append((row, outcome))
                _update_board_state(board_states, row["board"], group, outcome)
                for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON):
                    _update_state(states[group][horizon], outcome, horizon)
                if group in ("CANDIDATE", "PRIMARY_CONTROL"):
                    grouped_outcomes["FULL_DOWNSIDE_BOUNCE"].append((row, outcome))
                    _update_state(states["FULL_DOWNSIDE_BOUNCE"][SECONDARY_HORIZON], outcome, SECONDARY_HORIZON)
                    _update_state(states["FULL_DOWNSIDE_BOUNCE"][PRIMARY_HORIZON], outcome, PRIMARY_HORIZON)
                    _update_board_state(board_states, row["board"], "FULL_DOWNSIDE_BOUNCE", outcome)
                    if group == "CANDIDATE":
                        raw_events.append((date, row["symbol"], "CANDIDATE"))
                    else:
                        raw_events.append((date, row["symbol"], "PRIMARY_CONTROL"))
        downside_10 = _stratified_spread(grouped_outcomes, "CANDIDATE", "PRIMARY_CONTROL", PRIMARY_HORIZON)
        downside_5 = _stratified_spread(grouped_outcomes, "CANDIDATE", "PRIMARY_CONTROL", SECONDARY_HORIZON)
        generic_10 = _stratified_spread(grouped_outcomes, "GENERIC_RECLAIM", "GENERIC_BOUNCE_CONTROL", PRIMARY_HORIZON, "non_downside_bounce_bin")
        generic_5 = _stratified_spread(grouped_outcomes, "GENERIC_RECLAIM", "GENERIC_BOUNCE_CONTROL", SECONDARY_HORIZON, "non_downside_bounce_bin")
        raw_10 = _raw_spread(grouped_outcomes, "CANDIDATE", "PRIMARY_CONTROL", PRIMARY_HORIZON)
        raw_5 = _raw_spread(grouped_outcomes, "CANDIDATE", "PRIMARY_CONTROL", SECONDARY_HORIZON)
        baseline_10 = _summary_stats([value for row, outcome in grouped_outcomes["FULL_DOWNSIDE_BOUNCE"] if (value := _available_return(outcome, PRIMARY_HORIZON)) is not None])
        baseline_5 = _summary_stats([value for row, outcome in grouped_outcomes["FULL_DOWNSIDE_BOUNCE"] if (value := _available_return(outcome, SECONDARY_HORIZON)) is not None])
        rho_rows = [(float(row["reclaim_margin"]), float(value)) for row, outcome in grouped_outcomes["FULL_DOWNSIDE_BOUNCE"] if (value := _available_return(outcome, PRIMARY_HORIZON)) is not None]
        rho = spearman([item[0] for item in rho_rows], [item[1] for item in rho_rows]) if len(rho_rows) >= 5 else None
        if rho is not None:
            continuous_rows.append({"date": date, "rho": rho, "n": len(rho_rows)})
        interaction = downside_10["spread"] - generic_10["spread"] if downside_10["spread"] is not None and generic_10["spread"] is not None else None
        daily_rows.append({
            "date": date,
            "candidate_n": item["candidate_n"],
            "control_n": item["primary_control_n"],
            "baseline_n": item["downside_bounce_baseline_n"],
            "generic_reclaim_n": item["generic_reclaim_n"],
            "generic_control_n": item["generic_control_n"],
            "raw_candidate_10D": raw_10["left_mean"],
            "raw_control_10D": raw_10["right_mean"],
            "raw_spread_10D": raw_10["spread"],
            "raw_candidate_5D": raw_5["left_mean"],
            "raw_control_5D": raw_5["right_mean"],
            "raw_spread_5D": raw_5["spread"],
            "full_downside_bounce_10D": baseline_10["mean"],
            "full_downside_bounce_5D": baseline_5["mean"],
            "primary_stratified_10D": downside_10["spread"],
            "primary_stratified_5D": downside_5["spread"],
            "primary_shared_bins_10D": downside_10["valid_shared_bins"],
            "generic_reclaim_stratified_10D": generic_10["spread"],
            "generic_reclaim_stratified_5D": generic_5["spread"],
            "generic_shared_bins_10D": generic_10["valid_shared_bins"],
            "context_interaction_10D": interaction,
            "continuous_reclaim_margin_rho_10D": rho,
        })
    outcome_artifact = _write_jsonl_gzip(outcome_path, detail_rows)
    primary_spreads = [float(row["primary_stratified_10D"]) for row in daily_rows if row["primary_stratified_10D"] is not None]
    primary_5d = [float(row["primary_stratified_5D"]) for row in daily_rows if row["primary_stratified_5D"] is not None]
    generic_spreads = [float(row["generic_reclaim_stratified_10D"]) for row in daily_rows if row["generic_reclaim_stratified_10D"] is not None]
    interactions = [float(row["context_interaction_10D"]) for row in daily_rows if row["context_interaction_10D"] is not None]
    primary_ci = list(_moving_block_bootstrap_ci(primary_spreads)) if len(primary_spreads) >= BOOTSTRAP_BLOCK_LENGTH else [None, None]
    primary_5d_ci = list(_moving_block_bootstrap_ci(primary_5d)) if len(primary_5d) >= BOOTSTRAP_BLOCK_LENGTH else [None, None]
    generic_ci = list(_moving_block_bootstrap_ci(generic_spreads)) if len(generic_spreads) >= BOOTSTRAP_BLOCK_LENGTH else [None, None]
    interaction_ci = list(_moving_block_bootstrap_ci(interactions)) if len(interactions) >= BOOTSTRAP_BLOCK_LENGTH else [None, None]
    continuous_values = [float(row["rho"]) for row in continuous_rows]
    shared_signal_dates = set(date for date, item in signal["per_date"].items() if _shared_bin_dates({date: {"CANDIDATE": item["candidate_rows"], "PRIMARY_CONTROL": item["control_rows"]}}, "CANDIDATE", "PRIMARY_CONTROL"))
    coverage = {
        group: {horizon: _summary_stats(states[group][horizon]["returns"], states[group][horizon]) for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)}
        for group in state_groups
    }
    candidate_10_coverage = coverage["CANDIDATE"][PRIMARY_HORIZON]["n"] / states["CANDIDATE"][PRIMARY_HORIZON]["event_count"] if states["CANDIDATE"][PRIMARY_HORIZON]["event_count"] else 0.0
    control_10_coverage = coverage["PRIMARY_CONTROL"][PRIMARY_HORIZON]["n"] / states["PRIMARY_CONTROL"][PRIMARY_HORIZON]["event_count"] if states["PRIMARY_CONTROL"][PRIMARY_HORIZON]["event_count"] else 0.0
    shared_date_coverage = len(primary_spreads) / len(shared_signal_dates) if shared_signal_dates else 0.0
    coverage_gate = {"candidate_usable_10D_coverage": candidate_10_coverage, "primary_control_usable_10D_coverage": control_10_coverage, "shared_bounce_bin_10D_date_coverage": shared_date_coverage, "minimum_core_event_coverage": 0.95, "status": "PASS" if candidate_10_coverage >= 0.95 and control_10_coverage >= 0.95 else "CRSR_OUTCOME_COVERAGE_NOT_RESEARCH_READY"}
    if coverage_gate["status"] != "PASS":
        raise RuntimeError(coverage_gate["status"])
    years = _year_summary(daily_rows, "primary_stratified_10D")
    board_diagnostics = {board: {group: {horizon: _summary_stats(board_states[board][group][horizon]["returns"], board_states[board][group][horizon]) for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for group in state_groups} for board in BOARDS}
    cooldown_retained = _cooldown_retain(raw_events, session_index, cooldown_sessions=10)
    cooldown_rows: dict[str, dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]]] = defaultdict(lambda: {"CANDIDATE": [], "PRIMARY_CONTROL": []})
    for date, symbol, group in cooldown_retained:
        row_outcome = primary_outcome_by_pair[(date, symbol)]
        row = next(row for row in (signal["per_date"][date]["candidate_rows"] + signal["per_date"][date]["control_rows"]) if row["symbol"] == symbol)
        cooldown_rows[date][group].append((row, row_outcome))
    cooldown_daily = []
    for date in sorted(cooldown_rows):
        spread = _stratified_spread(cooldown_rows, "CANDIDATE", "PRIMARY_CONTROL", PRIMARY_HORIZON)
        if spread["spread"] is not None:
            cooldown_daily.append(float(spread["spread"]))
    cooldown_ci = list(_moving_block_bootstrap_ci(cooldown_daily)) if len(cooldown_daily) >= BOOTSTRAP_BLOCK_LENGTH else [None, None]
    cooldown = {"cooldown_sessions": 10, "raw_event_counts": {"candidate": sum(group == "CANDIDATE" for _date, _symbol, group in raw_events), "control": sum(group == "PRIMARY_CONTROL" for _date, _symbol, group in raw_events)}, "retained_event_counts": {"candidate": sum(group == "CANDIDATE" for _date, _symbol, group in cooldown_retained), "control": sum(group == "PRIMARY_CONTROL" for _date, _symbol, group in cooldown_retained)}, "valid_dates": len(cooldown_daily), "mean_spread_10D": float(np.mean(cooldown_daily)) if cooldown_daily else None, "median_spread_10D": float(np.median(cooldown_daily)) if cooldown_daily else None, "positive_date_rate": float(np.mean(np.asarray(cooldown_daily) > 0)) if cooldown_daily else None, "moving_block_bootstrap_ci_95": cooldown_ci}
    raw_event_rows = {group: [row for date in signal["per_date"].values() for row in date["candidate_rows" if group == "CANDIDATE" else "control_rows"]] for group in ("CANDIDATE", "PRIMARY_CONTROL")}
    support = (
        bool(primary_spreads)
        and float(np.mean(primary_spreads)) > 0
        and primary_ci[0] is not None and primary_ci[0] > 0
        and bool(continuous_values) and float(np.mean(continuous_values)) > 0
        and bool(cooldown_daily) and float(np.mean(cooldown_daily)) >= 0
        and bool(interactions) and float(np.mean(interactions)) >= 0
        and sum(bool(years[year]["sign_positive"]) for year in years) >= 3
        and coverage_gate["status"] == "PASS"
    )
    primary_mean = float(np.mean(primary_spreads)) if primary_spreads else None
    continuous_mean = float(np.mean(continuous_values)) if continuous_values else None
    if primary_ci[1] is not None and primary_ci[1] <= 0:
        decision = "CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL"
    elif primary_mean is not None and primary_mean <= 0 and continuous_mean is not None and continuous_mean <= 0:
        decision = "CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL"
    elif support:
        decision = "CONTROLLED_RIGHT_SIDE_REVERSAL_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION"
    else:
        decision = "CONTROLLED_RIGHT_SIDE_REVERSAL_NEEDS_MORE_EVIDENCE"
    outcome_maturity = {"primary_horizon": PRIMARY_HORIZON, "last_signal_date_with_mature_10D": session_dates[-PRIMARY_HORIZON_INT - 1] if len(session_dates) > PRIMARY_HORIZON_INT else None, "mature_signal_date_count": max(0, len(session_dates) - PRIMARY_HORIZON_INT), "censored_signal_dates_after_maturity": PRIMARY_HORIZON_INT}
    return {
        "outcome_artifact": outcome_artifact,
        "primary": {"mean_stratified_spread_10D": primary_mean, "median_stratified_spread_10D": float(np.median(primary_spreads)) if primary_spreads else None, "moving_block_bootstrap_ci_95": primary_ci, "positive_spread_date_rate_10D": float(np.mean(np.asarray(primary_spreads) > 0)) if primary_spreads else None, "valid_date_count": len(primary_spreads), "signal_shared_bounce_bin_date_count": len(shared_signal_dates), "shared_bounce_bin_10D_date_coverage": shared_date_coverage},
        "raw_secondary": {"candidate_10D": _summary_stats([value for row in daily_rows if (value := row.get("raw_candidate_10D")) is not None]), "full_downside_bounce_10D": _summary_stats([value for row in daily_rows if (value := row.get("full_downside_bounce_10D")) is not None]), "primary_control_10D": _summary_stats([value for row in daily_rows if (value := row.get("raw_control_10D")) is not None]), "raw_spread_10D_mean": float(np.mean([row["raw_spread_10D"] for row in daily_rows if row["raw_spread_10D"] is not None])) if any(row["raw_spread_10D"] is not None for row in daily_rows) else None},
        "secondary_5D": {"mean_stratified_spread_5D": float(np.mean(primary_5d)) if primary_5d else None, "median_stratified_spread_5D": float(np.median(primary_5d)) if primary_5d else None, "moving_block_bootstrap_ci_95": primary_5d_ci, "positive_spread_date_rate_5D": float(np.mean(np.asarray(primary_5d) > 0)) if primary_5d else None, "valid_date_count": len(primary_5d)},
        "continuous": {"mean_daily_rho": continuous_mean, "median_daily_rho": float(np.median(continuous_values)) if continuous_values else None, "positive_rho_date_rate": float(np.mean(np.asarray(continuous_values) > 0)) if continuous_values else None, "valid_rho_dates": len(continuous_values)},
        "context_interaction": {"mean_interaction_10D": float(np.mean(interactions)) if interactions else None, "median_interaction_10D": float(np.median(interactions)) if interactions else None, "moving_block_bootstrap_ci_95": interaction_ci, "positive_interaction_date_rate": float(np.mean(np.asarray(interactions) > 0)) if interactions else None, "valid_date_count": len(interactions), "generic_reclaim_mean_spread_10D": float(np.mean(generic_spreads)) if generic_spreads else None, "generic_reclaim_median_spread_10D": float(np.median(generic_spreads)) if generic_spreads else None, "generic_reclaim_ci_95": generic_ci},
        "daily_rows": daily_rows,
        "continuous_rows": continuous_rows,
        "execution_coverage": coverage,
        "coverage_gate": coverage_gate,
        "outcome_maturity": outcome_maturity,
        "year_diagnostics": years,
        "board_diagnostics": board_diagnostics,
        "symbol_concentration": {group: _group_concentration(rows) for group, rows in raw_event_rows.items()},
        "monthly_concentration": _monthly_concentration(daily_rows),
        "cooldown": cooldown,
        "candidate_control_prior_distributions": {group: {field: _date_distribution(rows, field) for field in ("r20_pre", "prior_realized_volatility20_pct", "median_traded_amount20")} for group, rows in raw_event_rows.items()},
        "post_stratification_t_day_return_balance": {"definition": "absolute candidate-control mean T-day-return difference within shared bounce bins, signal-only", "available_dates": len(shared_signal_dates), "note": "outcome-blind diagnostic"},
        "decision": decision,
    }


PRIMARY_HORIZON_INT = 10


def _render_report(summary: Mapping[str, Any]) -> str:
    primary = summary["primary"]
    continuous = summary["continuous"]
    interaction = summary["context_interaction"]
    signal = summary["signal_only"]
    lines = [
        "# NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1 — research report",
        "",
        f"Decision: `{summary['decision']}`",
        "",
        "This is DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DATE_ANCHORED / DIAGNOSTIC_ONLY evidence for a NEW_RESEARCH_HYPOTHESIS. It is not old D reconstruction, production, a frozen candidate, causal mechanism evidence, or Final OOS.",
        "",
        "## Fixed identity",
        "",
        f"- Base: `{summary['base']}`; protocol commit: `{summary['protocol']['commit_sha']}`.",
        f"- Input audit: `{summary['input_audit']['status']}`; sessions={signal['sessions']} ({signal['first_session']} to {signal['last_session']}); universe identities={signal['eligible_symbol_dates']}.",
        f"- Downside-extreme={signal['downside_extreme_count']}; full downside-bounce baseline={signal['downside_bounce_baseline_count']}; candidate={signal['candidate_count']}; primary control={signal['primary_control_count']}.",
        "- Fixed state: T-1-only 20-session return, same-date bottom 20% rank with symbol tie-break and absolute negative filter; strict close above prior five-session close high; no volume/turnover/RSI/MACD/MA qualification.",
        "",
        "## Primary identification",
        "",
        f"- 10D bounce-magnitude-stratified candidate minus primary-control spread: {primary['mean_stratified_spread_10D']} percentage points.",
        f"- Median date spread: {primary['median_stratified_spread_10D']}; 95% 20-session moving-block-bootstrap CI: {primary['moving_block_bootstrap_ci_95']}.",
        f"- Positive-spread date rate: {primary['positive_spread_date_rate_10D']}; valid dates={primary['valid_date_count']}; shared-bin date coverage={primary['shared_bounce_bin_10D_date_coverage']}.",
        f"- Raw unstratified 10D spread mean: {summary['raw_secondary']['raw_spread_10D_mean']} percentage points.",
        f"- Full downside-bounce baseline 10D event summary: {json.dumps(summary['execution_coverage']['FULL_DOWNSIDE_BOUNCE']['10D'], ensure_ascii=False, sort_keys=True)}.",
        "",
        "## Secondary and robustness",
        "",
        f"- 5D stratified spread: {summary['secondary_5D']['mean_stratified_spread_5D']} percentage points; CI={summary['secondary_5D']['moving_block_bootstrap_ci_95']}.",
        f"- Continuous reclaim-margin rho: mean={continuous['mean_daily_rho']}, median={continuous['median_daily_rho']}, positive-rho rate={continuous['positive_rho_date_rate']}, valid dates={continuous['valid_rho_dates']}.",
        f"- Non-downside generic reclaim spread: {interaction['generic_reclaim_mean_spread_10D']}; context interaction mean={interaction['mean_interaction_10D']}, CI={interaction['moving_block_bootstrap_ci_95']}.",
        f"- Ten-session cooldown: mean={summary['cooldown']['mean_spread_10D']}, median={summary['cooldown']['median_spread_10D']}, CI={summary['cooldown']['moving_block_bootstrap_ci_95']}.",
        f"- Year diagnostics: {json.dumps(summary['year_diagnostics'], ensure_ascii=False, sort_keys=True)}",
        f"- Board diagnostics: {json.dumps(summary['board_diagnostics'], ensure_ascii=False, sort_keys=True)}",
        f"- T-day return balance before stratification: {json.dumps(signal['t_day_return_distribution_before_stratification'], ensure_ascii=False, sort_keys=True)}",
        "",
        "## Coverage and unresolved explanations",
        "",
        f"- Coverage gate: {json.dumps(summary['coverage_gate'], ensure_ascii=False, sort_keys=True)}; execution/reference coverage: {json.dumps(summary['execution_coverage'], ensure_ascii=False, sort_keys=True)}.",
        "- Reference entry is T+1 XSHG open and `REFERENCE_EXECUTION_NOT_ACTUAL_FILL`; returns are gross because `TRANSACTION_COST_MODEL_NOT_PREEXISTING`.",
        "- Limit-state classification: `LIMIT_STATE_EXECUTION_CLASSIFICATION_NOT_AVAILABLE` unless an existing authoritative classifier is added in a new protocol.",
        "- Size and historical sector: `UNRESOLVED_ALTERNATIVE_EXPLANATION / NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION`.",
        f"- B/RS/VCB membership-only overlap: {json.dumps(summary['signal_overlap'], ensure_ascii=False, sort_keys=True)}.",
        f"- Symbol concentration: {json.dumps(summary['symbol_concentration'], ensure_ascii=False, sort_keys=True)}; monthly concentration: {json.dumps(summary['monthly_concentration'], ensure_ascii=False, sort_keys=True)}.",
        "",
        "## Interpretation limit",
        "",
        "The fixed result, if positive, is only DEVELOPMENT incremental predictive evidence after coarse T-day-bounce control. Mechanism remains HYPOTHESIS. It does not prove seller exhaustion, panic clearing, a bottom, capital flow, causal reversal, executable alpha, production readiness, portfolio alpha, or Final OOS validation.",
        "",
        "## Governance",
        "",
        "B and B prospective observation are unchanged; RS, VCB, Volume-Path and turnover/RV are unchanged; C was not read; old D was not reconstructed; Final OOS is SEALED / UNREAD; the forbidden directory was untouched; no provider change, tuning, promotion, freeze or automatic follow-up was performed.",
    ]
    return "\n".join(lines) + "\n"


def run(*, phase: str, raw_dir: Path, core_manifest_path: Path, core_output_path: Path, b_membership_path: Path | None, rs_membership_path: Path | None, vcb_membership_path: Path | None, output_dir: Path, detail_dir: Path, base: str) -> dict[str, Any]:
    if phase not in {"signal", "full"}:
        raise ValueError("phase must be signal or full")
    protocol_path = Path("docs/research/new_controlled_right_side_reversal_v1_protocol.md")
    if not protocol_path.exists() or PROTOCOL_COMMIT not in protocol_path.read_text(encoding="utf-8"):
        raise RuntimeError("pre-outcome protocol commit identity is missing")
    detail_dir.mkdir(parents=True, exist_ok=True)
    signal_path = detail_dir / "new_controlled_right_side_reversal_v1_signal_membership.jsonl.gz"
    signal_audit_path = detail_dir / "new_controlled_right_side_reversal_v1_signal_audit.json"
    if phase == "full" and signal_path.exists() and signal_audit_path.exists():
        signal = _reuse_signal_pass(signal_path, signal_audit_path)
    else:
        signal = _signal_pass(raw_dir=raw_dir, core_manifest_path=core_manifest_path, core_output_path=core_output_path, b_membership_path=b_membership_path, rs_membership_path=rs_membership_path, vcb_membership_path=vcb_membership_path, signal_path=signal_path, audit_path=signal_audit_path)
    if phase == "signal":
        print(json.dumps(signal["signal_summary"], ensure_ascii=False, sort_keys=True))
        return signal["signal_summary"]
    outcomes = _process_outcomes(signal=signal, raw_dir=raw_dir, outcome_path=detail_dir / "new_controlled_right_side_reversal_v1_outcomes.jsonl.gz")
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA,
        "strategy": STRATEGY_VERSION,
        "base": base,
        "protocol": {"commit_sha": PROTOCOL_COMMIT, "status": "PRE_OUTCOME_PROTOCOL_COMMITTED"},
        "labels": ["DEVELOPMENT", "RECONSTRUCTED_RETROSPECTIVE", "DATE_ANCHORED", "DIAGNOSTIC_ONLY", "NEW_RESEARCH_HYPOTHESIS", "PREDICTIVE_EVIDENCE_UNTESTED_AT_PROTOCOL", "MECHANISM_EVIDENCE_HYPOTHESIS", "FINAL_OOS_UNREAD", "NO_VINTAGE_PROOF"],
        "input_audit": signal["audit"],
        "signal_only": signal["signal_only"],
        "signal_overlap": signal["signal_overlap"],
        "fixed_signal": {"downside_lookback": DOWNSIDE_LOOKBACK, "downside_quantile": DOWNSIDE_QUANTILE, "reclaim_lookback": RECLAIM_LOOKBACK, "bounce_bins": BOUNCE_BINS, "candidate": "DOWNSIDE_EXTREME AND RECLAIM5", "primary_control": "DOWNSIDE_EXTREME AND SIMPLE_POSITIVE_BOUNCE AND NOT RECLAIM5", "volume_confirmation": "VOLUME_CONFIRMATION_DISABLED_IN_CRSR_V1"},
        "artifacts": {"signal_membership": signal["signal_artifact"], "outcome_detail": {"logical_path": "local-only/new_controlled_right_side_reversal_v1_outcomes.jsonl.gz", **outcomes["outcome_artifact"]}},
        **{key: value for key, value in outcomes.items() if key != "outcome_artifact"},
        "alternative_explanations": {"size": "UNRESOLVED_ALTERNATIVE_EXPLANATION / NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION", "sector": "UNRESOLVED_ALTERNATIVE_EXPLANATION / NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION", "execution_slippage": "UNRESOLVED_ALTERNATIVE_EXPLANATION", "limit_state": "LIMIT_STATE_EXECUTION_CLASSIFICATION_NOT_AVAILABLE", "items": ["simple_mean_reversion_after_large_loss", "generic_t_day_rebound_strength", "generic_5_session_reclaim", "market_regime", "board_composition", "volatility_exposure", "liquidity_traded_amount", "size", "sector", "new_listing_history_availability", "gap_news", "limit_state_suspension", "repeated_same_stock_events", "common_calendar_shocks", "universe_construction", "corporate_action_artifacts", "price_level_tick_size"]},
        "transaction_cost": {"model": "TRANSACTION_COST_MODEL_NOT_PREEXISTING", "reported_returns": "gross"},
        "governance": {"new_research_hypothesis": True, "old_d_reconstruction": False, "b_unchanged": True, "b_prospective_unchanged": True, "rs_unchanged": True, "vcb_unchanged": True, "volume_path_unchanged": True, "turnover_rv_unchanged": True, "c_read": False, "final_oos_read": False, "forbidden_directory_touched": False, "automatic_follow_up_started": False, "parameter_tuning": False, "production_path_changed": False},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "new_controlled_right_side_reversal_v1_summary.json"
    report_path = output_dir / "new_controlled_right_side_reversal_v1_report.md"
    manifest_path = output_dir / "new_controlled_right_side_reversal_v1_manifest.json"
    write_json(summary_path, summary)
    report_path.write_text(_render_report(summary), encoding="utf-8", newline="\n")
    write_json(manifest_path, {"schema_version": MANIFEST_SCHEMA, "strategy": STRATEGY_VERSION, "protocol_commit_sha": PROTOCOL_COMMIT, "signal_artifact": signal["signal_artifact"], "outcome_detail_artifact": summary["artifacts"]["outcome_detail"], "summary_path": "docs/research/artifacts/new_controlled_right_side_reversal_v1_summary.json", "summary_sha256": file_sha256(summary_path), "report_path": "docs/research/artifacts/new_controlled_right_side_reversal_v1_report.md", "final_oos_read": False, "forbidden_directory_touched": False, "signal_sort": "date ascending, symbol ascending"})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("signal", "full"), default="signal")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/validation/core_signal_validation/raw"))
    parser.add_argument("--core-manifest", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"))
    parser.add_argument("--core-output", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_replay_results.jsonl.gz"))
    parser.add_argument("--b-membership", type=Path, default=Path("data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"))
    parser.add_argument("--rs-membership", type=Path, default=Path("data/validation/new_cross_sectional_relative_strength_leadership_v1/new_cross_sectional_relative_strength_leadership_v1_signal_membership.jsonl.gz"))
    parser.add_argument("--vcb-membership", type=Path, default=Path("data/validation/new_volatility_contraction_breakout_v1/new_volatility_contraction_breakout_v1_signal_membership.jsonl.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/research/artifacts"))
    parser.add_argument("--detail-dir", type=Path, default=Path("data/validation/new_controlled_right_side_reversal_v1"))
    parser.add_argument("--base", default="36f8120651e8f6a0d66e1d97769dc7c6d8a66e7b")
    args = parser.parse_args()
    result = run(phase=args.phase, raw_dir=args.raw_dir, core_manifest_path=args.core_manifest, core_output_path=args.core_output, b_membership_path=args.b_membership, rs_membership_path=args.rs_membership, vcb_membership_path=args.vcb_membership, output_dir=args.output_dir, detail_dir=args.detail_dir, base=args.base)
    if args.phase == "full":
        print(json.dumps({"decision": result["decision"], "primary": result["primary"], "continuous": result["continuous"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
