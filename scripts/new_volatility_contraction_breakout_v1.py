"""Fixed, independent evaluator for NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1.

The signal pass reads only the frozen T-close replay inputs.  The outcome pass
is separate and is enabled only after the committed pre-outcome protocol.  This
module does not import a production/prospective watchlist generator and never
reads Final OOS data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

import core_signal_replay as replay
import validate_development_returns_v2 as returns_v2


STRATEGY_VERSION = "NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1"
PROTOCOL_COMMIT = "177d1b9194c33a09ca619142df772bba4a960103"
RECENT_RANGE_WINDOW = 10
REFERENCE_RANGE_WINDOW = 40
BREAKOUT_WINDOW = 20
COMPRESSION_QUANTILE = 0.20
MIN_SIGNAL_BARS = max(RECENT_RANGE_WINDOW + REFERENCE_RANGE_WINDOW + 2, BREAKOUT_WINDOW + 1)
BOOTSTRAP_BLOCK_LENGTH = 20
BOOTSTRAP_REPETITIONS = 5000
BOOTSTRAP_SEED = 20260906
PRIMARY_HORIZON = "10D"
SECONDARY_HORIZON = "5D"
SIGNAL_SCHEMA = "VCB_SIGNAL_MEMBERSHIP_V1"
SUMMARY_SCHEMA = "VCB_RESEARCH_SUMMARY_V1"
MANIFEST_SCHEMA = "VCB_RESEARCH_MANIFEST_V1"
VALID_CLASSES = ("CANDIDATE", "PRIMARY_CONTROL")
BOARDS = ("Main", "ChiNext", "STAR", "OUT_OF_SCOPE_PREFIX")
EXPECTED_DAILY_K_SHA256 = "61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426"
EXPECTED_ADJUSTMENT_SHA256 = "a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716"
EXPECTED_CORE_OUTPUT_SHA256 = "0d23cf54843920f5fdcc05847e4b78c5d605b05c8793f878b6021c85b3ab0c2f"
EXPECTED_UNIVERSE_ROWS = 4_041_140
EXPECTED_UNIVERSE_IDENTITY_SHA256 = "dbc5d220f24f51a0245d047b88733c961fc4f184d02ef6f5ac0fc795576217b0"


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
    content_digest = hashlib.sha256()
    count = 0
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            for row in rows:
                line = (canonical_json(dict(row)) + "\n").encode("utf-8")
                compressed.write(line)
                content_digest.update(line)
                count += 1
    return {"path": path.as_posix(), "rows": count, "bytes": path.stat().st_size, "file_sha256": file_sha256(path), "content_sha256": content_digest.hexdigest()}


def _rank_ascending(values: Mapping[str, float]) -> dict[str, int]:
    ordered = sorted(values.items(), key=lambda item: (float(item[1]), item[0]))
    return {symbol: index for index, (symbol, _value) in enumerate(ordered, start=1)}


def _bottom_k(n: int) -> int:
    return int(math.ceil(COMPRESSION_QUANTILE * n))


def _is_generic_breakout(close_t: float, prior_high20: float) -> bool:
    return float(close_t) > float(prior_high20)


def _classify(generic_breakout: bool, strong_compression: bool) -> tuple[bool, bool]:
    return bool(generic_breakout and strong_compression), bool(generic_breakout and not strong_compression)


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


def _moving_block_bootstrap_ci(values: Sequence[float], *, block_length: int = BOOTSTRAP_BLOCK_LENGTH, repetitions: int = BOOTSTRAP_REPETITIONS, seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) == 0 or not np.isfinite(array).all():
        raise ValueError("bootstrap values must be a non-empty finite vector")
    if block_length < 1 or block_length > len(array) or repetitions < 1:
        raise ValueError("invalid moving-block bootstrap parameters")
    starts = np.arange(0, len(array) - block_length + 1, dtype=int)
    rng = np.random.default_rng(seed)
    means = np.empty(repetitions, dtype=float)
    block_count = int(math.ceil(len(array) / block_length))
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


def _summary_stats(values: Sequence[float], state: Mapping[str, Any]) -> dict[str, Any]:
    result = _distribution(values)
    result.update({"positive_rate": float(np.mean(np.asarray(values) > 0)) if values else None, "mfe_mean": float(np.mean(state["mfe"])) if state["mfe"] else None, "mae_mean": float(np.mean(state["mae"])) if state["mae"] else None, "status_counts": dict(sorted(state["status_counts"].items()))})
    return result


def _new_state() -> dict[str, Any]:
    return {"status_counts": Counter(), "returns": [], "mfe": [], "mae": []}


def _update_state(state: dict[str, Any], outcome: Mapping[str, Any]) -> None:
    state["status_counts"][str(outcome["status"])] += 1
    if outcome["status"] == "AVAILABLE":
        state["returns"].append(float(outcome["return_pct"]))
        state["mfe"].append(float(outcome["mfe_pct"]))
        state["mae"].append(float(outcome["mae_pct"]))


def _outcome_record(row: Mapping[str, Any], store: dict[str, Any], events: dict[str, list[tuple[int, float, float, float, float]]], session_dates: list[str], session_ms: np.ndarray, session_index: dict[str, int]) -> dict[str, Any]:
    return returns_v2._build_event_record(row={"as_of_date": row["date"], "signal_date": row["date"], "earliest_execution_date": row["earliest_execution_date"], "symbol": row["symbol"], "setup_id": STRATEGY_VERSION}, store=store, events=events, session_dates=session_dates, session_ms=session_ms, session_index=session_index)


def _feature_from_bars(closes: Sequence[float], highs: Sequence[float], lows: Sequence[float], turnover: Sequence[float] | None = None) -> dict[str, float] | None:
    if len(closes) < MIN_SIGNAL_BARS or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    c = np.asarray(closes, dtype=float)
    hi = np.asarray(highs, dtype=float)
    lo = np.asarray(lows, dtype=float)
    if not np.isfinite(c).all() or not np.isfinite(hi).all() or not np.isfinite(lo).all() or (c <= 0).any() or (hi <= 0).any() or (lo <= 0).any():
        return None
    tr = np.maximum.reduce((hi[1:] - lo[1:], np.abs(hi[1:] - c[:-1]), np.abs(lo[1:] - c[:-1])))
    previous_close = c[:-1]
    if len(tr) < RECENT_RANGE_WINDOW + REFERENCE_RANGE_WINDOW + 1 or (previous_close <= 0).any() or not np.isfinite(tr).all():
        return None
    trp = tr / previous_close
    recent = trp[-(RECENT_RANGE_WINDOW + 1) : -1]
    reference = trp[-(RECENT_RANGE_WINDOW + REFERENCE_RANGE_WINDOW + 1) : -(RECENT_RANGE_WINDOW + 1)]
    if len(recent) != 10 or len(reference) != 40 or not np.isfinite(recent).all() or not np.isfinite(reference).all():
        return None
    recent_mean = float(np.mean(recent))
    reference_mean = float(np.mean(reference))
    if not _finite(recent_mean) or not _finite(reference_mean) or reference_mean <= 0:
        return None
    prior_high = float(np.max(hi[-(BREAKOUT_WINDOW + 1) : -1]))
    prior_return = float(c[-1] / c[-BREAKOUT_WINDOW - 1] - 1.0)
    close_returns = c[-(RECENT_RANGE_WINDOW + 1) :][1:] / c[-(RECENT_RANGE_WINDOW + 1) :][:-1] - 1.0
    prior_volatility = float(np.std(close_returns * 100.0, ddof=1))
    median_amount = None
    if turnover is not None and len(turnover) >= RECENT_RANGE_WINDOW and np.isfinite(turnover[-RECENT_RANGE_WINDOW:]).all() and (np.asarray(turnover[-RECENT_RANGE_WINDOW:]) >= 0).all():
        median_amount = float(np.median(np.asarray(turnover[-RECENT_RANGE_WINDOW:], dtype=float)))
    return {"trp_recent10": recent_mean, "trp_reference40": reference_mean, "contraction_ratio": recent_mean / reference_mean, "prior_high20": prior_high, "close_t": float(c[-1]), "prior_return20": prior_return, "prior_volatility20_pct": prior_volatility, "median_traded_amount20": median_amount}


def _load_b_membership(path: Path) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    memberships: set[tuple[str, str]] = set()
    rows = 0
    for record in _iter_jsonl_gzip(path):
        rows += 1
        signal_date, symbol = record.get("signal_date"), record.get("symbol")
        if isinstance(signal_date, str) and isinstance(symbol, str):
            memberships.add((signal_date, symbol.lower()))
    return memberships, {"logical_path": path.as_posix(), "rows_read_for_signal_membership": rows, "unique_signal_memberships": len(memberships), "file_sha256": file_sha256(path), "outcomes_accessed": False}


def _input_audit(raw_dir: Path, core_manifest_path: Path, core_output_path: Path) -> dict[str, Any]:
    paths = (raw_dir, core_manifest_path, core_output_path)
    if any("final_oos" in str(path).lower() for path in paths):
        raise RuntimeError("Final OOS path is forbidden")
    manifest = json.loads(core_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "CORE_SIGNAL_VALIDATION_DATASET_MANIFEST_V1":
        raise RuntimeError("VCB_INPUT_PROVENANCE_CONFLICT: core manifest schema")
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
        raise RuntimeError("VCB_INPUT_PROVENANCE_CONFLICT: frozen input identity mismatch")
    previous: tuple[str, str] | None = None
    ordered = True
    identity_rows = 0
    with gzip.open(core_output_path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            row = json.loads(line)
            key = (str(row["signal_date"]), str(row["symbol"]))
            ordered = ordered and (previous is None or key >= previous)
            previous = key
            identity_rows += 1
    if not ordered or identity_rows != EXPECTED_UNIVERSE_ROWS:
        raise RuntimeError("VCB_HISTORICAL_PIT_UNIVERSE_NOT_AVAILABLE: identity stream mismatch")
    counts = [item["evaluable_symbol_count"] for item in coverage.values()]
    raw_counts = [item["raw_symbol_count_at_T"] for item in coverage.values()]
    return {
        "status": "PASS",
        "historical_pit_universe": {"source": "existing continuous replay universe", "sessions": len(signal_dates), "first_session": signal_dates[0], "last_session": signal_dates[-1], "candidate_evaluations": expected, "per_session_min": min(counts), "per_session_max": max(counts), "per_session_mean": float(np.mean(counts)), "per_session_median": float(np.median(counts)), "raw_t_day_min": min(raw_counts), "raw_t_day_max": max(raw_counts), "semantics": manifest["universe_semantics"], "identity_source_sha256": EXPECTED_UNIVERSE_IDENTITY_SHA256, "identity_stream_sorted": True, "listing_handling": "T-day raw row plus >=120 valid bars; no current backfill", "missing_history_handling": "symbol-date exclusion; no interpolation or session deletion", "board_identity": "Main=00/60; ChiNext=30; STAR=68; other prefixes retained and reported separately"},
        "signal_ohlc_basis": {"semantics": manifest["adjustment_semantics"], "daily_k_sha256": daily_hash, "adjustment_factors_sha256": adjustment_hash, "known_at_vintage_proof": manifest["provenance"]["known_at_vintage_proof"], "future_events_excluded": True, "ohlc_fields": ["open", "high", "low", "close"], "corporate_action_check": "validated T-anchor affine transform; positive finite OHLC; duplicate-free keys"},
        "calendar": {"benchmark_rows": index_meta["row_count"], "benchmark_files": index_meta["files"], "schedule": manifest["signal_date_schedule"], "timezone": "Asia/Shanghai", "window_unit": "completed XSHG signal sessions"},
        "raw_stock_meta": stock_meta,
        "adjustment_event_meta": event_meta,
        "core_output_sha256": core_hash,
        "final_oos_read": False,
        "forbidden_directory_touched": False,
    }


def _signal_pass(*, raw_dir: Path, core_manifest_path: Path, core_output_path: Path, b_membership_path: Path, signal_path: Path, audit_path: Path) -> dict[str, Any]:
    audit = _input_audit(raw_dir, core_manifest_path, core_output_path)
    index_dates, _index_bars, _index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_position = {date: index for index, date in enumerate(session_dates)}
    signal_dates = [date for date in session_dates if replay.VALIDATION_START <= date <= replay.VALIDATION_END]
    store, _stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")
    b_memberships, b_source = _load_b_membership(b_membership_path)
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    content_digest = hashlib.sha256()
    per_date: dict[str, dict[str, Any]] = {}
    signal_rows = 0
    all_generic_pairs: list[tuple[str, str]] = []
    candidate_pairs: list[tuple[str, str]] = []
    control_pairs: list[tuple[str, str]] = []
    with signal_path.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0) as compressed:
            for date_index, signal_date in enumerate(signal_dates):
                anchor_ms = index_dates[signal_date]
                eligible_symbols, numeric_bars = replay._numeric_bars_for_date(store, signal_date, anchor_ms, events)
                ratio_values: dict[str, float] = {}
                features: dict[str, dict[str, Any]] = {}
                exclusion_counts: Counter[str] = Counter()
                for symbol in sorted(eligible_symbols):
                    closes, _volume, highs, lows = numeric_bars[symbol]
                    start, end = store["bounds"][symbol]
                    turnover = store["turnover"][start:end]
                    feature = _feature_from_bars(closes, highs, lows, turnover)
                    if feature is None:
                        reason = "INSUFFICIENT_SIGNAL_HISTORY" if len(closes) < MIN_SIGNAL_BARS else "INVALID_OHLC_OR_TRP"
                        exclusion_counts[reason] += 1
                        features[symbol] = {"eligibility": "EXCLUDED", "exclusion_reason": reason}
                    else:
                        ratio_values[symbol] = feature["contraction_ratio"]
                        features[symbol] = {"eligibility": "VALID_FEATURE", "exclusion_reason": None, **feature}
                ranks = _rank_ascending(ratio_values)
                bottom_k = _bottom_k(len(ratio_values))
                date_rows: list[dict[str, Any]] = []
                group_rows: dict[str, list[dict[str, Any]]] = {"CANDIDATE": [], "PRIMARY_CONTROL": []}
                generic_count = 0
                for symbol in sorted(eligible_symbols):
                    feature = features[symbol]
                    valid = feature["eligibility"] == "VALID_FEATURE"
                    ratio = feature.get("contraction_ratio")
                    actual = bool(valid and ratio < 1.0)
                    strong = bool(actual and ranks[symbol] <= bottom_k)
                    breakout = bool(valid and _is_generic_breakout(feature["close_t"], feature["prior_high20"]))
                    candidate, control = _classify(breakout, strong)
                    if breakout:
                        generic_count += 1
                        all_generic_pairs.append((signal_date, symbol))
                    if candidate:
                        candidate_pairs.append((signal_date, symbol))
                    if control:
                        control_pairs.append((signal_date, symbol))
                    next_position = session_position[signal_date] + 1
                    row = {"date": signal_date, "symbol": symbol, "board": _board(symbol), "earliest_execution_date": session_dates[next_position] if next_position < len(session_dates) else None, "eligibility": feature["eligibility"], "exclusion_reason": feature["exclusion_reason"], "trp_recent10": feature.get("trp_recent10"), "trp_reference40": feature.get("trp_reference40"), "contraction_ratio": ratio, "compression_rank": ranks.get(symbol), "actual_contraction": actual, "strong_compression": strong, "prior_high20": feature.get("prior_high20"), "close_t": feature.get("close_t"), "generic_breakout": breakout, "candidate": candidate, "primary_control": control, "prior_return20": feature.get("prior_return20"), "prior_volatility20_pct": feature.get("prior_volatility20_pct"), "median_traded_amount20": feature.get("median_traded_amount20"), "b_signal_membership": (signal_date, symbol) in b_memberships}
                    date_rows.append(row)
                    if candidate:
                        group_rows["CANDIDATE"].append(row)
                    elif control:
                        group_rows["PRIMARY_CONTROL"].append(row)
                    line = (canonical_json(row) + "\n").encode("utf-8")
                    compressed.write(line)
                    content_digest.update(line)
                    signal_rows += 1
                per_date[signal_date] = {"signal_date": signal_date, "eligible_n": len(eligible_symbols), "valid_feature_n": len(ratio_values), "insufficient_history_n": exclusion_counts["INSUFFICIENT_SIGNAL_HISTORY"], "invalid_ohlc_or_trp_n": exclusion_counts["INVALID_OHLC_OR_TRP"], "generic_breakout_n": generic_count, "candidate_n": len(group_rows["CANDIDATE"]), "primary_control_n": len(group_rows["PRIMARY_CONTROL"]), "candidate_rows": group_rows["CANDIDATE"], "control_rows": group_rows["PRIMARY_CONTROL"]}
                if date_index % 100 == 0:
                    print(f"signal pass {date_index + 1}/{len(signal_dates)} {signal_date}", flush=True)
    candidate_dates = {date for date, _symbol in candidate_pairs}
    control_dates = {date for date, _symbol in control_pairs}
    b_pairs = {(date, symbol) for date, symbol in b_memberships if date in per_date}
    candidate_set, control_set = set(candidate_pairs), set(control_pairs)
    overlap = len(candidate_set & b_pairs)
    signal_only = {"sessions": len(per_date), "first_session": min(per_date), "last_session": max(per_date), "eligible_symbol_dates": sum(item["eligible_n"] for item in per_date.values()), "valid_contraction_ratio_count": sum(item["valid_feature_n"] for item in per_date.values()), "insufficient_history_count": sum(item["insufficient_history_n"] for item in per_date.values()), "generic_breakout_count": len(all_generic_pairs), "candidate_count": len(candidate_pairs), "control_count": len(control_pairs), "candidate_active_dates": len(candidate_dates), "control_active_dates": len(control_dates), "dates_both_groups_present": len(candidate_dates & control_dates), "mean_candidate_n_per_date": float(np.mean([item["candidate_n"] for item in per_date.values()])), "median_candidate_n_per_date": float(np.median([item["candidate_n"] for item in per_date.values()])), "mean_control_n_per_date": float(np.mean([item["primary_control_n"] for item in per_date.values()])), "median_control_n_per_date": float(np.median([item["primary_control_n"] for item in per_date.values()])), "sample_gate": {"both_group_active_dates_min": 200, "candidate_events_min": 500, "control_events_min": 500, "status": "PASS" if len(candidate_dates & control_dates) >= 200 and len(candidate_pairs) >= 500 and len(control_pairs) >= 500 else "VCB_SIGNAL_CONSTRUCTION_NOT_RESEARCH_READY"}}
    if signal_only["sample_gate"]["status"] != "PASS":
        raise RuntimeError(signal_only["sample_gate"]["status"])
    signal_artifact = {"logical_path": "local-only/new_volatility_contraction_breakout_v1_signal_membership.jsonl.gz", "rows": signal_rows, "bytes": signal_path.stat().st_size, "file_sha256": file_sha256(signal_path), "content_sha256": content_digest.hexdigest(), "sort": "date ascending, symbol ascending"}
    b_overlap = {"source": b_source, "same_date_overlap": len(candidate_dates & {date for date, _symbol in b_pairs}), "same_symbol_date_overlap": overlap, "candidate_share_overlapping_b": overlap / len(candidate_pairs) if candidate_pairs else None, "b_share_overlapping_candidate": overlap / len(b_pairs) if b_pairs else None, "b_memberships_in_research_dates": len(b_pairs)}
    signal_summary = {"schema_version": SIGNAL_SCHEMA, "strategy": STRATEGY_VERSION, "protocol_commit_sha": PROTOCOL_COMMIT, "input_audit": audit, "signal_only": signal_only, "b_signal_overlap": b_overlap, "signal_artifact": signal_artifact, "final_oos_read": False, "forbidden_directory_touched": False}
    write_json(audit_path, signal_summary)
    return {"audit": audit, "per_date": per_date, "signal_only": signal_only, "signal_artifact": signal_artifact, "b_signal_overlap": b_overlap, "signal_summary": signal_summary}


def _process_outcomes(*, signal: dict[str, Any], raw_dir: Path, signal_path: Path, outcome_path: Path) -> dict[str, Any]:
    index_dates, _index_bars, _index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.asarray([index_dates[date] for date in session_dates], dtype=np.int64)
    session_index = {date: index for index, date in enumerate(session_dates)}
    store, _stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")
    states = {name: {horizon: _new_state() for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for name in VALID_CLASSES}
    board_states = {board: {name: {horizon: [] for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for name in VALID_CLASSES} for board in BOARDS}
    outcome_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    daily_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    rhos: list[dict[str, Any]] = []
    for date in sorted(signal["per_date"]):
        group_outcomes: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {name: [] for name in VALID_CLASSES}
        for name, key in (("CANDIDATE", "candidate_rows"), ("PRIMARY_CONTROL", "control_rows")):
            for row in signal["per_date"][date][key]:
                outcome = _outcome_record(row, store, events, session_dates, session_ms, session_index)
                outcome_by_pair[(date, row["symbol"])] = outcome
                group_outcomes[name].append((row, outcome))
                detail_rows.append({"signal": row, "outcome": outcome})
                for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON):
                    _update_state(states[name][horizon], outcome["outcomes"][horizon])
                    if outcome["outcomes"][horizon]["status"] == "AVAILABLE":
                        board_states[row["board"]][name][horizon].append(float(outcome["outcomes"][horizon]["return_pct"]))
        def valid_returns(name: str, horizon: str) -> list[float]:
            return [float(item[1]["outcomes"][horizon]["return_pct"]) for item in group_outcomes[name] if item[1]["outcomes"][horizon]["status"] == "AVAILABLE"]
        candidate_10, control_10 = valid_returns("CANDIDATE", PRIMARY_HORIZON), valid_returns("PRIMARY_CONTROL", PRIMARY_HORIZON)
        candidate_5, control_5 = valid_returns("CANDIDATE", SECONDARY_HORIZON), valid_returns("PRIMARY_CONTROL", SECONDARY_HORIZON)
        generic_10 = candidate_10 + control_10
        spread_10 = float(np.mean(candidate_10) - np.mean(control_10)) if candidate_10 and control_10 else None
        spread_5 = float(np.mean(candidate_5) - np.mean(control_5)) if candidate_5 and control_5 else None
        generic_mean_10 = float(np.mean(generic_10)) if generic_10 else None
        compression, returns = [], []
        for name in VALID_CLASSES:
            for row, outcome in group_outcomes[name]:
                value = outcome["outcomes"][PRIMARY_HORIZON]
                if value["status"] == "AVAILABLE":
                    compression.append(-float(row["contraction_ratio"]))
                    returns.append(float(value["return_pct"]))
        rho = spearman(compression, returns) if len(returns) >= 5 else None
        if rho is not None:
            rhos.append({"date": date, "rho": rho, "n": len(returns)})
        daily_rows.append({"date": date, "candidate_n": len(candidate_10), "control_n": len(control_10), "candidate_mean_10D": float(np.mean(candidate_10)) if candidate_10 else None, "control_mean_10D": float(np.mean(control_10)) if control_10 else None, "spread_10D": spread_10, "candidate_n_5D": len(candidate_5), "control_n_5D": len(control_5), "candidate_mean_5D": float(np.mean(candidate_5)) if candidate_5 else None, "control_mean_5D": float(np.mean(control_5)) if control_5 else None, "spread_5D": spread_5, "generic_breakout_mean_10D": generic_mean_10, "candidate_minus_full_generic_mean_10D": float(np.mean(candidate_10) - generic_mean_10) if candidate_10 and generic_mean_10 is not None else None, "continuous_rho_10D": rho})
    outcome_artifact = _write_jsonl_gzip(outcome_path, detail_rows)
    raw_events = []
    for date in sorted(signal["per_date"]):
        raw_events.extend([(date, row["symbol"], "CANDIDATE" if row["candidate"] else "PRIMARY_CONTROL") for row in signal["per_date"][date]["candidate_rows"] + signal["per_date"][date]["control_rows"]])
    by_symbol: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for date, symbol, name in raw_events:
        by_symbol[symbol].append((date, name))
    retained = _cooldown_retain(raw_events, session_index, cooldown_sessions=10)
    cooldown_daily: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"CANDIDATE": [], "PRIMARY_CONTROL": []})
    for date, symbol, name in retained:
        outcome = outcome_by_pair[(date, symbol)][PRIMARY_HORIZON]
        if outcome["status"] == "AVAILABLE":
            cooldown_daily[date][name].append(float(outcome["return_pct"]))
    cooldown_spreads = [float(np.mean(values["CANDIDATE"]) - np.mean(values["PRIMARY_CONTROL"])) for date, values in sorted(cooldown_daily.items()) if values["CANDIDATE"] and values["PRIMARY_CONTROL"]]
    cooldown_ci = list(_moving_block_bootstrap_ci(cooldown_spreads)) if len(cooldown_spreads) >= BOOTSTRAP_BLOCK_LENGTH else [None, None]
    primary_spreads = [float(row["spread_10D"]) for row in daily_rows if row["spread_10D"] is not None]
    primary_5d = [float(row["spread_5D"]) for row in daily_rows if row["spread_5D"] is not None]
    ci = list(_moving_block_bootstrap_ci(primary_spreads)) if len(primary_spreads) >= BOOTSTRAP_BLOCK_LENGTH else [None, None]
    ci_5d = list(_moving_block_bootstrap_ci(primary_5d)) if len(primary_5d) >= BOOTSTRAP_BLOCK_LENGTH else [None, None]
    years = {}
    for year in ("2023", "2024", "2025", "2026"):
        values = [float(row["spread_10D"]) for row in daily_rows if row["date"].startswith(year) and row["spread_10D"] is not None]
        years[year] = {"dates": len(values), "mean_spread_10D": float(np.mean(values)) if values else None, "median_spread_10D": float(np.median(values)) if values else None, "positive_date_rate": float(np.mean(np.asarray(values) > 0)) if values else None, "sign_positive": bool(np.mean(values) > 0) if values else None}
    board_diagnostics = {board: {name: {horizon: _distribution(board_states[board][name][horizon]) for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for name in VALID_CLASSES} for board in BOARDS}
    signal_rows_by_class = {name: [row for date in sorted(signal["per_date"]) for row in signal["per_date"][date]["candidate_rows" if name == "CANDIDATE" else "control_rows"]] for name in VALID_CLASSES}
    symbol_concentration = {}
    for name, rows in signal_rows_by_class.items():
        counts = Counter(row["symbol"] for row in rows)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        total = sum(counts.values())
        symbol_concentration[name] = {"unique_symbols": len(counts), "top1_share": ordered[0][1] / total if ordered else None, "top5_share": sum(count for _symbol, count in ordered[:5]) / total if total else None, "top10": [{"symbol": symbol, "count": count} for symbol, count in ordered[:10]]}
    monthly = Counter(row["date"][:7] for row in daily_rows if row["spread_10D"] is not None)
    outcome_maturity = {}
    last_signal_index = session_index[max(signal["per_date"])]
    for horizon in (5, 10):
        mature = min(last_signal_index, len(session_dates) - 1 - horizon)
        outcome_maturity[f"{horizon}D"] = {"mature_through_signal_date": session_dates[mature], "censored_signal_dates_after_maturity": max(0, last_signal_index - mature)}
    primary = {"mean_spread_10D": float(np.mean(primary_spreads)) if primary_spreads else None, "median_spread_10D": float(np.median(primary_spreads)) if primary_spreads else None, "moving_block_bootstrap_ci_95": ci, "positive_spread_date_rate_10D": float(np.mean(np.asarray(primary_spreads) > 0)) if primary_spreads else None, "both_group_valid_date_count": len(primary_spreads), "spread_date_count": len(daily_rows)}
    rho_values = [float(item["rho"]) for item in rhos]
    full_generic_state = {horizon: _new_state() for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)}
    for name in VALID_CLASSES:
        for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON):
            for field in ("returns", "mfe", "mae"):
                full_generic_state[horizon][field].extend(states[name][horizon][field])
            full_generic_state[horizon]["status_counts"].update(states[name][horizon]["status_counts"])
    simple_baseline = {horizon: _summary_stats(full_generic_state[horizon]["returns"], full_generic_state[horizon]) for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)}
    support = primary["mean_spread_10D"] is not None and primary["mean_spread_10D"] > 0 and ci[0] is not None and ci[0] > 0 and rho_values and float(np.mean(rho_values)) > 0 and cooldown_spreads and float(np.mean(cooldown_spreads)) >= 0 and sum(bool(years[y]["sign_positive"]) for y in years) >= 3
    if ci[1] is not None and ci[1] <= 0:
        decision = "VOLATILITY_CONTRACTION_BREAKOUT_NO_CLEAR_INCREMENTAL_SIGNAL"
    elif primary["mean_spread_10D"] is not None and primary["mean_spread_10D"] <= 0 and (not rho_values or float(np.mean(rho_values)) <= 0):
        decision = "VOLATILITY_CONTRACTION_BREAKOUT_NO_CLEAR_INCREMENTAL_SIGNAL"
    elif support:
        decision = "VOLATILITY_CONTRACTION_BREAKOUT_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION"
    else:
        decision = "VOLATILITY_CONTRACTION_BREAKOUT_NEEDS_MORE_EVIDENCE"
    return {"outcome_artifact": outcome_artifact, "primary": primary, "secondary_5D": {"mean_spread_5D": float(np.mean(primary_5d)) if primary_5d else None, "median_spread_5D": float(np.median(primary_5d)) if primary_5d else None, "moving_block_bootstrap_ci_95": ci_5d, "positive_spread_date_rate_5D": float(np.mean(np.asarray(primary_5d) > 0)) if primary_5d else None}, "daily_rows": daily_rows, "continuous": {"mean_daily_rho": float(np.mean(rho_values)) if rho_values else None, "median_daily_rho": float(np.median(rho_values)) if rho_values else None, "positive_rho_date_rate": float(np.mean(np.asarray(rho_values) > 0)) if rho_values else None, "valid_rho_dates": len(rho_values)}, "simple_generic_breakout_baseline": simple_baseline, "execution_coverage": {name: {horizon: _summary_stats(states[name][horizon]["returns"], states[name][horizon]) for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for name in VALID_CLASSES}, "outcome_status_counts": {name: {horizon: dict(sorted(states[name][horizon]["status_counts"].items())) for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for name in VALID_CLASSES}, "outcome_maturity": outcome_maturity, "year_diagnostics": years, "board_diagnostics": board_diagnostics, "symbol_concentration": symbol_concentration, "monthly_concentration": dict(sorted(monthly.items())), "cooldown": {"raw_event_counts": {"candidate": sum(name == "CANDIDATE" for _date, _symbol, name in raw_events), "control": sum(name == "PRIMARY_CONTROL" for _date, _symbol, name in raw_events)}, "retained_event_counts": {"candidate": sum(name == "CANDIDATE" for _date, _symbol, name in retained), "control": sum(name == "PRIMARY_CONTROL" for _date, _symbol, name in retained)}, "both_group_valid_dates": len(cooldown_spreads), "mean_spread_10D": float(np.mean(cooldown_spreads)) if cooldown_spreads else None, "moving_block_bootstrap_ci_95": cooldown_ci, "direction_relative_to_primary": "same_sign" if cooldown_spreads and primary_spreads and np.sign(np.mean(cooldown_spreads)) == np.sign(np.mean(primary_spreads)) else "different_or_unavailable"}, "candidate_control_prior_distributions": {name: {"prior_return20": _distribution([float(row["prior_return20"]) for row in rows]), "prior_volatility20_pct": _distribution([float(row["prior_volatility20_pct"]) for row in rows]), "median_traded_amount20": _distribution([float(row["median_traded_amount20"]) for row in rows if row["median_traded_amount20"] is not None])} for name, rows in signal_rows_by_class.items()}, "decision": decision}


def _render_report(summary: Mapping[str, Any]) -> str:
    primary, continuous = summary["primary"], summary["continuous"]
    lines = ["# NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1 — research report", "", f"Decision: `{summary['decision']}`", "", "This is DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DATE_ANCHORED / DIAGNOSTIC_ONLY evidence. It is not production, a frozen candidate, causal mechanism evidence, or Final OOS.", "", "## Fixed identity", "", f"- Base: `{summary['base']}`; protocol commit: `{summary['protocol']['commit_sha']}`.", f"- Sessions: {summary['signal_only']['sessions']} ({summary['signal_only']['first_session']} to {summary['signal_only']['last_session']}).", f"- Universe identities: {summary['signal_only']['eligible_symbol_dates']}; generic breakout={summary['signal_only']['generic_breakout_count']}; candidate={summary['signal_only']['candidate_count']}; control={summary['signal_only']['control_count']}.", "- Rule: TRP recent 10 sessions versus prior 40 sessions, ratio < 1, bottom 20% rank with symbol tie-break, strict close > prior 20-session high; volume qualification disabled.", "", "## Primary incremental result", "", f"- 10D equal-weight date spread (candidate minus primary control): {primary['mean_spread_10D']} percentage points.", f"- Median spread: {primary['median_spread_10D']} percentage points.", f"- 95% moving-block-bootstrap CI: {primary['moving_block_bootstrap_ci_95']}.", f"- Positive-spread date rate: {primary['positive_spread_date_rate_10D']}; both-group valid dates: {primary['both_group_valid_date_count']}.", f"- Continuous compression rho: mean={continuous['mean_daily_rho']}, median={continuous['median_daily_rho']}, positive-date rate={continuous['positive_rho_date_rate']}, valid dates={continuous['valid_rho_dates']}.", "", "## Secondary and robustness", "", f"- 5D candidate-control spread: {summary['secondary_5D']['mean_spread_5D']} percentage points.", f"- Cooldown: {summary['cooldown']['mean_spread_10D']} percentage points; CI={summary['cooldown']['moving_block_bootstrap_ci_95']}.", f"- Year diagnostics: {json.dumps(summary['year_diagnostics'], ensure_ascii=False, sort_keys=True)}", f"- Board diagnostics: {json.dumps(summary['board_diagnostics'], ensure_ascii=False, sort_keys=True)}", f"- Prior distributions: {json.dumps(summary['candidate_control_prior_distributions'], ensure_ascii=False, sort_keys=True)}", "", "## Input and execution boundaries", "", f"- Input audit: `{summary['input_audit']['status']}`; OHLC basis=`{summary['input_audit']['signal_ohlc_basis']['semantics']}`; universe identity=`{summary['input_audit']['historical_pit_universe']['identity_source_sha256']}`.", "- Reference entry: T+1 XSHG open; `REFERENCE_EXECUTION_NOT_ACTUAL_FILL`.", f"- Execution/status coverage: {json.dumps(summary['outcome_status_counts'], ensure_ascii=False, sort_keys=True)}", "- Historical PIT size and sector explanations: unresolved/not available for this V1 identification.", f"- B signal overlap (membership only): {json.dumps(summary['b_signal_overlap'], ensure_ascii=False, sort_keys=True)}", "- RS signal overlap: NOT_AVAILABLE; no canonical RS membership detail was lawfully available.", "- Limit-state classification: LIMIT_STATE_EXECUTION_CLASSIFICATION_NOT_AVAILABLE.", "- Transaction-cost model: TRANSACTION_COST_MODEL_NOT_PREEXISTING; reported returns are gross.", "", "## Interpretation limit", "", "The fixed result, if positive, is only DEVELOPMENT incremental predictive evidence over the generic-breakout control. Mechanism remains HYPOTHESIS; this is not production-ready, frozen, causal, portfolio-alpha, or Final OOS evidence.", "", "## Governance", "", "B and its prospective observation remain unchanged; RS, Volume-Path and turnover/RV remain unchanged; C, controlled reversal, Final OOS and the forbidden directory were not read; no provider replacement, parameter tuning, promotion, freeze or follow-up candidate was started."]
    return "\n".join(lines) + "\n"


def run(*, phase: str, raw_dir: Path, core_manifest_path: Path, core_output_path: Path, b_membership_path: Path, output_dir: Path, detail_dir: Path, base: str) -> dict[str, Any]:
    if phase not in {"signal", "full"}:
        raise ValueError("phase must be signal or full")
    protocol_path = Path("docs/research/new_volatility_contraction_breakout_v1_protocol.md")
    if not protocol_path.exists() or PROTOCOL_COMMIT not in protocol_path.read_text(encoding="utf-8"):
        raise RuntimeError("pre-outcome protocol commit identity is missing")
    detail_dir.mkdir(parents=True, exist_ok=True)
    signal_path = detail_dir / "new_volatility_contraction_breakout_v1_signal_membership.jsonl.gz"
    signal_audit_path = detail_dir / "new_volatility_contraction_breakout_v1_signal_audit.json"
    signal = _signal_pass(raw_dir=raw_dir, core_manifest_path=core_manifest_path, core_output_path=core_output_path, b_membership_path=b_membership_path, signal_path=signal_path, audit_path=signal_audit_path)
    if phase == "signal":
        print(json.dumps(signal["signal_summary"], ensure_ascii=False, sort_keys=True))
        return signal["signal_summary"]
    outcome_path = detail_dir / "new_volatility_contraction_breakout_v1_outcomes.jsonl.gz"
    outcomes = _process_outcomes(signal=signal, raw_dir=raw_dir, signal_path=signal_path, outcome_path=outcome_path)
    summary: dict[str, Any] = {"schema_version": SUMMARY_SCHEMA, "strategy": STRATEGY_VERSION, "base": base, "protocol": {"commit_sha": PROTOCOL_COMMIT, "status": "PRE_OUTCOME_PROTOCOL_COMMITTED"}, "labels": ["DEVELOPMENT", "RECONSTRUCTED_RETROSPECTIVE", "DATE_ANCHORED", "DIAGNOSTIC_ONLY", "NEW_RESEARCH_HYPOTHESIS", "PREDICTIVE_EVIDENCE_UNTESTED_AT_PROTOCOL", "MECHANISM_EVIDENCE_HYPOTHESIS", "FINAL_OOS_UNREAD", "NO_VINTAGE_PROOF"], "input_audit": signal["audit"], "signal_only": signal["signal_only"], "fixed_signal": {"recent_range_window": RECENT_RANGE_WINDOW, "reference_range_window": REFERENCE_RANGE_WINDOW, "breakout_window": BREAKOUT_WINDOW, "compression_quantile": COMPRESSION_QUANTILE, "actual_contraction": "ratio < 1.0", "candidate": "generic breakout AND strong compression", "primary_control": "generic breakout AND NOT strong compression", "volume_confirmation": "VOLUME_CONFIRMATION_DISABLED_IN_V1"}, "b_signal_overlap": signal["b_signal_overlap"], "rs_signal_overlap": "NOT_AVAILABLE", "artifacts": {"signal_membership": signal["signal_artifact"], "outcome_detail": {"logical_path": "local-only/new_volatility_contraction_breakout_v1_outcomes.jsonl.gz", **outcomes["outcome_artifact"]}}, **{key: value for key, value in outcomes.items() if key != "outcome_artifact"}, "alternative_explanations": {"size": "UNRESOLVED_ALTERNATIVE_EXPLANATION / NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION", "sector": "UNRESOLVED_ALTERNATIVE_EXPLANATION / NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION", "execution_slippage": "UNRESOLVED_ALTERNATIVE_EXPLANATION", "limit_state": "LIMIT_STATE_EXECUTION_CLASSIFICATION_NOT_AVAILABLE", "items": ["generic_breakout_momentum", "low_volatility", "pre_compression_trend_strength", "market_regime", "board_composition", "liquidity_traded_amount", "new_listing_history_availability", "gap_news", "repeated_breakouts", "common_calendar_shocks", "universe_construction", "corporate_action_artifacts", "price_level_tick_size"]}, "transaction_cost": {"model": "TRANSACTION_COST_MODEL_NOT_PREEXISTING", "reported_returns": "gross"}, "governance": {"b_unchanged": True, "b_prospective_unchanged": True, "b_prospective_outcomes_accessed": False, "rs_unchanged": True, "volume_path_unchanged": True, "turnover_rv_unchanged": True, "c_read": False, "controlled_reversal_read": False, "final_oos_read": False, "forbidden_directory_touched": False, "automatic_follow_up_started": False, "parameter_tuning": False, "production_path_changed": False}}
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "new_volatility_contraction_breakout_v1_summary.json"
    report_path = output_dir / "new_volatility_contraction_breakout_v1_report.md"
    manifest_path = output_dir / "new_volatility_contraction_breakout_v1_manifest.json"
    write_json(summary_path, summary)
    report_path.write_text(_render_report(summary), encoding="utf-8", newline="\n")
    write_json(manifest_path, {"schema_version": MANIFEST_SCHEMA, "strategy": STRATEGY_VERSION, "protocol_commit_sha": PROTOCOL_COMMIT, "signal_artifact": signal["signal_artifact"], "outcome_detail_artifact": summary["artifacts"]["outcome_detail"], "summary_path": "docs/research/artifacts/new_volatility_contraction_breakout_v1_summary.json", "summary_sha256": file_sha256(summary_path), "report_path": "docs/research/artifacts/new_volatility_contraction_breakout_v1_report.md", "final_oos_read": False, "forbidden_directory_touched": False, "signal_sort": "date ascending, symbol ascending"})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("signal", "full"), default="signal")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/validation/core_signal_validation/raw"))
    parser.add_argument("--core-manifest", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"))
    parser.add_argument("--core-output", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_replay_results.jsonl.gz"))
    parser.add_argument("--b-membership", type=Path, default=Path("data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/research/artifacts"))
    parser.add_argument("--detail-dir", type=Path, default=Path("data/validation/new_volatility_contraction_breakout_v1"))
    parser.add_argument("--base", default="44544b831dfb12bc03bbc9efab49704f095cce1d")
    args = parser.parse_args()
    result = run(phase=args.phase, raw_dir=args.raw_dir, core_manifest_path=args.core_manifest, core_output_path=args.core_output, b_membership_path=args.b_membership, output_dir=args.output_dir, detail_dir=args.detail_dir, base=args.base)
    if args.phase == "full":
        print(json.dumps({"decision": result["decision"], "primary": result["primary"], "continuous": result["continuous"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
