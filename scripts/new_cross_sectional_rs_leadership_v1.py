"""Fixed, independent research evaluator for cross-sectional leadership V1.

The signal pass only reads the frozen T-close replay inputs.  The outcome pass is
separate and is enabled only after the committed pre-outcome protocol.  The
evaluator never imports a production/prospective watchlist path and never reads
Final OOS data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
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


STRATEGY_VERSION = "NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1"
PROTOCOL_COMMIT = "73d62f40fad92f1c85662136e50dc45fb78035bb"
SHORT_LOOKBACK = 20
MEDIUM_LOOKBACK = 60
TOP_QUINTILE = 0.20
BOOTSTRAP_BLOCK_LENGTH = 20
BOOTSTRAP_REPETITIONS = 5000
BOOTSTRAP_SEED = 20260906
PRIMARY_HORIZON = "10D"
SECONDARY_HORIZON = "5D"
MIN_SIGNAL_BARS = MEDIUM_LOOKBACK + 1
SIGNAL_SCHEMA = "RS_LEADERSHIP_SIGNAL_MEMBERSHIP_V1"
SUMMARY_SCHEMA = "RS_LEADERSHIP_RESEARCH_SUMMARY_V1"
MANIFEST_SCHEMA = "RS_LEADERSHIP_RESEARCH_MANIFEST_V1"
REPORT_SCHEMA = "RS_LEADERSHIP_RESEARCH_REPORT_V1"
VALID_CLASSES = ("CANDIDATE", "PRIMARY_CONTROL")
BOARDS = ("Main", "ChiNext", "STAR", "OUT_OF_SCOPE_PREFIX")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def trailing_return(closes: Sequence[float], lookback: int) -> float:
    """Return close[T]/close[T-lookback]-1 using exactly lookback+1 bars."""

    if len(closes) < lookback + 1:
        raise ValueError(f"{lookback}D return requires {lookback + 1} valid bars")
    current = float(closes[-1])
    prior = float(closes[-lookback - 1])
    if not _finite(current) or not _finite(prior) or current <= 0 or prior <= 0:
        raise ValueError("signal prices must be finite and positive")
    return current / prior - 1.0


def top_quintile_ranked(values: Mapping[str, float], fraction: float = TOP_QUINTILE) -> tuple[dict[str, int], set[str]]:
    """Return deterministic one-based descending ranks and exact top ceil(fraction*N)."""

    if not values:
        return {}, set()
    if fraction <= 0 or fraction > 1:
        raise ValueError("top-quintile fraction must be in (0, 1]")
    ordered = sorted(values.items(), key=lambda item: (-float(item[1]), item[0]))
    ranks = {symbol: index for index, (symbol, _value) in enumerate(ordered, start=1)}
    top_k = int(math.ceil(fraction * len(ordered)))
    return ranks, {symbol for symbol, _value in ordered[:top_k]}


def classify_membership(q20: set[str], q60: set[str]) -> dict[str, str]:
    """Classify exactly Q60 rows into candidate and primary-control sets."""

    candidate = q20 & q60
    control = q60 - q20
    if candidate & control or not candidate <= q60:
        raise AssertionError("candidate/control membership invariant failed")
    return {symbol: "CANDIDATE" for symbol in candidate} | {symbol: "PRIMARY_CONTROL" for symbol in control}


def _pct(values: Sequence[float] | np.ndarray) -> list[float]:
    return [float(value) * 100.0 for value in values]


def realized_volatility_20d_pct(closes: Sequence[float]) -> float:
    """Sample stdev of 20 valid one-session close returns, in percentage points."""

    if len(closes) < SHORT_LOOKBACK + 1:
        raise ValueError("20D realized volatility requires 21 valid bars")
    values = np.asarray(closes[-SHORT_LOOKBACK - 1 :], dtype=float)
    returns = values[1:] / values[:-1] - 1.0
    return float(np.std(returns * 100.0, ddof=1))


def median_traded_amount_20d(turnover: Sequence[float]) -> float:
    if len(turnover) < SHORT_LOOKBACK:
        raise ValueError("20D traded amount requires 20 valid bars")
    values = np.asarray(turnover[-SHORT_LOOKBACK:], dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("traded amount must be finite and non-negative")
    return float(np.median(values))


def _rankdata(values: Sequence[float]) -> np.ndarray:
    """Average ranks, one-based, with deterministic equality handling."""

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
    x = _rankdata(values_x)
    y = _rankdata(values_y)
    x_centered = x - np.mean(x)
    y_centered = y - np.mean(y)
    denominator = float(np.sqrt(np.sum(x_centered * x_centered) * np.sum(y_centered * y_centered)))
    if denominator == 0:
        return None
    return float(np.sum(x_centered * y_centered) / denominator)


def moving_block_bootstrap_ci(
    values: Sequence[float],
    *,
    block_length: int = BOOTSTRAP_BLOCK_LENGTH,
    repetitions: int = BOOTSTRAP_REPETITIONS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Non-circular moving-block bootstrap over an ordered date series."""

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


def _summary_stats(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "positive_rate": None, "mfe_mean": None, "mae_mean": None}
    return {
        "n": len(values),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "positive_rate": float(np.mean(np.asarray(values) > 0)),
    }


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "p25": None, "p75": None}
    array = np.asarray(values, dtype=float)
    return {
        "n": int(len(array)),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "p25": float(np.quantile(array, 0.25)),
        "p75": float(np.quantile(array, 0.75)),
    }


def _write_jsonl_gzip(path: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_digest = hashlib.sha256()
    content_digest = hashlib.sha256()
    count = 0
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            for row in rows:
                line = (canonical_json(dict(row)) + "\n").encode("utf-8")
                compressed.write(line)
                content_digest.update(line)
                count += 1
    file_digest.update(path.read_bytes())
    return {
        "path": path.as_posix(),
        "rows": count,
        "bytes": path.stat().st_size,
        "sha256": file_digest.hexdigest(),
        "content_sha256": content_digest.hexdigest(),
    }


def _iter_jsonl_gzip(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


@dataclass(frozen=True)
class SignalPassResult:
    per_date: dict[str, dict[str, Any]]
    signal_artifact: dict[str, Any]
    signal_rows: int
    b_overlap: dict[str, Any]


def _next_execution_date(signal_date: str, session_dates: Sequence[str]) -> str | None:
    try:
        index = session_dates.index(signal_date)
    except ValueError as exc:
        raise RuntimeError(f"signal date is not in XSHG calendar: {signal_date}") from exc
    return session_dates[index + 1] if index + 1 < len(session_dates) else None


def _load_b_membership(path: Path) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    """Read only signal_date/symbol membership from the B event stream.

    The event stream may contain outcome fields for its own development record.
    They are intentionally not accessed, copied, or used here.
    """

    memberships: set[tuple[str, str]] = set()
    rows = 0
    for record in _iter_jsonl_gzip(path):
        rows += 1
        signal_date = record.get("signal_date")
        symbol = record.get("symbol")
        if isinstance(signal_date, str) and isinstance(symbol, str):
            memberships.add((signal_date, symbol.lower()))
    return memberships, {
        "logical_path": path.as_posix(),
        "rows_read_for_signal_membership": rows,
        "unique_signal_memberships": len(memberships),
        "file_sha256": file_sha256(path),
        "outcomes_accessed": False,
    }


def _input_audit(raw_dir: Path, core_manifest_path: Path, core_output_path: Path) -> dict[str, Any]:
    core_manifest = json.loads(core_manifest_path.read_text(encoding="utf-8"))
    index_dates, _index_bars, index_meta = replay._load_index(raw_dir)
    store, stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    signal_dates = replay._continuous_signal_dates(index_dates)
    coverage = replay._coverage_by_date(store, signal_dates, index_dates)
    counts = [item["evaluable_symbol_count"] for item in coverage.values()]
    raw_counts = [item["raw_symbol_count_at_T"] for item in coverage.values()]
    source = core_manifest["provenance"]
    expected_rows = int(core_manifest["replay"]["candidate_evaluations"])
    if sum(counts) != expected_rows:
        raise RuntimeError("RS_LEADERSHIP_INPUT_PROVENANCE_CONFLICT: replay count mismatch")
    if file_sha256(raw_dir / "daily_k.parquet") != source["raw_inputs"]["files"][0]["sha256"]:
        raise RuntimeError("RS_LEADERSHIP_INPUT_PROVENANCE_CONFLICT: daily_k hash mismatch")
    if file_sha256(raw_dir / "adjustment_factors.parquet") != source["raw_inputs"]["files"][1]["sha256"]:
        raise RuntimeError("RS_LEADERSHIP_INPUT_PROVENANCE_CONFLICT: adjustment hash mismatch")
    if file_sha256(core_output_path) != "0d23cf54843920f5fdcc05847e4b78c5d605b05c8793f878b6021c85b3ab0c2f":
        raise RuntimeError("RS_LEADERSHIP_INPUT_PROVENANCE_CONFLICT: core output hash mismatch")
    return {
        "status": "PASS",
        "historical_pit_universe": {
            "source": "existing continuous replay universe",
            "sessions": len(signal_dates),
            "first_session": signal_dates[0],
            "last_session": signal_dates[-1],
            "candidate_evaluations": expected_rows,
            "per_session_min": min(counts),
            "per_session_max": max(counts),
            "per_session_mean": float(np.mean(counts)),
            "per_session_median": float(np.median(counts)),
            "raw_t_day_min": min(raw_counts),
            "raw_t_day_max": max(raw_counts),
            "semantics": core_manifest["universe_semantics"],
            "listing_handling": "T-day raw row plus >=120 valid bars; no current backfill",
            "missing_history_handling": "symbol-date exclusion; no interpolation or session deletion",
            "board_identity": "Main=00/60; ChiNext=30; STAR=68; other prefixes retained and reported separately",
            "identity_source_sha256": "dbc5d220f24f51a0245d047b88733c961fc4f184d02ef6f5ac0fc795576217b0",
        },
        "signal_price_basis": {
            "semantics": core_manifest["adjustment_semantics"],
            "daily_k_sha256": source["raw_inputs"]["files"][0]["sha256"],
            "adjustment_factors_sha256": source["raw_inputs"]["files"][1]["sha256"],
            "known_at_vintage_proof": source["known_at_vintage_proof"],
            "future_events_excluded": True,
        },
        "calendar": {
            "benchmark_rows": index_meta["row_count"],
            "benchmark_files": index_meta["files"],
            "schedule": core_manifest["signal_date_schedule"],
        },
        "raw_stock_meta": stock_meta,
        "common_benchmark_subtraction": "COMMON_BENCHMARK_SUBTRACTION_IS_RANK_INVARIANT",
        "final_oos_read": False,
        "forbidden_directory_touched": False,
    }


def _signal_pass(
    *,
    raw_dir: Path,
    core_manifest_path: Path,
    core_output_path: Path,
    b_membership_path: Path,
    signal_path: Path,
) -> SignalPassResult:
    audit = _input_audit(raw_dir, core_manifest_path, core_output_path)
    index_dates, _index_bars, _index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    signal_dates = [date for date in session_dates if replay.VALIDATION_START <= date <= replay.VALIDATION_END]
    store, _stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")
    b_memberships, b_source = _load_b_membership(b_membership_path)
    per_date: dict[str, dict[str, Any]] = {}
    signal_rows = 0
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    content_digest = hashlib.sha256()
    with signal_path.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0) as compressed:
            for date_index, signal_date in enumerate(signal_dates):
                anchor_ms = index_dates[signal_date]
                eligible_symbols, numeric_bars = replay._numeric_bars_for_date(store, signal_date, anchor_ms, events)
                r20: dict[str, float] = {}
                r60: dict[str, float] = {}
                diagnostics: dict[str, tuple[float, float]] = {}
                insufficient = 0
                for symbol in eligible_symbols:
                    closes, _volume, _high, _low = numeric_bars[symbol]
                    try:
                        short = trailing_return(closes, SHORT_LOOKBACK)
                        medium = trailing_return(closes, MEDIUM_LOOKBACK)
                        vol = realized_volatility_20d_pct(closes)
                        amount = median_traded_amount_20d(store["turnover"][store["bounds"][symbol][0] : store["bounds"][symbol][1]][-SHORT_LOOKBACK:])
                    except ValueError:
                        insufficient += 1
                        continue
                    r20[symbol] = short
                    r60[symbol] = medium
                    diagnostics[symbol] = (vol, amount)
                valid_symbols = set(r20) & set(r60)
                if set(r20) != valid_symbols or set(r60) != valid_symbols:
                    raise RuntimeError("R20/R60 valid participant sets diverged")
                rank20, q20 = top_quintile_ranked(r20)
                rank60, q60 = top_quintile_ranked(r60)
                classes = classify_membership(q20, q60)
                if q20 & q60 != set(classes):
                    raise RuntimeError("candidate/control membership accounting mismatch")
                rows_for_date: list[dict[str, Any]] = []
                execution_date = _next_execution_date(signal_date, session_dates)
                for symbol in sorted(classes):
                    row = {
                        "as_of_date": signal_date,
                        "signal_date": signal_date,
                        "earliest_execution_date": execution_date,
                        "symbol": symbol,
                        "board": _board(symbol),
                        "r20": r20[symbol],
                        "r60": r60[symbol],
                        "rank20": rank20[symbol],
                        "rank60": rank60[symbol],
                        "q20_leader": symbol in q20,
                        "q60_leader": symbol in q60,
                        "classification": classes[symbol],
                        "realized_volatility_20d_pct": diagnostics[symbol][0],
                        "median_traded_amount_20d": diagnostics[symbol][1],
                        "b_signal_membership": (signal_date, symbol) in b_memberships,
                    }
                    rows_for_date.append(row)
                for row in rows_for_date:
                    line = (canonical_json(row) + "\n").encode("utf-8")
                    compressed.write(line)
                    content_digest.update(line)
                    signal_rows += 1
                per_date[signal_date] = {
                    "signal_date": signal_date,
                    "eligible_n": len(eligible_symbols),
                    "valid_r20_n": len(r20),
                    "valid_r60_n": len(r60),
                    "q20_n": len(q20),
                    "q60_n": len(q60),
                    "candidate_n": sum(value == "CANDIDATE" for value in classes.values()),
                    "primary_control_n": sum(value == "PRIMARY_CONTROL" for value in classes.values()),
                    "insufficient_history_n": insufficient,
                    "candidate_symbols": [row["symbol"] for row in rows_for_date if row["classification"] == "CANDIDATE"],
                    "control_symbols": [row["symbol"] for row in rows_for_date if row["classification"] == "PRIMARY_CONTROL"],
                }
                if date_index % 100 == 0:
                    print(f"signal pass {date_index + 1}/{len(signal_dates)} {signal_date}", flush=True)
    signal_artifact = {
        "logical_path": "local-only/new_cross_sectional_relative_strength_leadership_v1_signal_membership.jsonl.gz",
        "rows": signal_rows,
        "bytes": signal_path.stat().st_size,
        "file_sha256": file_sha256(signal_path),
        "content_sha256": content_digest.hexdigest(),
    }
    candidate_pairs = {(date, symbol) for date, values in per_date.items() for symbol in values["candidate_symbols"]}
    control_pairs = {(date, symbol) for date, values in per_date.items() for symbol in values["control_symbols"]}
    overlap = len(candidate_pairs & b_memberships)
    b_in_scope = {pair for pair in b_memberships if pair[0] in per_date}
    b_overlap = {
        "source": b_source,
        "same_date_overlap": overlap,
        "same_symbol_date_overlap": overlap,
        "candidate_share_overlapping_b": overlap / len(candidate_pairs) if candidate_pairs else None,
        "b_share_overlapping_candidate": overlap / len(b_in_scope) if b_in_scope else None,
        "b_memberships_in_research_dates": len(b_in_scope),
    }
    if not per_date:
        raise RuntimeError("RS_LEADERSHIP_SIGNAL_CONSTRUCTION_NOT_RESEARCH_READY: no signal dates")
    candidate_active = sum(values["candidate_n"] > 0 for values in per_date.values())
    control_active = sum(values["primary_control_n"] > 0 for values in per_date.values())
    if candidate_active / len(per_date) < 0.98 or control_active / len(per_date) < 0.98:
        raise RuntimeError("RS_LEADERSHIP_SIGNAL_CONSTRUCTION_NOT_RESEARCH_READY")
    return SignalPassResult(per_date=per_date, signal_artifact=signal_artifact, signal_rows=signal_rows, b_overlap=b_overlap)


def _outcome_record(row: Mapping[str, Any], store: dict[str, Any], events: dict[str, list[tuple[int, float, float, float, float]]], session_dates: list[str], session_ms: np.ndarray, session_index: dict[str, int]) -> dict[str, Any]:
    return returns_v2._build_event_record(
        row={
            "as_of_date": row["as_of_date"],
            "signal_date": row["signal_date"],
            "earliest_execution_date": row["earliest_execution_date"],
            "symbol": row["symbol"],
            "setup_id": STRATEGY_VERSION,
        },
        store=store,
        events=events,
        session_dates=session_dates,
        session_ms=session_ms,
        session_index=session_index,
    )


def _empty_horizon_state() -> dict[str, Any]:
    return {
        "status_counts": Counter(),
        "returns": [],
        "mfe": [],
        "mae": [],
    }


def _event_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    values = state["returns"]
    result = _summary_stats(values)
    result["status_counts"] = dict(sorted(state["status_counts"].items()))
    result["mfe_mean"] = float(np.mean(state["mfe"])) if state["mfe"] else None
    result["mfe_median"] = float(np.median(state["mfe"])) if state["mfe"] else None
    result["mae_mean"] = float(np.mean(state["mae"])) if state["mae"] else None
    result["mae_median"] = float(np.median(state["mae"])) if state["mae"] else None
    return result


def _update_horizon(state: dict[str, Any], outcome: Mapping[str, Any]) -> None:
    status = str(outcome["status"])
    state["status_counts"][status] += 1
    if status == "AVAILABLE":
        state["returns"].append(float(outcome["return_pct"]))
        state["mfe"].append(float(outcome["mfe_pct"]))
        state["mae"].append(float(outcome["mae_pct"]))


def _process_outcome_date(
    rows: list[dict[str, Any]],
    *,
    store: dict[str, Any],
    events: dict[str, list[tuple[int, float, float, float, float]]],
    session_dates: list[str],
    session_ms: np.ndarray,
    session_index: dict[str, int],
    detail_handle: gzip.GzipFile,
    states: dict[str, dict[str, dict[str, Any]]],
    daily_rows: list[dict[str, Any]],
    continuous_rhos: list[dict[str, Any]],
    board_states: dict[str, dict[str, dict[str, Any]]],
    vol_values: dict[str, list[float]],
    amount_values: dict[str, list[float]],
    symbol_counts: dict[str, Counter[str]],
    month_counts: Counter[str],
    run_state: dict[tuple[str, str], tuple[int, int]],
    run_lengths: dict[str, list[int]],
    date_index: int,
) -> None:
    if not rows:
        return
    signal_date = rows[0]["signal_date"]
    class_returns: dict[str, dict[str, list[float]]] = {class_name: {h: [] for h in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for class_name in VALID_CLASSES}
    q60_ranks: list[float] = []
    q60_returns: list[float] = []
    for row in rows:
        class_name = row["classification"]
        outcome_record = _outcome_record(row, store, events, session_dates, session_ms, session_index)
        detail = dict(row)
        detail["outcomes"] = {h: outcome_record["outcomes"][h] for h in (SECONDARY_HORIZON, PRIMARY_HORIZON)}
        encoded = (canonical_json(detail) + "\n").encode("utf-8")
        detail_handle.write(encoded)
        for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON):
            outcome = outcome_record["outcomes"][horizon]
            _update_horizon(states[class_name][horizon], outcome)
            board_states[row["board"]][class_name][horizon]["all"].append(outcome)
            if outcome["status"] == "AVAILABLE":
                class_returns[class_name][horizon].append(float(outcome["return_pct"]))
                if horizon == PRIMARY_HORIZON:
                    q60_ranks.append(float(row["rank20"]))
                    q60_returns.append(float(outcome["return_pct"]))
        vol_values[class_name].append(float(row["realized_volatility_20d_pct"]))
        amount_values[class_name].append(float(row["median_traded_amount_20d"]))
        symbol_counts[class_name][row["symbol"]] += 1
        month_counts[f"{signal_date[:7]}:{class_name}"] += 1
        key = (class_name, row["symbol"])
        previous = run_state.get(key)
        if previous is None or previous[0] != date_index - 1:
            if previous is not None:
                run_lengths[class_name].append(previous[1])
            run_state[key] = (date_index, 1)
        else:
            run_state[key] = (date_index, previous[1] + 1)
    means = {class_name: {h: (float(np.mean(values)) if values else None) for h, values in class_values.items()} for class_name, class_values in class_returns.items()}
    daily = {
        "signal_date": signal_date,
        "candidate_n": sum(row["classification"] == "CANDIDATE" for row in rows),
        "primary_control_n": sum(row["classification"] == "PRIMARY_CONTROL" for row in rows),
        "candidate_mean_5D": means["CANDIDATE"][SECONDARY_HORIZON],
        "control_mean_5D": means["PRIMARY_CONTROL"][SECONDARY_HORIZON],
        "spread_5D": None,
        "candidate_mean_10D": means["CANDIDATE"][PRIMARY_HORIZON],
        "control_mean_10D": means["PRIMARY_CONTROL"][PRIMARY_HORIZON],
        "spread_10D": None,
        "q60_available_10D_n": len(q60_returns),
    }
    if means["CANDIDATE"][SECONDARY_HORIZON] is not None and means["PRIMARY_CONTROL"][SECONDARY_HORIZON] is not None:
        daily["spread_5D"] = means["CANDIDATE"][SECONDARY_HORIZON] - means["PRIMARY_CONTROL"][SECONDARY_HORIZON]
    if means["CANDIDATE"][PRIMARY_HORIZON] is not None and means["PRIMARY_CONTROL"][PRIMARY_HORIZON] is not None:
        daily["spread_10D"] = means["CANDIDATE"][PRIMARY_HORIZON] - means["PRIMARY_CONTROL"][PRIMARY_HORIZON]
    daily_rows.append(daily)
    rho = spearman(q60_ranks, q60_returns)
    if rho is not None:
        continuous_rhos.append({"signal_date": signal_date, "rho": rho, "n": len(q60_returns)})


def _finalize_runs(run_state: Mapping[tuple[str, str], tuple[int, int]], run_lengths: dict[str, list[int]]) -> None:
    for class_name, _symbol in run_state:
        run_lengths[class_name].append(run_state[(class_name, _symbol)][1])


def _state_summary(states: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    return {
        class_name: {horizon: _event_summary(state) for horizon, state in horizons.items()}
        for class_name, horizons in states.items()
    }


def _run_summary(values: Sequence[int]) -> dict[str, Any]:
    return {
        "run_count": len(values),
        "mean_run_length": float(np.mean(values)) if values else None,
        "median_run_length": float(np.median(values)) if values else None,
        "max_run_length": max(values) if values else None,
    }


def _board_summary(board_states: Mapping[str, Mapping[str, Mapping[str, Mapping[str, list[Mapping[str, Any]]]]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for board, class_states in board_states.items():
        result[board] = {}
        for class_name, horizon_states in class_states.items():
            result[board][class_name] = {}
            for horizon, values in horizon_states.items():
                available = [float(item["return_pct"]) for item in values["all"] if item["status"] == "AVAILABLE"]
                result[board][class_name][horizon] = _summary_stats(available)
    return result


def _year_summary(daily_rows: Sequence[Mapping[str, Any]], horizon: str) -> dict[str, Any]:
    field = "spread_10D" if horizon == PRIMARY_HORIZON else "spread_5D"
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in daily_rows:
        value = row.get(field)
        if value is not None:
            grouped[row["signal_date"][:4]].append(float(value))
    result = {}
    for year in ("2023", "2024", "2025", "2026"):
        values = grouped.get(year, [])
        result[year] = {
            "n_dates": len(values),
            "mean_spread": float(np.mean(values)) if values else None,
            "median_spread": float(np.median(values)) if values else None,
            "positive_dates": int(sum(value > 0 for value in values)),
            "positive_rate": float(np.mean(np.asarray(values) > 0)) if values else None,
        }
    return result


def _monthly_summary(daily_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in daily_rows:
        if row.get("spread_10D") is not None:
            grouped[row["signal_date"][:7]].append(float(row["spread_10D"]))
    return {
        month: {
            "n_dates": len(values),
            "mean_spread_10D": float(np.mean(values)),
            "positive_dates": int(sum(value > 0 for value in values)),
        }
        for month, values in sorted(grouped.items())
    }


def _decision(primary: Mapping[str, Any], continuous: Mapping[str, Any], years: Mapping[str, Mapping[str, Any]]) -> str:
    mean = primary.get("mean_spread_10D")
    ci = primary.get("moving_block_bootstrap_ci_95") or [None, None]
    rho = continuous.get("mean_daily_rho")
    coverage_ok = bool(primary.get("both_groups_available_date_rate", 0.0) >= 0.98)
    positive_years = sum((years[year].get("mean_spread") or 0.0) > 0 for year in years)
    if ci[1] is not None and ci[1] <= 0:
        return "RS_LEADERSHIP_NO_CLEAR_INCREMENTAL_SIGNAL"
    if mean is not None and mean <= 0 and rho is not None and rho <= 0:
        return "RS_LEADERSHIP_NO_CLEAR_INCREMENTAL_SIGNAL"
    if (
        mean is not None
        and mean > 0
        and ci[0] is not None
        and ci[0] > 0
        and rho is not None
        and rho > 0
        and coverage_ok
        and positive_years >= 3
    ):
        return "RS_LEADERSHIP_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION"
    return "RS_LEADERSHIP_NEEDS_MORE_EVIDENCE"


def _render_report(summary: Mapping[str, Any]) -> str:
    primary = summary["primary"]
    decision = summary["decision"]
    ci = primary["moving_block_bootstrap_ci_95"]
    lines = [
        "# NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1 — research report",
        "",
        f"Decision: `{decision}`",
        "",
        "This is DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DIAGNOSTIC_ONLY evidence. It is not production, a frozen candidate, causal mechanism evidence, or Final OOS.",
        "",
        "## Fixed identity",
        "",
        f"- Protocol commit: `{summary['protocol']['commit_sha']}`.",
        f"- Sessions: {summary['signal_only']['sessions']} ({summary['signal_only']['first_session']} to {summary['signal_only']['last_session']}).",
        f"- Signal rows: {summary['artifacts']['signal_membership']['rows']} (candidate/control Q60 membership only).",
        f"- Candidate active sessions: {summary['signal_only']['candidate_active_sessions']}; primary-control active sessions: {summary['signal_only']['control_active_sessions']}.",
        "- Rule: fixed R20/R60, descending rank, exact symbol tie-break, top 20%, candidate=Q20∩Q60, control=Q60\\Q20.",
        "",
        "## Primary result",
        "",
        f"- 10D equal-weight mean date spread (candidate minus primary control): {primary['mean_spread_10D']} percentage points.",
        f"- Median date spread: {primary['median_spread_10D']} percentage points.",
        f"- 95% 20-session moving-block-bootstrap CI: [{ci[0]}, {ci[1]}].",
        f"- Positive-spread date rate: {primary['positive_spread_date_rate_10D']}.",
        f"- Dates with both groups available: {primary['both_groups_available_dates']} / {primary['spread_date_count']}.",
        "",
        "## Secondary and robustness",
        "",
        f"- Equal-weight mean daily Spearman(R20 rank, future 10D return) within Q60: {summary['continuous_rank_check']['mean_daily_rho']}.",
        f"- 5D analogue mean date spread: {summary['secondary_5D']['mean_spread_5D']} percentage points.",
        f"- Calendar-year diagnostics: {json.dumps(summary['year_diagnostics'], ensure_ascii=False, sort_keys=True)}",
        f"- Board diagnostics: {json.dumps(summary['board_diagnostics'], ensure_ascii=False, sort_keys=True)}",
        "",
        "## Input and execution boundaries",
        "",
        "- Signal input audit: PASS; existing date-anchored replay universe and validated T-anchor signal prices.",
        "- Reference entry: T+1 XSHG open; not an actual fill.",
        f"- Execution coverage: {json.dumps(summary['execution_coverage'], ensure_ascii=False, sort_keys=True)}",
        "- Historical PIT size and sector explanations: unresolved/not available for this V1 identification.",
        f"- B signal overlap (membership only): {json.dumps(summary['b_signal_overlap'], ensure_ascii=False, sort_keys=True)}",
        "- Transaction-cost model: not pre-existing; returns are gross and break-even cost is not a tradability guarantee.",
        "",
        "## Governance",
        "",
        "B, B prospective observation, Volume-Path, turnover/RV, C, production path, frozen state, and Final OOS were not modified/read for this research. No automatic follow-up was started.",
    ]
    return "\n".join(lines) + "\n"


def run(
    *,
    raw_dir: Path,
    core_manifest_path: Path,
    core_output_path: Path,
    b_membership_path: Path,
    output_dir: Path,
    detail_dir: Path,
) -> dict[str, Any]:
    if any("final_oos" in str(path).lower() for path in (raw_dir, core_manifest_path, core_output_path, b_membership_path, output_dir, detail_dir)):
        raise RuntimeError("Final OOS path is forbidden")
    protocol_path = Path("docs/research/new_cross_sectional_relative_strength_leadership_v1_protocol.md")
    if not protocol_path.exists() or PROTOCOL_COMMIT not in protocol_path.read_text(encoding="utf-8"):
        raise RuntimeError("pre-outcome protocol commit identity is missing")
    detail_dir.mkdir(parents=True, exist_ok=True)
    signal_path = detail_dir / "new_cross_sectional_relative_strength_leadership_v1_signal_membership.jsonl.gz"
    outcome_path = detail_dir / "new_cross_sectional_relative_strength_leadership_v1_outcomes.jsonl.gz"
    signal_result = _signal_pass(
        raw_dir=raw_dir,
        core_manifest_path=core_manifest_path,
        core_output_path=core_output_path,
        b_membership_path=b_membership_path,
        signal_path=signal_path,
    )
    per_date = signal_result.per_date
    states = {class_name: {horizon: _empty_horizon_state() for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for class_name in VALID_CLASSES}
    board_states = {board: {class_name: {horizon: {"all": []} for horizon in (SECONDARY_HORIZON, PRIMARY_HORIZON)} for class_name in VALID_CLASSES} for board in BOARDS}
    vol_values = {class_name: [] for class_name in VALID_CLASSES}
    amount_values = {class_name: [] for class_name in VALID_CLASSES}
    symbol_counts = {class_name: Counter() for class_name in VALID_CLASSES}
    month_counts: Counter[str] = Counter()
    run_state: dict[tuple[str, str], tuple[int, int]] = {}
    run_lengths: dict[str, list[int]] = {class_name: [] for class_name in VALID_CLASSES}
    daily_rows: list[dict[str, Any]] = []
    continuous_rhos: list[dict[str, Any]] = []
    index_dates, _index_bars, _index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.asarray([index_dates[date] for date in session_dates], dtype=np.int64)
    session_index = {date: index for index, date in enumerate(session_dates)}
    store, _stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")
    detail_digest = hashlib.sha256()
    current_date: str | None = None
    current_rows: list[dict[str, Any]] = []
    detail_dir.mkdir(parents=True, exist_ok=True)
    with outcome_path.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0) as detail_handle:
            for row in _iter_jsonl_gzip(signal_path):
                if current_date is None:
                    current_date = row["signal_date"]
                if row["signal_date"] != current_date:
                    _process_outcome_date(
                        current_rows,
                        store=store,
                        events=events,
                        session_dates=session_dates,
                        session_ms=session_ms,
                        session_index=session_index,
                        detail_handle=detail_handle,
                        states=states,
                        daily_rows=daily_rows,
                        continuous_rhos=continuous_rhos,
                        board_states=board_states,
                        vol_values=vol_values,
                        amount_values=amount_values,
                        symbol_counts=symbol_counts,
                        month_counts=month_counts,
                        run_state=run_state,
                        run_lengths=run_lengths,
                        date_index=session_index[current_date],
                    )
                    current_rows = []
                    current_date = row["signal_date"]
                current_rows.append(row)
            _process_outcome_date(
                current_rows,
                store=store,
                events=events,
                session_dates=session_dates,
                session_ms=session_ms,
                session_index=session_index,
                detail_handle=detail_handle,
                states=states,
                daily_rows=daily_rows,
                continuous_rhos=continuous_rhos,
                board_states=board_states,
                vol_values=vol_values,
                amount_values=amount_values,
                symbol_counts=symbol_counts,
                month_counts=month_counts,
                run_state=run_state,
                run_lengths=run_lengths,
                date_index=session_index[current_date] if current_date is not None else 0,
            )
    _finalize_runs(run_state, run_lengths)
    available_spreads_10d = [float(row["spread_10D"]) for row in daily_rows if row["spread_10D"] is not None]
    available_spreads_5d = [float(row["spread_5D"]) for row in daily_rows if row["spread_5D"] is not None]
    ci_10d = moving_block_bootstrap_ci(available_spreads_10d) if len(available_spreads_10d) >= BOOTSTRAP_BLOCK_LENGTH else (None, None)
    ci_5d = moving_block_bootstrap_ci(available_spreads_5d) if len(available_spreads_5d) >= BOOTSTRAP_BLOCK_LENGTH else (None, None)
    mean_rho = float(np.mean([item["rho"] for item in continuous_rhos])) if continuous_rhos else None
    median_rho = float(np.median([item["rho"] for item in continuous_rhos])) if continuous_rhos else None
    primary = {
        "mean_spread_10D": float(np.mean(available_spreads_10d)) if available_spreads_10d else None,
        "median_spread_10D": float(np.median(available_spreads_10d)) if available_spreads_10d else None,
        "moving_block_bootstrap_ci_95": list(ci_10d) if ci_10d[0] is not None else [None, None],
        "positive_spread_date_rate_10D": float(np.mean(np.asarray(available_spreads_10d) > 0)) if available_spreads_10d else None,
        "both_groups_available_dates": len(available_spreads_10d),
        "spread_date_count": len(daily_rows),
        "both_groups_available_date_rate": len(available_spreads_10d) / len(daily_rows) if daily_rows else 0.0,
    }
    secondary = {
        "mean_spread_5D": float(np.mean(available_spreads_5d)) if available_spreads_5d else None,
        "median_spread_5D": float(np.median(available_spreads_5d)) if available_spreads_5d else None,
        "moving_block_bootstrap_ci_95": list(ci_5d) if ci_5d[0] is not None else [None, None],
        "positive_spread_date_rate_5D": float(np.mean(np.asarray(available_spreads_5d) > 0)) if available_spreads_5d else None,
    }
    signal_only = {
        "sessions": len(per_date),
        "first_session": min(per_date),
        "last_session": max(per_date),
        "candidate_active_sessions": sum(item["candidate_n"] > 0 for item in per_date.values()),
        "control_active_sessions": sum(item["primary_control_n"] > 0 for item in per_date.values()),
        "eligible_symbol_dates": sum(item["eligible_n"] for item in per_date.values()),
        "valid_r20_symbol_dates": sum(item["valid_r20_n"] for item in per_date.values()),
        "valid_r60_symbol_dates": sum(item["valid_r60_n"] for item in per_date.values()),
        "q20_symbol_dates": sum(item["q20_n"] for item in per_date.values()),
        "q60_symbol_dates": sum(item["q60_n"] for item in per_date.values()),
        "candidate_symbol_dates": sum(item["candidate_n"] for item in per_date.values()),
        "primary_control_symbol_dates": sum(item["primary_control_n"] for item in per_date.values()),
        "insufficient_history_symbol_dates": sum(item["insufficient_history_n"] for item in per_date.values()),
        "coverage_gate": "PASS",
    }
    execution_coverage = _state_summary(states)
    years = _year_summary(daily_rows, PRIMARY_HORIZON)
    decision = _decision(primary, {"mean_daily_rho": mean_rho}, years)
    top_symbols = {}
    for class_name, counts in symbol_counts.items():
        total = sum(counts.values())
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        shares = [count / total for _symbol, count in ordered] if total else []
        top_symbols[class_name] = {
            "unique_symbols": len(counts),
            "top1_share": shares[0] if shares else None,
            "top5_share": sum(shares[:5]) if shares else None,
            "hhi": sum(value * value for value in shares),
            "top10": [{"symbol": symbol, "count": count} for symbol, count in ordered[:10]],
        }
    best = max(daily_rows, key=lambda row: row["spread_10D"] if row["spread_10D"] is not None else -float("inf")) if available_spreads_10d else None
    worst = min(daily_rows, key=lambda row: row["spread_10D"] if row["spread_10D"] is not None else float("inf")) if available_spreads_10d else None
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA,
        "strategy": STRATEGY_VERSION,
        "protocol": {"commit_sha": PROTOCOL_COMMIT, "status": "PRE_OUTCOME_PROTOCOL_COMMITTED"},
        "labels": ["DEVELOPMENT", "RECONSTRUCTED_RETROSPECTIVE", "DATE_ANCHORED", "DIAGNOSTIC_ONLY", "NEW_RESEARCH_HYPOTHESIS", "FINAL_OOS_UNREAD"],
        "input_audit": _input_audit(raw_dir, core_manifest_path, core_output_path),
        "signal_only": signal_only,
        "artifacts": {
            "signal_membership": signal_result.signal_artifact,
            "outcome_detail": {
                "logical_path": "local-only/new_cross_sectional_relative_strength_leadership_v1_outcomes.jsonl.gz",
                "rows": sum(sum(item["status_counts"].values()) for class_states in states.values() for item in class_states.values()) // 2,
                "bytes": outcome_path.stat().st_size,
                "file_sha256": file_sha256(outcome_path),
            },
        },
        "fixed_signal": {
            "short_lookback": SHORT_LOOKBACK,
            "medium_lookback": MEDIUM_LOOKBACK,
            "top_fraction": TOP_QUINTILE,
            "rank_tie_break": "symbol ascending",
            "candidate": "Q20_LEADER intersection Q60_LEADER",
            "primary_control": "Q60_LEADER minus Q20_LEADER",
            "common_benchmark_subtraction": "rank invariant and not used",
        },
        "b_signal_overlap": signal_result.b_overlap,
        "primary": primary,
        "secondary_5D": secondary,
        "continuous_rank_check": {
            "mean_daily_rho": mean_rho,
            "median_daily_rho": median_rho,
            "dates_with_rho": len(continuous_rhos),
        },
        "execution_coverage": execution_coverage,
        "year_diagnostics": years,
        "board_diagnostics": _board_summary(board_states),
        "volatility_distribution": {class_name: _distribution(values) for class_name, values in vol_values.items()},
        "median_traded_amount_distribution": {class_name: _distribution(values) for class_name, values in amount_values.items()},
        "membership_persistence": {class_name: _run_summary(values) for class_name, values in run_lengths.items()},
        "symbol_concentration": top_symbols,
        "monthly_concentration": _monthly_summary(daily_rows),
        "best_worst_signal_dates": {"best_10D": best, "worst_10D": worst},
        "alternative_explanations": {
            "size": "UNRESOLVED_ALTERNATIVE_EXPLANATION / NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION",
            "sector": "UNRESOLVED_ALTERNATIVE_EXPLANATION / NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION",
            "others": ["generic_60D_momentum", "short_term_20D_momentum", "market_regime", "board_composition", "volatility", "liquidity", "new_listing_history_availability", "repeated_membership", "common_calendar_shock", "universe_construction"],
        },
        "transaction_cost": {"model": "TRANSACTION_COST_MODEL_NOT_PREEXISTING", "reported_returns": "gross"},
        "decision": decision,
        "governance": {
            "b_unchanged": True,
            "b_prospective_outcomes_accessed": False,
            "volume_path_unchanged": True,
            "turnover_rv_unchanged": True,
            "c_read": False,
            "final_oos_read": False,
            "forbidden_directory_touched": False,
            "automatic_follow_up_started": False,
        },
    }
    report = _render_report(summary)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "new_cross_sectional_relative_strength_leadership_v1_summary.json", summary)
    write_json(output_dir / "new_cross_sectional_relative_strength_leadership_v1_manifest.json", {
        "schema_version": MANIFEST_SCHEMA,
        "strategy": STRATEGY_VERSION,
        "protocol_commit_sha": PROTOCOL_COMMIT,
        "signal_artifact": signal_result.signal_artifact,
        "outcome_detail_artifact": summary["artifacts"]["outcome_detail"],
        "summary_path": "docs/research/artifacts/new_cross_sectional_relative_strength_leadership_v1_summary.json",
        "summary_sha256": file_sha256(output_dir / "new_cross_sectional_relative_strength_leadership_v1_summary.json"),
        "report_path": "docs/research/artifacts/new_cross_sectional_relative_strength_leadership_v1_report.md",
        "final_oos_read": False,
        "forbidden_directory_touched": False,
    })
    (output_dir / "new_cross_sectional_relative_strength_leadership_v1_report.md").write_text(report, encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=Path("data/validation/core_signal_validation/raw"))
    parser.add_argument("--core-manifest", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"))
    parser.add_argument("--core-output", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_replay_results.jsonl.gz"))
    parser.add_argument("--b-membership", type=Path, default=Path("data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/research/artifacts"))
    parser.add_argument("--detail-dir", type=Path, default=Path("../rs_leadership_local_artifacts"))
    args = parser.parse_args()
    summary = run(
        raw_dir=args.raw_dir,
        core_manifest_path=args.core_manifest,
        core_output_path=args.core_output,
        b_membership_path=args.b_membership,
        output_dir=args.output_dir,
        detail_dir=args.detail_dir,
    )
    print(json.dumps({"decision": summary["decision"], "primary": summary["primary"], "continuous_rank_check": summary["continuous_rank_check"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
