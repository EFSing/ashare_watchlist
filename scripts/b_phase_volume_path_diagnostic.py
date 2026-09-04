"""Pre-registered DEVELOPMENT diagnostic for the corrected B volume path.

This module is research-only. It reuses the frozen B numeric projection and V2
outcome builder, never changes B qualification, and has no threshold-search mode.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

import core_signal_replay as replay
from b_breakout_retest import _b_match
from b_breakout_retest_v1_1 import (
    SETUP_ID,
    STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION,
    evaluate_numeric_projection,
)
from strategy_development_eligibility import (
    _frozen_timing,
    _next_execution_date,
    _repo_root_from_registry,
    _runtime_environment,
    _verify_frozen_projection_identity,
    _verify_required_registry_hashes,
)
import validate_development_returns as returns_v1
import validate_development_returns_v2 as returns_v2


SCHEMA_VERSION = "B_PHASE_VOLUME_PATH_DIAGNOSTIC_V1"
EVIDENCE_LABELS = ("DEVELOPMENT", "RECONSTRUCTED_RETROSPECTIVE", "DIAGNOSTIC_ONLY")
DECISIONS = (
    "VOLUME_PATH_SUPPORTED_FOR_FURTHER_VALIDATION",
    "VOLUME_PATH_NEEDS_MORE_EVIDENCE",
    "VOLUME_PATH_NO_CLEAR_INCREMENTAL_SIGNAL",
)
FEATURES = (
    "breakout_volume_ratio",
    "b_existing_pull_volume_ratio",
    "pre_t_retest_volume_ratio",
    "reactivation_vs_retest_ratio",
    "reactivation_vs_breakout_ratio",
)
PRIMARY_FEATURES = (
    "pre_t_retest_volume_ratio",
    "reactivation_vs_retest_ratio",
    "breakout_volume_ratio",
)
DECOMPOSED_FEATURES = PRIMARY_FEATURES[:2]
PRIMARY_HORIZONS = ("5D", "10D")
OUTCOME_FIELDS = ("return_pct", "mfe_pct", "mae_pct")
STAGE_LABELS = (
    "PULLBACK_ALL_PASS",
    "PULLBACK_VOLUME_FAIL_ONLY",
    "PULLBACK_TURN_STRENGTH_FAIL_ONLY",
    "PULLBACK_PRICE_STRUCTURE_FAIL",
    "PULLBACK_MULTIPLE_FAIL",
)


def _safe_ratio(numerator: float, denominator: float) -> tuple[float | None, str | None]:
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None, "NON_FINITE_DENOMINATOR_OR_NUMERATOR"
    if denominator == 0:
        return None, "ZERO_DENOMINATOR"
    value = numerator / denominator
    if not math.isfinite(value):
        return None, "NON_FINITE_RESULT"
    return float(value), None


def _first_breakout_trace(
    close: np.ndarray,
    volume: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    dates: list[str] | None = None,
) -> dict[str, Any] | None:
    """Expose the first-breakout facts without changing the B evaluator."""

    n = len(close)
    ma5 = float(np.mean(close[-5:]))
    signal_close = float(close[-1])
    for i in range(max(61, n - 15), n - 1):
        base_hi = float(np.max(close[i - 60 : i]))
        breakout = (
            float(close[i]) > base_hi
            and float(volume[i]) >= 1.8 * float(np.mean(volume[i - 20 : i]))
            and float(close[i] / close[i - 1] - 1.0) >= 0.03
        )
        if not breakout:
            continue

        pull_volume = (
            float(np.mean(volume[i + 1 :]))
            if n - 1 > i + 1
            else float(volume[-1])
        )
        price_pass = (
            signal_close >= base_hi * 0.97
            and (
                abs(signal_close / base_hi - 1.0) <= 0.04
                or base_hi * 0.97 <= signal_close <= base_hi * 1.04
            )
        )
        volume_pass = pull_volume < float(volume[i]) * 0.7
        turn_pass = signal_close >= float(close[-2]) or signal_close >= ma5
        failed_count = sum(not item for item in (price_pass, volume_pass, turn_pass))
        if failed_count == 0:
            stage = "PULLBACK_ALL_PASS"
        elif not volume_pass and price_pass and turn_pass:
            stage = "PULLBACK_VOLUME_FAIL_ONLY"
        elif not turn_pass and price_pass and volume_pass:
            stage = "PULLBACK_TURN_STRENGTH_FAIL_ONLY"
        elif not price_pass and volume_pass and turn_pass:
            stage = "PULLBACK_PRICE_STRUCTURE_FAIL"
        else:
            stage = "PULLBACK_MULTIPLE_FAIL"

        unavailable: dict[str, str] = {}
        breakout_mean = float(np.mean(volume[i - 20 : i]))
        breakout_ratio, reason = _safe_ratio(float(volume[i]), breakout_mean)
        if reason:
            unavailable["breakout_volume_ratio"] = reason
        existing_ratio, reason = _safe_ratio(pull_volume, float(volume[i]))
        if reason:
            unavailable["b_existing_pull_volume_ratio"] = reason

        pre_t_ratio: float | None = None
        reactivation_retest: float | None = None
        if i + 1 <= n - 2:
            retest_mean = float(np.mean(volume[i + 1 : n - 1]))
            pre_t_ratio, reason = _safe_ratio(retest_mean, float(volume[i]))
            if reason:
                unavailable["pre_t_retest_volume_ratio"] = reason
            reactivation_retest, reason = _safe_ratio(float(volume[-1]), retest_mean)
            if reason:
                unavailable["reactivation_vs_retest_ratio"] = reason
        else:
            unavailable["pre_t_retest_volume_ratio"] = "NO_PRE_T_RETEST_INTERVAL"
            unavailable["reactivation_vs_retest_ratio"] = "NO_PRE_T_RETEST_INTERVAL"

        reactivation_breakout, reason = _safe_ratio(float(volume[-1]), float(volume[i]))
        if reason:
            unavailable["reactivation_vs_breakout_ratio"] = reason

        day_range = float(high[-1] - low[-1])
        pos250_low = float(np.min(low[-250:]))
        pos250_high = float(np.max(high[-250:]))
        return {
            "breakout_index": i,
            "breakout_date": None if dates is None else dates[i],
            "base_hi": base_hi,
            "pullback_stage": stage,
            "price_structure_pass": price_pass,
            "volume_pass": volume_pass,
            "turn_strength_pass": turn_pass,
            "breakout_volume_ratio": breakout_ratio,
            "b_existing_pull_volume_ratio": existing_ratio,
            "pre_t_retest_volume_ratio": pre_t_ratio,
            "reactivation_vs_retest_ratio": reactivation_retest,
            "reactivation_vs_breakout_ratio": reactivation_breakout,
            "feature_unavailable": unavailable,
            "signal_day_return_pct": float((close[-1] / close[-2] - 1.0) * 100.0),
            "close_relative_previous": float(close[-1] / close[-2]),
            "close_vs_ma5": float(close[-1] / ma5) if ma5 else None,
            "close_position_in_day_range": (
                float((close[-1] - low[-1]) / day_range) if day_range > 0 else None
            ),
            "distance_from_base_hi_pct": float((close[-1] / base_hi - 1.0) * 100.0),
            "pos250": (
                float((close[-1] - pos250_low) / (pos250_high - pos250_low))
                if pos250_high > pos250_low
                else 0.5
            ),
        }
    return None


def _window_dates(store: dict[str, Any], symbol: str, anchor_ms: int, length: int) -> list[str]:
    start, end = store["bounds"][symbol]
    symbol_dates = store["date_ms"][start:end]
    local_end = int(np.searchsorted(symbol_dates, anchor_ms, side="right"))
    selected = symbol_dates[local_end - length : local_end]
    if len(selected) != length:
        raise RuntimeError(f"date/array length mismatch for {symbol}")
    return [replay._date_from_ms(int(value)) for value in selected]


def _adjusted_symbol_arrays(
    store: dict[str, Any], symbol: str,
    symbol_events: list[tuple[int, float, float, float, float]], event_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build one full-history T-anchor state, reused across all matching T rows."""

    start, end = store["bounds"][symbol]
    dates = store["date_ms"][start:end]
    close = np.array(store["close"][start:end], dtype=float, copy=True)
    high = np.array(store["high"][start:end], dtype=float, copy=True)
    low = np.array(store["low"][start:end], dtype=float, copy=True)
    volume = np.asarray(store["volume"][start:end], dtype=float)
    for ex_date_ms, dividend, bonus, allotment, allotment_price in symbol_events[:event_count]:
        mask = dates < ex_date_ms
        denominator = 1.0 + bonus + allotment
        if denominator <= 0 or not math.isfinite(denominator):
            raise RuntimeError(f"invalid corporate-action denominator for {symbol}")
        for values in (close, high, low):
            values[mask] = (values[mask] - dividend + allotment_price * allotment) / denominator
    return dates, close, volume, high, low


def _breakout_mask(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Vectorized exact breakout predicates; pullback/T semantics remain row-level."""

    result = np.zeros(len(close), dtype=bool)
    if len(close) <= 61:
        return result
    close_windows = np.lib.stride_tricks.sliding_window_view(close, 60)
    volume_windows = np.lib.stride_tricks.sliding_window_view(volume, 20)
    indices = np.arange(61, len(close))
    base_hi = np.max(close_windows[indices - 60], axis=1)
    prev_volume = np.mean(volume_windows[indices - 20], axis=1)
    # Preserve the scalar evaluator's IEEE divide behavior for malformed zero
    # predecessor prices without emitting a noisy vectorized runtime warning.
    with np.errstate(divide="ignore", invalid="ignore"):
        one_day_change = close[indices] / close[indices - 1] - 1.0
    result[indices] = (
        (close[indices] > base_hi)
        & (volume[indices] >= 1.8 * prev_volume)
        & (one_day_change >= 0.03)
    )
    return result


def _board(symbol: str) -> str:
    code = symbol.split(".", 1)[0]
    if code.startswith(("00", "60")):
        return "main"
    if code.startswith("30"):
        return "ChiNext"
    if code.startswith("68"):
        return "STAR"
    return "OUT_OF_SCOPE_PREFIX"


def _near_price_limit_proxy(symbol: str, signal_return_pct: float) -> bool | None:
    board = _board(symbol)
    if board == "main":
        return abs(signal_return_pct) >= 9.5
    if board in {"ChiNext", "STAR"}:
        return abs(signal_return_pct) >= 19.0
    return None


def _available(records: Iterable[dict[str, Any]], horizon: str) -> list[dict[str, float]]:
    values = []
    for record in records:
        outcome = record["outcomes"][horizon]
        if outcome["status"] == "AVAILABLE":
            values.append(outcome)
    return values


def _metrics(records: Iterable[dict[str, Any]], horizon: str) -> dict[str, Any]:
    values = _available(records, horizon)
    if not values:
        return {
            "n": 0,
            "mean_return_pct": None,
            "median_return_pct": None,
            "positive_rate": None,
            "mean_mfe_pct": None,
            "median_mfe_pct": None,
            "mean_mae_pct": None,
            "median_mae_pct": None,
        }
    returns = np.asarray([float(value["return_pct"]) for value in values])
    mfe = np.asarray([float(value["mfe_pct"]) for value in values])
    mae = np.asarray([float(value["mae_pct"]) for value in values])
    return {
        "n": len(values),
        "mean_return_pct": float(np.mean(returns)),
        "median_return_pct": float(np.median(returns)),
        "positive_rate": float(np.mean(returns > 0)),
        "mean_mfe_pct": float(np.mean(mfe)),
        "median_mfe_pct": float(np.median(mfe)),
        "mean_mae_pct": float(np.mean(mae)),
        "median_mae_pct": float(np.median(mae)),
    }


def _distribution(records: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    values = np.asarray(
        [float(record[feature]) for record in records if record.get(feature) is not None],
        dtype=float,
    )
    result = {"n": int(len(values)), "unavailable_n": len(records) - int(len(values))}
    if not len(values):
        return result
    quantiles = np.quantile(values, [0.1, 0.25, 0.5, 0.75, 0.9])
    return result | {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "min": float(np.min(values)),
        "p10": float(quantiles[0]),
        "p25": float(quantiles[1]),
        "median": float(quantiles[2]),
        "p75": float(quantiles[3]),
        "p90": float(quantiles[4]),
        "max": float(np.max(values)),
    }


def _assign_bins(records: list[dict[str, Any]], feature: str, bins: int) -> dict[int, int]:
    available = [
        (index, float(record[feature]), record["symbol"], record["signal_date"])
        for index, record in enumerate(records)
        if record.get(feature) is not None
    ]
    available.sort(key=lambda item: (item[1], item[2], item[3], item[0]))
    count = len(available)
    return {
        index: min(bins, int(position * bins / count) + 1)
        for position, (index, _value, _symbol, _date) in enumerate(available)
    } if count else {}


def _quantile_table(records: list[dict[str, Any]], feature: str, bins: int) -> list[dict[str, Any]]:
    assigned = _assign_bins(records, feature, bins)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, bin_number in assigned.items():
        grouped[bin_number].append(records[index])
    table = []
    for bin_number in range(1, bins + 1):
        rows = grouped.get(bin_number, [])
        values = [float(row[feature]) for row in rows]
        item: dict[str, Any] = {
            "bin": bin_number,
            "row_n": len(rows),
            "feature_min": min(values) if values else None,
            "feature_max": max(values) if values else None,
        }
        for horizon in PRIMARY_HORIZONS:
            item[horizon] = _metrics(rows, horizon)
        table.append(item)
    return table


def _spearman(records: list[dict[str, Any]], feature: str, horizon: str, outcome: str) -> dict[str, Any]:
    pairs = [
        (float(record[feature]), float(record["outcomes"][horizon][outcome]))
        for record in records
        if record.get(feature) is not None
        and record["outcomes"][horizon]["status"] == "AVAILABLE"
    ]
    if len(pairs) < 2:
        return {"n": len(pairs), "rho": None}
    x = np.asarray([pair[0] for pair in pairs], dtype=float)
    y = np.asarray([pair[1] for pair in pairs], dtype=float)
    x_rank = _average_ranks(x)
    y_rank = _average_ranks(y)
    if np.std(x_rank) == 0 or np.std(y_rank) == 0:
        return {"n": len(pairs), "rho": None}
    return {"n": len(pairs), "rho": float(np.corrcoef(x_rank, y_rank)[0, 1])}


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    position = 0
    while position < len(values):
        end = position + 1
        while end < len(values) and values[order[end]] == values[order[position]]:
            end += 1
        ranks[order[position:end]] = (position + end - 1) / 2.0 + 1.0
        position = end
    return ranks


def _sign(value: float | None) -> int:
    if value is None or value == 0:
        return 0
    return 1 if value > 0 else -1


def _endpoint_robustness(
    records: list[dict[str, Any]], feature: str, horizon: str, group_field: str,
    groups: Iterable[str],
) -> list[dict[str, Any]]:
    assignments = _assign_bins(records, feature, 5)
    result = []
    for group in groups:
        low = [records[index] for index, value in assignments.items() if value == 1 and str(records[index][group_field]) == group]
        high = [records[index] for index, value in assignments.items() if value == 5 and str(records[index][group_field]) == group]
        low_metrics, high_metrics = _metrics(low, horizon), _metrics(high, horizon)
        result.append({
            "group": group,
            "low": low_metrics,
            "high": high_metrics,
            "high_minus_low_mean_return_pct": (
                high_metrics["mean_return_pct"] - low_metrics["mean_return_pct"]
                if high_metrics["mean_return_pct"] is not None and low_metrics["mean_return_pct"] is not None
                else None
            ),
        })
    return result


def _matrix(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    row_bins = _assign_bins(records, "pre_t_retest_volume_ratio", 5)
    col_bins = _assign_bins(records, "reactivation_vs_retest_ratio", 5)
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for index in sorted(set(row_bins) & set(col_bins)):
        grouped[(row_bins[index], col_bins[index])].append(records[index])
    result = []
    for row_bin in range(1, 6):
        for col_bin in range(1, 6):
            rows = grouped.get((row_bin, col_bin), [])
            result.append({
                "retest_quintile": row_bin,
                "reactivation_quintile": col_bin,
                "row_n": len(rows),
                "5D": _metrics(rows, "5D"),
                "10D": _metrics(rows, "10D"),
            })
    return result


def _direction_audit(
    records: list[dict[str, Any]], feature: str, horizon: str,
    matrix_rows: list[dict[str, Any]], structural_spearman: dict[str, Any],
) -> dict[str, Any]:
    table = _quantile_table(records, feature, 5)
    rho = _spearman(records, feature, horizon, "return_pct")["rho"]
    low, high = table[0][horizon], table[-1][horizon]
    mean_spread = (
        high["mean_return_pct"] - low["mean_return_pct"]
        if high["mean_return_pct"] is not None and low["mean_return_pct"] is not None else None
    )
    median_spread = (
        high["median_return_pct"] - low["median_return_pct"]
        if high["median_return_pct"] is not None and low["median_return_pct"] is not None else None
    )
    direction = _sign(rho)
    transitions = []
    for left, right in zip(table, table[1:]):
        lval, rval = left[horizon]["mean_return_pct"], right[horizon]["mean_return_pct"]
        transitions.append(_sign(rval - lval) if lval is not None and rval is not None else 0)
    years = _endpoint_robustness(records, feature, horizon, "year", ("2023", "2024", "2025", "2026"))
    boards = _endpoint_robustness(records, feature, horizon, "board", ("main", "ChiNext", "STAR"))
    year_consistent = sum(
        item["low"]["n"] >= 30 and item["high"]["n"] >= 30
        and _sign(item["high_minus_low_mean_return_pct"]) == direction
        for item in years
    )
    board_consistent = sum(
        item["low"]["n"] >= 30 and item["high"]["n"] >= 30
        and _sign(item["high_minus_low_mean_return_pct"]) == direction
        for item in boards
    )
    sensitivity_records = [record for record in records if record["near_price_limit_proxy"] is not True]
    sensitivity_rho = _spearman(sensitivity_records, feature, horizon, "return_pct")["rho"]
    sensitivity_table = _quantile_table(sensitivity_records, feature, 5)
    sens_low, sens_high = sensitivity_table[0][horizon], sensitivity_table[-1][horizon]
    sensitivity_spread = (
        sens_high["mean_return_pct"] - sens_low["mean_return_pct"]
        if sens_high["mean_return_pct"] is not None and sens_low["mean_return_pct"] is not None else None
    )
    if feature == "pre_t_retest_volume_ratio":
        matrix_low = [row for row in matrix_rows if row["retest_quintile"] == 1]
        matrix_high = [row for row in matrix_rows if row["retest_quintile"] == 5]
    else:
        matrix_low = [row for row in matrix_rows if row["reactivation_quintile"] == 1]
        matrix_high = [row for row in matrix_rows if row["reactivation_quintile"] == 5]
    def weighted(rows: list[dict[str, Any]]) -> float | None:
        usable = [(row[horizon]["n"], row[horizon]["mean_return_pct"]) for row in rows if row[horizon]["mean_return_pct"] is not None]
        total = sum(item[0] for item in usable)
        return sum(item[0] * item[1] for item in usable) / total if total else None
    matrix_low_mean, matrix_high_mean = weighted(matrix_low), weighted(matrix_high)
    matrix_spread = (
        matrix_high_mean - matrix_low_mean
        if matrix_low_mean is not None and matrix_high_mean is not None else None
    )
    structural_rho = structural_spearman.get("rho")
    checks = {
        "overall_sign_alignment": direction != 0 and _sign(mean_spread) == direction and _sign(median_spread) == direction,
        "coherent_adjacent_transitions": sum(value == direction for value in transitions) >= 3,
        "year_consistency": year_consistent >= 3,
        "board_consistency": board_consistent >= 2,
        "matrix_compatible": _sign(matrix_spread) == direction,
        "near_limit_exclusion_preserves_direction": _sign(sensitivity_rho) == direction and _sign(sensitivity_spread) == direction,
        "structural_cohort_not_opposite": structural_rho is None or _sign(structural_rho) in {0, direction},
    }
    return {
        "feature": feature,
        "horizon": horizon,
        "direction": direction,
        "spearman_rho": rho,
        "high_minus_low_mean_return_pct": mean_spread,
        "high_minus_low_median_return_pct": median_spread,
        "adjacent_transition_signs": transitions,
        "year_consistent_count": year_consistent,
        "board_consistent_count": board_consistent,
        "matrix_high_minus_low_mean_return_pct": matrix_spread,
        "excluding_proxy_spearman_rho": sensitivity_rho,
        "excluding_proxy_high_minus_low_mean_return_pct": sensitivity_spread,
        "structural_spearman_rho": structural_rho,
        "checks": checks,
        "supported": all(checks.values()),
        "non_monotonic": direction != 0 and sum(value == direction for value in transitions) < 3,
        "year_detail": years,
        "board_detail": boards,
    }


def _write_event_artifact(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    content_digest = __import__("hashlib").sha256()
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            for record in records:
                line = (replay.canonical_json(record) + "\n").encode("utf-8")
                content_digest.update(line)
                compressed.write(line)
    return {
        "path": path.as_posix(),
        "rows": len(records),
        "bytes": path.stat().st_size,
        "file_sha256": replay.file_sha256(path),
        "content_stream_sha256": content_digest.hexdigest(),
    }


def _load_qualified_identity(path: Path) -> set[tuple[str, str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return {
            (row["symbol"], row["signal_date"], row["setup_id"])
            for row in (json.loads(line) for line in handle)
        }


def _table(rows: list[list[Any]], headers: list[str]) -> str:
    def cell(value: Any) -> str:
        if value is None:
            return "NA"
        if isinstance(value, float):
            return f"{value:.6f}"
        return str(value)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _render_report(summary: dict[str, Any]) -> str:
    cohort = summary["cohort_reconciliation"]
    lines = [
        "# B Phase Volume Path Diagnostic V1 Report",
        "",
        "Labels: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DIAGNOSTIC_ONLY`",
        "",
        "This is a pre-registered diagnostic decomposition of corrected B. It is not a new rule, strategy version, promotion, threshold or production result.",
        "",
        "## Final decision",
        "",
        f"`{summary['decision']}`",
        "",
        summary["decision_explanation"],
        "",
        "## Table A — cohort reconciliation",
        "",
        _table([
            ["total evaluation rows", cohort["total_evaluation_rows"]],
            ["first qualifying breakout rows", cohort["first_breakout_rows"]],
            *[[label, cohort["stage_counts"].get(label, 0)] for label in STAGE_LABELS],
            ["final B qualified", cohort["qualified_b_rows"]],
            ["qualified identity matched", cohort["qualified_identity_matched"]],
            ["unique structural symbols", cohort["structural_symbol_count"]],
            ["unique structural signal dates", cohort["structural_signal_date_count"]],
            ["unique breakout episodes", cohort["unique_breakout_episode_count"]],
            ["repeated breakout episode share", cohort["repeated_breakout_episode_share"]],
        ], ["item", "value"]),
        "",
        "Feature unavailable reasons: `" + replay.canonical_json(cohort["feature_unavailable_reason_counts"]) + "`.",
        "",
        "## Table B — qualified B feature distributions",
        "",
        _table([[feature] + [summary["feature_distributions"][feature].get(key) for key in ("n", "unavailable_n", "mean", "std", "p10", "p25", "median", "p75", "p90")]
                for feature in FEATURES],
               ["feature", "N", "unavailable", "mean", "std", "p10", "p25", "median", "p75", "p90"]),
    ]
    table_names = {
        "pre_t_retest_volume_ratio": "Table C — retest contraction quantiles vs 5D/10D",
        "reactivation_vs_retest_ratio": "Table D — reactivation expansion quantiles vs 5D/10D",
        "breakout_volume_ratio": "Table E — breakout volume quantiles vs 5D/10D",
    }
    for feature in PRIMARY_FEATURES:
        lines += ["", "## " + table_names[feature], ""]
        rows = []
        for item in summary["quantile_tables"][feature]["rows"]:
            for horizon in PRIMARY_HORIZONS:
                metrics = item[horizon]
                rows.append([item["bin"], item["feature_min"], item["feature_max"], horizon, metrics["n"], metrics["mean_return_pct"], metrics["median_return_pct"], metrics["positive_rate"], metrics["mean_mfe_pct"], metrics["mean_mae_pct"]])
        lines.append(_table(rows, ["bin", "min", "max", "horizon", "N", "mean ret", "median ret", "positive", "mean MFE", "mean MAE"]))
    lines += ["", "## Table F — retest × reactivation 2D matrix", ""]
    lines.append(_table([
        [row["retest_quintile"], row["reactivation_quintile"], row["row_n"], row["5D"]["mean_return_pct"], row["5D"]["median_return_pct"], row["5D"]["positive_rate"], row["5D"]["mean_mfe_pct"], row["5D"]["mean_mae_pct"], row["10D"]["mean_return_pct"], row["10D"]["median_return_pct"], row["10D"]["positive_rate"], row["10D"]["mean_mfe_pct"], row["10D"]["mean_mae_pct"]]
        for row in summary["matrix"]
    ], ["retest Q", "reactivation Q", "rows", "5D mean", "5D median", "5D positive", "5D MFE", "5D MAE", "10D mean", "10D median", "10D positive", "10D MFE", "10D MAE"]))
    audit = summary["decision_audit"]
    year_rows, board_rows = [], []
    for item in audit:
        for row in item["year_detail"]:
            year_rows.append([item["feature"], item["horizon"], row["group"], row["low"]["n"], row["high"]["n"], row["high_minus_low_mean_return_pct"]])
        for row in item["board_detail"]:
            board_rows.append([item["feature"], item["horizon"], row["group"], row["low"]["n"], row["high"]["n"], row["high_minus_low_mean_return_pct"]])
    lines += ["", "## Table G — year robustness", "", _table(year_rows, ["feature", "horizon", "year", "low N", "high N", "high-low mean ret"])]
    lines += ["", "## Table H — board robustness", "", _table(board_rows, ["feature", "horizon", "board", "low N", "high N", "high-low mean ret"])]
    lines += ["", "## Table I — NEAR_PRICE_LIMIT_PROXY_SENSITIVITY_NOT_EXACT_LIMIT_STATE", ""]
    lines.append(_table([
        [item["feature"], item["horizon"], item["spearman_rho"], item["high_minus_low_mean_return_pct"], item["excluding_proxy_spearman_rho"], item["excluding_proxy_high_minus_low_mean_return_pct"]]
        for item in audit
    ], ["feature", "horizon", "all rho", "all spread", "excluding proxy rho", "excluding proxy spread"]))
    lines += [
        "",
        "The proxy uses prefix-based ordinary board limits and is not an exact exchange limit-state classification. Exact classification remains `DEFERRED_REQUIRES_PIT_TRADING_STATUS_DATA`.",
        "",
        "## Continuous relationships and structural comparison",
        "",
        _table([[item["feature"], item["horizon"], item["spearman_rho"], item["high_minus_low_mean_return_pct"], item["high_minus_low_median_return_pct"], item["structural_spearman_rho"], item["supported"], item["non_monotonic"]] for item in audit], ["feature", "horizon", "qualified rho", "mean spread", "median spread", "structural rho", "supported", "non-monotonic"]),
        "",
        "Structural pullback-stage outcome summary:",
        "",
        _table([[stage, horizon, summary["structural_stage_outcomes"][stage][horizon]["n"], summary["structural_stage_outcomes"][stage][horizon]["mean_return_pct"], summary["structural_stage_outcomes"][stage][horizon]["median_return_pct"], summary["structural_stage_outcomes"][stage][horizon]["positive_rate"], summary["structural_stage_outcomes"][stage][horizon]["mean_mfe_pct"], summary["structural_stage_outcomes"][stage][horizon]["mean_mae_pct"]] for stage in STAGE_LABELS for horizon in PRIMARY_HORIZONS], ["stage", "horizon", "N", "mean ret", "median ret", "positive", "mean MFE", "mean MAE"]),
        "",
        "## Boundaries and provenance",
        "",
        f"- Protocol pre-outcome commit: `{summary['protocol']['commit_sha']}`.",
        f"- Corrected B spec SHA: `{summary['strategy']['spec_sha256']}`.",
        f"- Frozen daily-K SHA: `{summary['frozen_inputs']['daily_k_sha256']}`.",
        f"- Derived event artifact rows/content SHA: `{summary['artifacts']['events']['rows']}` / `{summary['artifacts']['events']['content_stream_sha256']}`.",
        "- The deterministic event detail is local-only and intentionally not version-controlled because its compressed size exceeds 143 MB; the tracked summary records its path, row count, byte size and hashes.",
        "- B spec, B score, 1.8 breakout threshold, 0.7 pullback threshold, hard gates, Top-N, prospective pipeline and frozen bytes are unchanged.",
        "- Final OOS was not read. No provider refetch, current-data backfill, model fitting or rule selection was performed.",
        "",
    ]
    return "\n".join(lines)


def run(
    *, raw_dir: Path, checkpoint_path: Path, core_output: Path, core_manifest_path: Path,
    qualified_events_path: Path, registry_path: Path, protocol_path: Path,
    protocol_commit: str, output_dir: Path, report_path: Path,
) -> dict[str, Any]:
    forbidden = ("final_oos", "continuous_speed_probe")
    for path in (raw_dir, checkpoint_path, core_output, core_manifest_path, qualified_events_path, registry_path, protocol_path, output_dir, report_path):
        if any(token in str(path).lower() for token in forbidden):
            raise RuntimeError(f"forbidden path in diagnostic arguments: {path}")
    if STRATEGY_SPEC_SHA256 != "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd":
        raise RuntimeError("corrected B strategy spec SHA changed")
    environment = _runtime_environment()
    registry, registry_verification = _verify_required_registry_hashes(raw_dir=raw_dir, registry_path=registry_path)
    root, _part_a, _part_b, source, core_summary = returns_v1._verify_frozen_inputs(
        raw_dir=raw_dir, checkpoint_path=checkpoint_path, core_output=core_output,
        core_manifest_path=core_manifest_path,
    )
    frozen_identity = _verify_frozen_projection_identity(
        registry=registry, root=root, source=source, core_summary=core_summary,
        core_output=core_output, core_manifest_path=core_manifest_path,
    )
    if len(registry_verification) != 13:
        raise RuntimeError("required frozen artifact count changed")
    frozen_timing = _frozen_timing(core_output)
    qualified_identity = _load_qualified_identity(qualified_events_path)
    if len(qualified_identity) != 17714:
        raise RuntimeError("authoritative qualified event identity count changed")

    index_dates, index_bars, _index_meta = replay._load_index(raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.asarray([index_dates[value] for value in session_dates], dtype=np.int64)
    session_index = {value: index for index, value in enumerate(session_dates)}
    signal_dates = [value for value in session_dates if replay.VALIDATION_START <= value <= replay.VALIDATION_END]
    if len(signal_dates) != 769:
        raise RuntimeError("frozen signal-date count changed")
    store, stock_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _event_meta = replay._load_events(raw_dir / "adjustment_factors.parquet")

    structural: list[dict[str, Any]] = []
    generated_qualified: set[tuple[str, str, str]] = set()
    total_evaluations = 0
    signal_ms_set = {index_dates[value] for value in signal_dates}
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
            dates_ms, adjusted_close, volume, adjusted_high, adjusted_low = _adjusted_symbol_arrays(
                store, symbol, symbol_events, event_count,
            )
            breakout_mask = _breakout_mask(adjusted_close, volume)
            for t_index in state_t_indices:
                lower = max(61, t_index - 14)
                relative = np.flatnonzero(breakout_mask[lower:t_index])
                if not len(relative):
                    continue
                start = max(0, t_index + 1 - replay.LOOKBACK_BARS)
                close = adjusted_close[start : t_index + 1]
                local_volume = volume[start : t_index + 1]
                high = adjusted_high[start : t_index + 1]
                low = adjusted_low[start : t_index + 1]
                dates = [replay._date_from_ms(int(value)) for value in dates_ms[start : t_index + 1]]
                trace = _first_breakout_trace(close, local_volume, high, low, dates)
                if trace is None:
                    raise RuntimeError(f"vectorized/exact first-breakout parity failed for {symbol} at index {t_index}")
                signal_date = dates[-1]
                anchor_ms = int(dates_ms[t_index])
                index_position = int(np.searchsorted(session_ms, anchor_ms, side="right"))
                t_index_bars = index_bars[:index_position]
                earliest_execution_date = _next_execution_date(signal_date, session_dates, session_index, frozen_timing)
                numeric_bars = (close, local_volume, high, low)
                projection = evaluate_numeric_projection(
                    symbol=symbol, signal_date=signal_date,
                    earliest_execution_date=earliest_execution_date,
                    bars=numeric_bars, index_bars=t_index_bars,
                )
                bp_price, matched, failed = _b_match(close, local_volume, float(np.mean(close[-5:])))
                if (bp_price is not None) != (trace["pullback_stage"] == "PULLBACK_ALL_PASS"):
                    raise RuntimeError(f"B first-breakout/pullback parity failed for {symbol} {signal_date}")
                if sorted(matched) != sorted(projection["matched_conditions"][: len(matched)]) and projection["status"] == "NOT_MATCHED":
                    raise RuntimeError(f"B matched-condition parity failed for {symbol} {signal_date}")
                outcome_row = returns_v2._build_event_record(
                    row=projection, store=store, events=events, session_dates=session_dates,
                    session_ms=session_ms, session_index=session_index,
                )
                record = {
                    "symbol": symbol,
                    "signal_date": signal_date,
                    "year": signal_date[:4],
                    "board": _board(symbol),
                    "breakout_date": trace["breakout_date"],
                    "pullback_stage": trace["pullback_stage"],
                    "downstream_status": projection["status"],
                    "final_b_qualified": projection["status"] == "QUALIFIED_LEGACY_BASELINE",
                    "near_price_limit_proxy": _near_price_limit_proxy(symbol, trace["signal_day_return_pct"]),
                    **trace,
                    "outcomes": outcome_row["outcomes"],
                }
                structural.append(record)
                if record["final_b_qualified"]:
                    generated_qualified.add((symbol, signal_date, SETUP_ID))
        if symbol_number % 500 == 0:
            print(f"progress symbols={symbol_number} evaluations={total_evaluations} first_breakouts={len(structural)}", flush=True)

    if total_evaluations != 4_041_140:
        raise RuntimeError(f"frozen evaluation count changed: {total_evaluations}")
    if generated_qualified != qualified_identity:
        missing = len(qualified_identity - generated_qualified)
        extra = len(generated_qualified - qualified_identity)
        raise RuntimeError(f"qualified identity mismatch: missing={missing}, extra={extra}")
    qualified = [record for record in structural if record["final_b_qualified"]]

    unavailable = Counter()
    for record in qualified:
        for feature, reason in record["feature_unavailable"].items():
            unavailable[f"{feature}:{reason}"] += 1
    stage_counts = Counter(record["pullback_stage"] for record in structural)
    episode_counts = Counter((record["symbol"], record["breakout_date"]) for record in structural)
    repeated_rows = sum(count for count in episode_counts.values() if count > 1)
    distributions = {feature: _distribution(qualified, feature) for feature in FEATURES}
    quantiles: dict[str, Any] = {}
    for feature in PRIMARY_FEATURES:
        computable = distributions[feature]["n"]
        bins = 10 if computable >= 1000 else 5
        table = _quantile_table(qualified, feature, bins)
        if bins == 10 and any(row["row_n"] < 100 for row in table):
            bins = 5
            table = _quantile_table(qualified, feature, bins)
            reason = "DECILE_MINIMUM_BIN_N_LT_100"
        else:
            reason = "QUALIFIED_DECILES_PRE_REGISTERED" if bins == 10 else "FEATURE_COMPUTABLE_N_LT_1000"
        quantiles[feature] = {"bin_count": bins, "reason": reason, "rows": table}

    correlations = {
        feature: {
            horizon: {outcome: _spearman(qualified, feature, horizon, outcome) for outcome in OUTCOME_FIELDS}
            for horizon in PRIMARY_HORIZONS
        }
        for feature in PRIMARY_FEATURES
    }
    matrix_rows = _matrix(qualified)
    structural_correlations = {
        feature: {
            horizon: _spearman(structural, feature, horizon, "return_pct")
            for horizon in PRIMARY_HORIZONS
        }
        for feature in DECOMPOSED_FEATURES
    }
    decision_audit = [
        _direction_audit(
            qualified, feature, horizon, matrix_rows,
            structural_correlations[feature][horizon],
        )
        for feature in DECOMPOSED_FEATURES
        for horizon in PRIMARY_HORIZONS
    ]
    supported = [item for item in decision_audit if item["supported"]]
    relationship_evidence = [
        item for item in decision_audit
        if item["direction"] != 0
        and _sign(item["high_minus_low_mean_return_pct"]) == item["direction"]
        and _sign(item["high_minus_low_median_return_pct"]) == item["direction"]
    ]
    if supported:
        decision = DECISIONS[0]
        explanation = "At least one pre-registered decomposed relationship passed every coherence check; this supports only a separate validation cycle."
    elif relationship_evidence:
        decision = DECISIONS[1]
        explanation = "Some overall decomposed relationships are directionally visible, but none passes all pre-registered year, board, matrix, structural and price-limit-proxy coherence checks."
    else:
        decision = DECISIONS[2]
        explanation = "Neither decomposed primary relationship shows aligned rank and endpoint evidence on 5D or 10D outcomes."

    event_artifact = _write_event_artifact(output_dir / "events.jsonl.gz", structural)
    stage_outcomes = {
        stage: {horizon: _metrics([row for row in structural if row["pullback_stage"] == stage], horizon) for horizon in PRIMARY_HORIZONS}
        for stage in STAGE_LABELS
    }
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "labels": list(EVIDENCE_LABELS),
        "status": "COMPLETE",
        "strategy": {"version": STRATEGY_VERSION, "spec_sha256": STRATEGY_SPEC_SHA256, "modified": False},
        "protocol": {
            "path": protocol_path.as_posix(),
            "commit_sha": protocol_commit,
            "file_sha256": replay.file_sha256(protocol_path),
            "frozen_before_outcome_read": True,
        },
        "frozen_inputs": frozen_identity | {"required_registry_artifacts_verified": len(registry_verification)},
        "environment": environment,
        "raw_store": stock_meta,
        "cohort_reconciliation": {
            "total_evaluation_rows": total_evaluations,
            "first_breakout_rows": len(structural),
            "stage_counts": dict(sorted(stage_counts.items())),
            "qualified_b_input_identity_count": len(qualified_identity),
            "qualified_b_rows": len(qualified),
            "qualified_identity_matched": len(generated_qualified),
            "qualified_feature_computable_counts": {feature: distributions[feature]["n"] for feature in FEATURES},
            "feature_unavailable_reason_counts": dict(sorted(unavailable.items())),
            "qualified_symbol_count": len({row["symbol"] for row in qualified}),
            "qualified_signal_date_count": len({row["signal_date"] for row in qualified}),
            "qualified_year_counts": dict(sorted(Counter(row["year"] for row in qualified).items())),
            "structural_symbol_count": len({row["symbol"] for row in structural}),
            "structural_signal_date_count": len({row["signal_date"] for row in structural}),
            "structural_year_counts": dict(sorted(Counter(row["year"] for row in structural).items())),
            "unique_breakout_episode_count": len(episode_counts),
            "repeated_breakout_episode_row_count": repeated_rows,
            "repeated_breakout_episode_share": repeated_rows / len(structural) if structural else None,
        },
        "feature_distributions": distributions,
        "quantile_tables": quantiles,
        "spearman": correlations,
        "matrix": matrix_rows,
        "structural_spearman": structural_correlations,
        "structural_stage_outcomes": stage_outcomes,
        "decision_audit": decision_audit,
        "non_monotonic_relationship_observed": any(item["non_monotonic"] for item in decision_audit),
        "decision": decision,
        "decision_explanation": explanation,
        "artifacts": {"events": event_artifact},
        "reproduction_command": (
            ".venv/Scripts/python.exe scripts/b_phase_volume_path_diagnostic.py "
            "--protocol-commit " + protocol_commit
        ),
        "boundaries": {
            "b_spec_unchanged": True,
            "b_score_unchanged": True,
            "breakout_threshold_unchanged": True,
            "pullback_threshold_unchanged": True,
            "top_n_unchanged": True,
            "prospective_pipeline_unchanged": True,
            "provider_refetch": False,
            "final_oos_read": False,
            "frozen_artifacts_modified": False,
            "parameter_sweep": False,
            "threshold_search": False,
            "model_fitting": False,
        },
    }
    summary["content_sha256"] = replay.sha256_json(summary)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(summary), encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=Path("data/validation/core_signal_validation/raw"))
    parser.add_argument("--checkpoint", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_resume_checkpoint.json"))
    parser.add_argument("--core-output", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_replay_results.jsonl.gz"))
    parser.add_argument("--core-manifest", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"))
    parser.add_argument("--qualified-events", type=Path, default=Path("data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"))
    parser.add_argument("--registry", type=Path, default=Path("data/governance/frozen_artifacts.json"))
    parser.add_argument("--protocol", type=Path, default=Path("docs/research/b_phase_volume_path_diagnostic_v1_protocol.md"))
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/validation/b_phase_volume_path_diagnostic_v1"))
    parser.add_argument("--report", type=Path, default=Path("docs/research/b_phase_volume_path_diagnostic_v1_report.md"))
    args = parser.parse_args()
    result = run(
        raw_dir=args.raw_dir, checkpoint_path=args.checkpoint, core_output=args.core_output,
        core_manifest_path=args.core_manifest, qualified_events_path=args.qualified_events,
        registry_path=args.registry, protocol_path=args.protocol,
        protocol_commit=args.protocol_commit, output_dir=args.output_dir,
        report_path=args.report,
    )
    print(json.dumps({"decision": result["decision"], "content_sha256": result["content_sha256"], "cohorts": result["cohort_reconciliation"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
