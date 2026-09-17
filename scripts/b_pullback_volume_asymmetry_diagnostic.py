"""Fixed, retrospective pullback-volume asymmetry diagnostic.

This module reuses the #66 frozen cohort and exact breakout/retest helpers.  It
does not change Formal B, acquire data, or search for a threshold.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import subprocess
from typing import Any

import numpy as np

import b_false_breakout_path_diagnostic as false_path
import b_phase_volume_path_diagnostic as volume_path
import core_signal_replay as replay


STUDY_ID = "B_PULLBACK_VOLUME_ASYMMETRY_DIAGNOSTIC_V1"
BLOCKED_STATUS = "B_PULLBACK_VOLUME_ASYMMETRY_BLOCKED_BY_COHORT_RECONCILIATION"
PROTOCOL = "docs/research/b_pullback_volume_asymmetry_diagnostic_v1_protocol.md"
PROTOCOL_COMMIT = "d0a477db3f375ef19fdec51bb091ac3162ea6278"
SOURCE_BRANCH = "codex/b-false-breakout-path-diagnostic-v1"
SOURCE_HEAD = "9dcd93f6460006eed9f1d0e421b45c3abe5adc99"
SPEC_SHA = "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd"

FEATURES = (
    "down_volume_share",
    "up_down_volume_ratio",
    "worst_price_day_volume_ratio",
    "pullback_volume_decay_ratio",
    "reactivation_vs_pullback_volume",
)
EXPECTED_DIRECTION = {
    "down_volume_share": "lower",
    "up_down_volume_ratio": "higher",
    "worst_price_day_volume_ratio": "lower",
    "pullback_volume_decay_ratio": "lower",
    "reactivation_vs_pullback_volume": "higher",
}
FEATURE_DEFINITIONS = {
    "down_volume_share": "sum(volume on close[d] < close[d-1] days in R) / sum(volume in R)",
    "up_down_volume_ratio": "mean(up-day volume in R) / mean(down-day volume in R); both classes required",
    "worst_price_day_volume_ratio": "volume on earliest minimum low[d]/L day in R / volume[i]",
    "pullback_volume_decay_ratio": "mean(volume in later half of R) / mean(volume in earlier half of R); len(R)>=4",
    "reactivation_vs_pullback_volume": "exact alias of existing reactivation_vs_retest_ratio = volume[T] / mean(volume[i+1:T])",
}

EXPECTED_INPUT_SHA = {
    "data/validation/core_signal_validation/raw/daily_k.parquet": "61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426",
    "data/validation/core_signal_validation/raw/adjustment_factors.parquet": "a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716",
    "data/validation/core_signal_validation/raw/index_000001_SH_2023.json": "c118fb39d31065914740da150455fba2375d3bcaa83566730d265df0753bb51c",
    "data/validation/core_signal_validation/raw/index_000001_SH_2024.json": "53fc9e9f0989e67f8a826614c5c8f260171cf081801bf752df6301e69f4ae4bf",
    "data/validation/core_signal_validation/raw/index_000001_SH_2025.json": "27acba0bd5bfc0f54d349d7dbc41a86bf6836dfee3976a970cbb210b287f76a1",
    "data/validation/core_signal_validation/raw/index_000001_SH_2026.json": "183f472a1699811edb2550f3ce99b2b05d06c23473b5e2acff0ad2431eaf1514",
}
EXPECTED_ELIGIBILITY_SHA = "8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9"
EXPECTED_FALSE_PATH_EVENTS_SHA = "d30f17e647ac9848af3b759956e450d72c222afe2787f5d5823f51511a4a3e4d"


def _blocked(reason: str) -> None:
    raise RuntimeError(f"{BLOCKED_STATUS}: {reason}")


def _safe_ratio(numerator: float, denominator: float) -> tuple[float | None, str | None]:
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None, "NON_FINITE_NUMERATOR_OR_DENOMINATOR"
    if denominator == 0:
        return None, "ZERO_DENOMINATOR"
    value = numerator / denominator
    if not math.isfinite(value):
        return None, "NON_FINITE_RESULT"
    return float(value), None


def _mean(values: np.ndarray) -> float | None:
    if len(values) == 0 or not np.all(np.isfinite(values)):
        return None
    value = float(np.mean(values))
    return value if math.isfinite(value) else None


def _same_value(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def _category_counts(
    close: np.ndarray, volume: np.ndarray, previous_close: np.ndarray, previous_volume: np.ndarray,
) -> dict[str, int]:
    counts = Counter({"A": 0, "B": 0, "C": 0, "D": 0, "OTHER": 0})
    for current_close, prior_close, current_volume, prior_volume in zip(
        close, previous_close, volume, previous_volume
    ):
        if not all(math.isfinite(float(value)) for value in (current_close, prior_close, current_volume, prior_volume)):
            counts["OTHER"] += 1
        elif current_close < prior_close and current_volume < prior_volume:
            counts["A"] += 1
        elif current_close >= prior_close and current_volume < prior_volume:
            counts["B"] += 1
        elif current_close > prior_close and current_volume > prior_volume:
            counts["C"] += 1
        elif current_close < prior_close and current_volume >= prior_volume:
            counts["D"] += 1
        else:
            counts["OTHER"] += 1
    return dict(counts)


def _feature_result_from_path(
    path: dict[str, Any], close: np.ndarray, volume: np.ndarray, high: np.ndarray,
    low: np.ndarray, dates: list[str],
) -> dict[str, Any]:
    del high  # The exact price-defense path is already supplied by path_features.
    breakout_index = int(path["breakout_index"])
    signal_index = len(close) - 1
    pullback_start = breakout_index + 1
    pullback_stop = signal_index
    pullback_close = np.asarray(close[pullback_start:pullback_stop], dtype=float)
    pullback_volume = np.asarray(volume[pullback_start:pullback_stop], dtype=float)
    pullback_low = np.asarray(low[pullback_start:pullback_stop], dtype=float)
    previous_close = np.asarray(close[breakout_index:signal_index - 0], dtype=float)[: len(pullback_close)]
    unavailable: dict[str, str] = {}
    values: dict[str, float | None] = {}

    if len(pullback_close) == 0:
        for feature in FEATURES[:4]:
            values[feature] = None
            unavailable[feature] = "NO_PULLBACK_WINDOW"
    else:
        down = pullback_close < previous_close
        up = pullback_close > previous_close

        total_volume = float(np.sum(pullback_volume)) if np.all(np.isfinite(pullback_volume)) else math.nan
        if not math.isfinite(total_volume) or total_volume <= 0:
            values["down_volume_share"] = None
            unavailable["down_volume_share"] = "INVALID_PULLBACK_VOLUME_SUM"
        else:
            values["down_volume_share"], reason = _safe_ratio(float(np.sum(pullback_volume[down])), total_volume)
            if reason:
                unavailable["down_volume_share"] = reason

        if not np.any(up) or not np.any(down):
            values["up_down_volume_ratio"] = None
            unavailable["up_down_volume_ratio"] = "NO_UP_OR_DOWN_DAY"
        else:
            up_mean = _mean(pullback_volume[up])
            down_mean = _mean(pullback_volume[down])
            if up_mean is None or down_mean is None or down_mean <= 0:
                values["up_down_volume_ratio"] = None
                unavailable["up_down_volume_ratio"] = "INVALID_UP_OR_DOWN_VOLUME"
            else:
                values["up_down_volume_ratio"], reason = _safe_ratio(up_mean, down_mean)
                if reason:
                    unavailable["up_down_volume_ratio"] = reason

        level = float(path["base_hi"])
        breakout_volume = float(volume[breakout_index])
        if not math.isfinite(level) or level == 0 or not np.all(np.isfinite(pullback_low)):
            values["worst_price_day_volume_ratio"] = None
            unavailable["worst_price_day_volume_ratio"] = "INVALID_PULLBACK_LOW_OR_BREAKOUT_LEVEL"
        else:
            relative_low = pullback_low / level
            worst_offset = int(np.argmin(relative_low))
            worst_day = pullback_start + worst_offset
            if not math.isfinite(breakout_volume) or breakout_volume <= 0:
                values["worst_price_day_volume_ratio"] = None
                unavailable["worst_price_day_volume_ratio"] = "INVALID_BREAKOUT_VOLUME"
            elif not math.isfinite(float(volume[worst_day])):
                values["worst_price_day_volume_ratio"] = None
                unavailable["worst_price_day_volume_ratio"] = "INVALID_WORST_DAY_VOLUME"
            else:
                values["worst_price_day_volume_ratio"], reason = _safe_ratio(float(volume[worst_day]), breakout_volume)
                if reason:
                    unavailable["worst_price_day_volume_ratio"] = reason

        if len(pullback_volume) < 4:
            values["pullback_volume_decay_ratio"] = None
            unavailable["pullback_volume_decay_ratio"] = "PULLBACK_WINDOW_LT_4"
        else:
            split = len(pullback_volume) // 2
            first_mean = _mean(pullback_volume[:split])
            second_mean = _mean(pullback_volume[split:])
            if first_mean is None or second_mean is None or first_mean <= 0:
                values["pullback_volume_decay_ratio"] = None
                unavailable["pullback_volume_decay_ratio"] = "INVALID_PULLBACK_HALF_VOLUME"
            else:
                values["pullback_volume_decay_ratio"], reason = _safe_ratio(second_mean, first_mean)
                if reason:
                    unavailable["pullback_volume_decay_ratio"] = reason

    existing_reason = path.get("feature_unavailable", {}).get("reactivation_vs_retest_ratio")
    existing_value = path.get("reactivation_vs_retest_ratio")
    if existing_value is None:
        values["reactivation_vs_pullback_volume"] = None
        unavailable["reactivation_vs_pullback_volume"] = existing_reason or "UNAVAILABLE_FROM_EXISTING_HELPER"
    elif math.isfinite(float(existing_value)):
        values["reactivation_vs_pullback_volume"] = float(existing_value)
    else:
        values["reactivation_vs_pullback_volume"] = None
        unavailable["reactivation_vs_pullback_volume"] = "NON_FINITE_EXISTING_HELPER_VALUE"

    category_close = pullback_close
    category_previous = previous_close
    category_volume = pullback_volume
    category_previous_volume = np.asarray(volume[breakout_index:signal_index], dtype=float)
    category_counts = _category_counts(category_close, category_volume, category_previous, category_previous_volume) if len(category_close) else {
        "A": 0, "B": 0, "C": 0, "D": 0, "OTHER": 0,
    }
    return {
        **values,
        "feature_unavailable": unavailable,
        "worst_price_day": (
            dates[pullback_start + int(np.argmin(pullback_low / float(path["base_hi"]))) ]
            if len(pullback_low) and np.all(np.isfinite(pullback_low)) and float(path["base_hi"]) != 0
            else None
        ),
        "descriptive_counts": category_counts,
        "path": path,
    }


def pullback_volume_features(
    close: np.ndarray, volume: np.ndarray, high: np.ndarray, low: np.ndarray, dates: list[str] | None = None,
) -> dict[str, Any]:
    """Return the five fixed features using #66's exact path helper."""

    if dates is None:
        dates = [str(index) for index in range(len(close))]
    path = false_path.path_features(close, volume, high, low, dates)
    return _feature_result_from_path(path, close, volume, high, low, dates)


def _load_jsonl_gz(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return [json.loads(line) for line in handle]


def _validate_source_ref(root: Path) -> None:
    try:
        actual = subprocess.check_output(["git", "rev-parse", f"origin/{SOURCE_BRANCH}"], cwd=root, text=True).strip()
    except subprocess.CalledProcessError as exc:
        _blocked(f"source branch ref unavailable: {exc}")
    if actual != SOURCE_HEAD:
        _blocked(f"#66 source head changed: expected {SOURCE_HEAD}, got {actual}")


def _validate_inputs(root: Path, raw_dir: Path, eligibility_path: Path, false_events_path: Path) -> None:
    forbidden = ("final_oos", "continuous_speed_probe")
    for path in (raw_dir, eligibility_path, false_events_path, root / PROTOCOL):
        if any(token in str(path).lower() for token in forbidden):
            _blocked(f"forbidden path: {path}")
    if false_path.sha(eligibility_path) != EXPECTED_ELIGIBILITY_SHA:
        _blocked("authoritative eligibility artifact hash changed")
    if false_path.sha(false_events_path) != EXPECTED_FALSE_PATH_EVENTS_SHA:
        _blocked("#66 frozen event artifact hash changed")
    for relative, expected in EXPECTED_INPUT_SHA.items():
        path = root / relative
        if not path.exists() or false_path.sha(path) != expected:
            _blocked(f"frozen input hash changed: {relative}")
    try:
        frozen_protocol = subprocess.check_output(["git", "show", f"{PROTOCOL_COMMIT}:{PROTOCOL}"], cwd=root)
    except subprocess.CalledProcessError as exc:
        _blocked(f"protocol commit unavailable: {exc}")
    if frozen_protocol != (root / PROTOCOL).read_bytes():
        _blocked("protocol bytes changed after pre-outcome commit")


def _reconcile_cohort(eligibility_path: Path, false_events_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    authoritative = _load_jsonl_gz(eligibility_path)
    frozen = _load_jsonl_gz(false_events_path)
    authoritative_ids = {(row["symbol"], row["signal_date"]) for row in authoritative}
    frozen_ids = {(row["symbol"], row["signal_date"]) for row in frozen}
    if len(authoritative_ids) != 17714 or len(frozen) != 17714 or frozen_ids != authoritative_ids:
        _blocked(
            f"cohort identity mismatch: authoritative={len(authoritative_ids)}, "
            f"frozen={len(frozen)}, intersection={len(frozen_ids & authoritative_ids)}"
        )
    labels = Counter(row.get("label") for row in frozen)
    if labels["TARGET"] != 4338 or labels["FAST_STOP"] != 4623 or labels["STOP"] + labels["FAST_STOP"] != 7953:
        _blocked(f"cohort label counts changed: {dict(labels)}")
    episodes = {(row["symbol"], row["breakout_date"]) for row in frozen}
    if len(episodes) != 9766:
        _blocked(f"unique episode count changed: {len(episodes)}")
    for row in frozen:
        if row.get("episode") != f"{row['symbol']}|{row['breakout_date']}":
            _blocked(f"episode identity mismatch for {row['symbol']} {row['signal_date']}")
    frozen.sort(key=lambda row: (row["symbol"], row["signal_date"]))
    reconciliation = {
        "authoritative_identity_count": len(authoritative_ids),
        "frozen_event_row_count": len(frozen),
        "identity_match": True,
        "target_count": labels["TARGET"],
        "fast_stop_count": labels["FAST_STOP"],
        "stop_count": labels["STOP"] + labels["FAST_STOP"],
        "unique_episode_count": len(episodes),
        "main_board_count": sum(row.get("board") == "main" for row in frozen),
        "year_counts": dict(sorted(Counter(row["year"] for row in frozen).items())),
        "label_counts": dict(sorted(labels.items(), key=lambda item: str(item[0]))),
    }
    return frozen, reconciliation


def _reconcile_path(frozen: dict[str, Any], path: dict[str, Any]) -> None:
    fields = (
        "breakout_index", "breakout_date", "base_hi", "breakout_volume_ratio",
        "pre_t_retest_volume_ratio", "reactivation_vs_retest_ratio",
        "max_retest_depth_vs_breakout_level",
    )
    for field in fields:
        if not _same_value(frozen.get(field), path.get(field)):
            _blocked(
                f"#66 exact path mismatch for {frozen['symbol']} {frozen['signal_date']} "
                f"field={field}: frozen={frozen.get(field)!r} rebuilt={path.get(field)!r}"
            )


def _build_rows(root: Path, frozen: list[dict[str, Any]], raw_dir: Path) -> list[dict[str, Any]]:
    store, _ = replay._load_stock_store(raw_dir / "daily_k.parquet")
    events, _ = replay._load_events(raw_dir / "adjustment_factors.parquet")
    rows: list[dict[str, Any]] = []
    cached_key: tuple[str, int] | None = None
    cached_arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None
    for index, frozen_row in enumerate(frozen):
        symbol = frozen_row["symbol"]
        signal_date = frozen_row["signal_date"]
        anchor_ms = replay._ms_from_date(signal_date)
        symbol_events = events.get(symbol, [])
        event_count = sum(event[0] <= anchor_ms for event in symbol_events)
        cache_key = (symbol, event_count)
        if cache_key != cached_key:
            cached_arrays = volume_path._adjusted_symbol_arrays(store, symbol, symbol_events, event_count)
            cached_key = cache_key
        if cached_arrays is None:
            _blocked(f"adjusted array unavailable for {symbol} {signal_date}")
        dates_ms, close, volume, high, low = cached_arrays
        end = int(np.searchsorted(dates_ms, anchor_ms, side="right"))
        start = max(0, end - replay.LOOKBACK_BARS)
        arrays = tuple(array[start:end] for array in (close, volume, high, low))
        dates = [store["date_text"][int(value)] for value in dates_ms[start:end]]
        path = false_path.path_features(*arrays, dates)
        _reconcile_path(frozen_row, path)
        computed = _feature_result_from_path(path, *arrays, dates)
        row = {
            "_index": index,
            "symbol": symbol,
            "signal_date": signal_date,
            "year": frozen_row["year"],
            "board": frozen_row["board"],
            "episode": frozen_row["episode"],
            "label": frozen_row["label"],
            "price_defense": path["max_retest_depth_vs_breakout_level"],
            **{feature: computed[feature] for feature in FEATURES},
            "_feature_unavailable": computed["feature_unavailable"],
            "_descriptive_counts": computed["descriptive_counts"],
        }
        rows.append(row)
        if index and index % 2000 == 0:
            print(f"reconciled rows {index}/{len(frozen)}", flush=True)
    return rows


def _median_iqr(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    array = np.asarray(values, dtype=float)
    quartiles = np.quantile(array, [0.25, 0.75])
    return float(np.median(array)), float(quartiles[1] - quartiles[0])


def _label_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = Counter(row["label"] for row in rows)
    target = labels["TARGET"]
    fast = labels["FAST_STOP"]
    all_stop = fast + labels["STOP"]
    return {
        "rows": len(rows),
        "TARGET": target,
        "FAST_STOP": fast,
        "STOP": all_stop,
        "other": {key: value for key, value in sorted(labels.items()) if key not in {"TARGET", "FAST_STOP", "STOP"}},
    }


def _tertiles(rows: list[dict[str, Any]], feature: str) -> dict[int, int]:
    return volume_path._assign_bins(rows, feature, 3)


def _rate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = Counter(row["label"] for row in rows)
    target = labels["TARGET"]
    fast = labels["FAST_STOP"]
    all_stop = fast + labels["STOP"]
    return {
        "cell_count": len(rows),
        "target_count": target,
        "fast_stop_count": fast,
        "stop_count": all_stop,
        "fast_stop_rate": fast / (target + fast) if target + fast else None,
        "stop_rate": all_stop / (target + all_stop) if target + all_stop else None,
    }


def _tertile_table(rows: list[dict[str, Any]], assignments: dict[int, int]) -> list[dict[str, Any]]:
    result = []
    for bin_number, name in ((1, "LOW"), (2, "MID"), (3, "HIGH")):
        group = [row for row in rows if assignments.get(row["_index"]) == bin_number]
        values = [float(row["_value_for_tertile"]) for row in group]
        result.append({
            "tertile": name,
            "bin": bin_number,
            "feature_min": min(values) if values else None,
            "feature_max": max(values) if values else None,
            **_rate_counts(group),
        })
    return result


def _direction_sign(expected: str) -> int:
    return -1 if expected == "lower" else 1


def _direction_support(
    target_median: float | None, fast_median: float | None, table: list[dict[str, Any]], expected: str,
) -> dict[str, Any]:
    expected_sign = _direction_sign(expected)
    median_difference = None if target_median is None or fast_median is None else target_median - fast_median
    median_sign = 0 if median_difference is None or median_difference == 0 else (1 if median_difference > 0 else -1)
    preferred_bin = 1 if expected == "lower" else 3
    opposite_bin = 3 if expected == "lower" else 1
    preferred = next(item for item in table if item["bin"] == preferred_bin)
    opposite = next(item for item in table if item["bin"] == opposite_bin)
    primary_endpoint = None
    secondary_endpoint = None
    if preferred["fast_stop_rate"] is not None and opposite["fast_stop_rate"] is not None:
        primary_endpoint = preferred["fast_stop_rate"] < opposite["fast_stop_rate"]
    if preferred["stop_rate"] is not None and opposite["stop_rate"] is not None:
        secondary_endpoint = preferred["stop_rate"] < opposite["stop_rate"]
    return {
        "expected_direction": expected,
        "target_minus_fast_stop_median": median_difference,
        "median_direction": median_sign,
        "median_supported": median_sign == expected_sign,
        "preferred_tertile": preferred["tertile"],
        "opposite_tertile": opposite["tertile"],
        "primary_endpoint_supported": primary_endpoint,
        "secondary_endpoint_supported": secondary_endpoint,
        "direction_supported": median_sign == expected_sign and primary_endpoint is True,
        "secondary_direction_supported": median_sign == expected_sign and secondary_endpoint is True,
    }


def _view_result(
    rows: list[dict[str, Any]], all_rows: list[dict[str, Any]], feature: str, expected: str,
) -> dict[str, Any]:
    eligible = [row for row in rows if row[feature] is not None]
    target_values = [float(row[feature]) for row in eligible if row["label"] == "TARGET"]
    fast_values = [float(row[feature]) for row in eligible if row["label"] == "FAST_STOP"]
    all_stop_values = [float(row[feature]) for row in eligible if row["label"] in {"FAST_STOP", "STOP"}]
    target_median, target_iqr = _median_iqr(target_values)
    fast_median, fast_iqr = _median_iqr(fast_values)
    stop_median, stop_iqr = _median_iqr(all_stop_values)
    for row in all_rows:
        row["_value_for_tertile"] = row[feature]
    assignments = _tertiles(all_rows, feature)
    table = _tertile_table(eligible, assignments)
    support = _direction_support(target_median, fast_median, table, expected)
    return {
        "row_count": len(rows),
        "eligible_count": len(eligible),
        "missing_count": len(rows) - len(eligible),
        "target_median": target_median,
        "fast_stop_median": fast_median,
        "target_iqr": target_iqr,
        "fast_stop_iqr": fast_iqr,
        "all_stop_median": stop_median,
        "all_stop_iqr": stop_iqr,
        "tertiles": table,
        **support,
    }


def _matrix(rows: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    for row in rows:
        row["_value_for_tertile"] = row["price_defense"]
    price_bins = _tertiles(rows, "_value_for_tertile")
    for row in rows:
        row["_value_for_tertile"] = row[feature]
    feature_bins = _tertiles(rows, "_value_for_tertile")
    cells = []
    for price_bin, price_name in ((1, "LOW"), (2, "MID"), (3, "HIGH")):
        for feature_bin, feature_name in ((1, "LOW"), (2, "MID"), (3, "HIGH")):
            group = [
                row for row in rows
                if price_bins.get(row["_index"]) == price_bin and feature_bins.get(row["_index"]) == feature_bin
            ]
            cells.append({
                "price_defense_tertile": price_name,
                "price_defense_bin": price_bin,
                "feature_tertile": feature_name,
                "feature_bin": feature_bin,
                **_rate_counts(group),
            })
    return {
        "price_defense_feature": "max_retest_depth_vs_breakout_level",
        "volume_feature": feature,
        "cells": cells,
    }


def _matrix_consistency(matrix: dict[str, Any], expected: str) -> dict[str, Any]:
    cells = matrix["cells"]
    supporting_rows = []
    opposite_rows = []
    usable_rows = []
    for price_bin in (1, 2, 3):
        low = next(cell for cell in cells if cell["price_defense_bin"] == price_bin and cell["feature_bin"] == 1)
        high = next(cell for cell in cells if cell["price_defense_bin"] == price_bin and cell["feature_bin"] == 3)
        if low["fast_stop_rate"] is None or high["fast_stop_rate"] is None:
            continue
        usable_rows.append(price_bin)
        supported = low["fast_stop_rate"] < high["fast_stop_rate"] if expected == "lower" else high["fast_stop_rate"] < low["fast_stop_rate"]
        opposite = high["fast_stop_rate"] < low["fast_stop_rate"] if expected == "lower" else low["fast_stop_rate"] < high["fast_stop_rate"]
        if supported:
            supporting_rows.append(price_bin)
        elif opposite:
            opposite_rows.append(price_bin)
    return {
        "usable_price_defense_rows": usable_rows,
        "supporting_price_defense_rows": supporting_rows,
        "opposite_price_defense_rows": opposite_rows,
        "matrix_consistent": len(supporting_rows) >= 2 and not opposite_rows,
    }


def _year_consistency(year_views: dict[str, dict[str, Any]], expected: str) -> dict[str, Any]:
    expected_sign = _direction_sign(expected)
    supported = [year for year, view in year_views.items() if view["direction_supported"]]
    reversed_years = [
        year for year, view in year_views.items()
        if view["median_direction"] == -expected_sign
    ]
    neutral = [year for year, view in year_views.items() if year not in supported and year not in reversed_years]
    return {
        "supported_years": supported,
        "reversed_years": reversed_years,
        "neutral_years": neutral,
        "directional_year_count": len(supported),
        "non_reversed_year_count": len(year_views) - len(reversed_years),
        "majority_non_reversed": len(year_views) - len(reversed_years) >= 3,
        "stable": len(supported) >= 2 and len(reversed_years) == 0,
    }


def _feature_summary(rows: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    expected = EXPECTED_DIRECTION[feature]
    overall = _view_result(rows, rows, feature, expected)
    main = _view_result([row for row in rows if row["board"] == "main"], rows, feature, expected)
    year_views = {
        year: _view_result([row for row in rows if row["year"] == year], rows, feature, expected)
        for year in ("2023", "2024", "2025", "2026")
    }
    episodes = {}
    for row in sorted(rows, key=lambda item: (item["signal_date"], item["symbol"])):
        episodes.setdefault(row["episode"], row)
    unique_episode = _view_result(list(episodes.values()), rows, feature, expected)
    return {
        "definition": FEATURE_DEFINITIONS[feature],
        "eligible_count": overall["eligible_count"],
        "missing_count": overall["missing_count"],
        "target_median": overall["target_median"],
        "fast_stop_median": overall["fast_stop_median"],
        "target_iqr": overall["target_iqr"],
        "fast_stop_iqr": overall["fast_stop_iqr"],
        "overall_direction_supported": overall["direction_supported"],
        "main_board_direction_supported": main["direction_supported"],
        "year_consistency": _year_consistency(year_views, expected),
        "unique_episode_supported": unique_episode["direction_supported"],
        "overall": overall,
        "main_board": main,
        "year_views": year_views,
        "unique_episode": unique_episode,
    }


def _aggregate_categories(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = Counter()
    by_label: dict[str, Counter[str]] = {}
    for row in rows:
        totals.update(row["_descriptive_counts"])
        label = row["label"] if row["label"] in {"TARGET", "FAST_STOP", "STOP"} else "OTHER"
        by_label.setdefault(label, Counter()).update(row["_descriptive_counts"])
    return {
        "unit": "pullback day-pair observations",
        "overall": dict(totals),
        "by_label": {label: dict(counts) for label, counts in sorted(by_label.items())},
    }


def _falsification(
    features: dict[str, dict[str, Any]], matrices: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    primary = [features[name] for name in FEATURES[:4]]
    overall_count = sum(item["overall_direction_supported"] for item in primary)
    main_count = sum(item["main_board_direction_supported"] for item in primary)
    episode_count = sum(item["unique_episode_supported"] for item in primary)
    year_majority_count = sum(item["year_consistency"]["majority_non_reversed"] for item in primary)
    secondary_count = sum(item["overall"]["secondary_direction_supported"] for item in primary)
    matrix_checks = {
        name: _matrix_consistency(matrix, EXPECTED_DIRECTION[matrix["volume_feature"]])
        for name, matrix in matrices.items()
    }
    robust_names = [
        name for name in FEATURES[:4]
        if features[name]["overall_direction_supported"]
        and features[name]["main_board_direction_supported"]
        and features[name]["unique_episode_supported"]
        and features[name]["year_consistency"]["majority_non_reversed"]
    ]
    candidate = (
        len(robust_names) >= 3
        and secondary_count >= 3
        and any(item["matrix_consistent"] for item in matrix_checks.values())
    )
    any_signal = overall_count > 0 or features[FEATURES[4]]["overall_direction_supported"]
    final_status = (
        "B_PULLBACK_VOLUME_ASYMMETRY_RESEARCH_CANDIDATE_SUPPORTED" if candidate
        else "B_PULLBACK_VOLUME_ASYMMETRY_PROSPECTIVE_EVIDENCE_REQUIRED" if any_signal
        else "B_PULLBACK_VOLUME_ASYMMETRY_NO_SIGNAL"
    )
    return {
        "h1_h4_overall_supported_count": overall_count,
        "h1_h4_main_board_supported_count": main_count,
        "h1_h4_unique_episode_supported_count": episode_count,
        "h1_h4_year_majority_non_reversed_count": year_majority_count,
        "h1_h4_secondary_supported_count": secondary_count,
        "matrix_checks": matrix_checks,
        "robust_feature_names": robust_names,
        "reactivation_alias_of_existing_baseline": True,
        "reactivation_incremental_information_established": False,
        "reactivation_incremental_reason": "F5 is exactly #66 reactivation_vs_retest_ratio; no additional model or matrix is permitted.",
        "candidate_criteria_met": candidate,
        "final_status": final_status,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _feature_table(features: dict[str, dict[str, Any]], view: str) -> list[str]:
    lines = [
        "| feature | TARGET median | FAST_STOP median | TARGET IQR | FAST_STOP IQR | missing | direction | all-STOP direction |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for feature in FEATURES:
        item = features[feature]
        selected = item[view]
        lines.append(
            f"| `{feature}` | {_fmt(selected['target_median'])} | {_fmt(selected['fast_stop_median'])} | "
            f"{_fmt(selected['target_iqr'])} | {_fmt(selected['fast_stop_iqr'])} | {selected['missing_count']} | "
            f"{_fmt(selected['direction_supported'])} | {_fmt(selected['secondary_direction_supported'])} |"
        )
    return lines


def _matrix_table(matrix: dict[str, Any]) -> list[str]:
    lines = [
        f"#### `{matrix['volume_feature']}` × price defense",
        "",
        "| price defense | volume tertile | cell count | TARGET | FAST_STOP | all STOP | FAST_STOP rate | STOP rate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell in matrix["cells"]:
        lines.append(
            f"| {cell['price_defense_tertile']} | {cell['feature_tertile']} | {cell['cell_count']} | "
            f"{cell['target_count']} | {cell['fast_stop_count']} | {cell['stop_count']} | "
            f"{_fmt(cell['fast_stop_rate'])} | {_fmt(cell['stop_rate'])} |"
        )
    return lines


def render_report(summary: dict[str, Any]) -> str:
    features = summary["features"]
    lines = [
        "# B Pullback Volume Asymmetry Diagnostic V1 Report",
        "",
        "DEVELOPMENT / DIAGNOSTIC_ONLY / INDEPENDENT_PROTOCOL. Formal B is unchanged.",
        "",
        "## 1. Question",
        "",
        "Test whether fixed pullback volume observables distinguish TARGET from FAST_STOP in the #66 frozen cohort.",
        "",
        "## 2. Frozen cohort",
        "",
        f"Rows={summary['cohort_rows']}; TARGET={summary['target_count']}; FAST_STOP={summary['fast_stop_count']}; "
        f"all STOP={summary['stop_count']}; unique episodes={summary['unique_episode_count']}.",
        "",
        "Primary is TARGET versus FAST_STOP. Secondary is TARGET versus all STOP, with FAST_STOP included once.",
        "",
        "## 3. Feature definitions",
        "",
    ]
    lines.extend(f"- `{feature}`: {definition}." for feature, definition in FEATURE_DEFINITIONS.items())
    lines.extend([
        "- Exact path: #66 `_first_breakout_trace`, breakout level `L=base_hi`, and pullback `R=i+1:T-1`; signal day T is excluded.",
        "- Price-defense control: exact #66 `max_retest_depth_vs_breakout_level`.",
        "",
        "## 4. Overall result",
        "",
    ])
    lines.extend(_feature_table(features, "overall"))
    lines.extend(["", "The direction column requires the pre-registered median and fixed-tertile endpoint comparison.", ""])
    lines.extend(["## 5. Main Board", ""])
    lines.extend(_feature_table(features, "main_board"))
    lines.extend(["", "## 6. Year split", "", "| feature | year | TARGET median | FAST_STOP median | direction | all-STOP direction |", "| --- | --- | ---: | ---: | --- | --- |"])
    for feature in FEATURES:
        for year, view in features[feature]["year_views"].items():
            lines.append(
                f"| `{feature}` | {year} | {_fmt(view['target_median'])} | {_fmt(view['fast_stop_median'])} | "
                f"{_fmt(view['direction_supported'])} | {_fmt(view['secondary_direction_supported'])} |"
            )
    lines.extend(["", "## 7. Unique episode", ""])
    lines.extend(_feature_table(features, "unique_episode"))
    lines.extend(["", "Unique episode view keeps the earliest qualified signal per `(symbol, breakout_date)`.", "", "## 8. Two matrices", ""])
    lines.extend(_matrix_table(summary["matrix_A"]))
    lines.extend([""])
    lines.extend(_matrix_table(summary["matrix_B"]))
    lines.extend(["", "## 9. Reactivation incremental check", "", "F5 is a direct alias of #66 `reactivation_vs_retest_ratio`; it was not recomputed against breakout volume.", ""])
    lines.append(f"Incremental information established: `{_fmt(summary['reactivation_incremental_check']['incremental_information_established'])}`; {summary['reactivation_incremental_check']['reason']}")
    lines.extend(["", "Descriptive pullback day-pair counts (not features or rules):", "", "| label | A | B | C | D | OTHER |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for label, counts in summary["descriptive_day_category_counts"]["by_label"].items():
        lines.append(f"| {label} | {counts.get('A', 0)} | {counts.get('B', 0)} | {counts.get('C', 0)} | {counts.get('D', 0)} | {counts.get('OTHER', 0)} |")
    lines.extend(["", "## 10. Falsification", ""])
    falsification = summary["falsification"]
    lines.extend([
        f"- H1-H4 overall supported count: `{falsification['h1_h4_overall_supported_count']}/4`; Main Board: `{falsification['h1_h4_main_board_supported_count']}/4`.",
        f"- H1-H4 unique-episode supported count: `{falsification['h1_h4_unique_episode_supported_count']}/4`; year majority non-reversed count: `{falsification['h1_h4_year_majority_non_reversed_count']}/4`.",
        f"- H1-H4 secondary all-STOP supported count: `{falsification['h1_h4_secondary_supported_count']}/4`.",
        f"- Matrix A consistent: `{_fmt(falsification['matrix_checks']['matrix_A']['matrix_consistent'])}`; Matrix B consistent: `{_fmt(falsification['matrix_checks']['matrix_B']['matrix_consistent'])}`.",
        "- No threshold, window, tertile, label, technical indicator, or small-cell rule was selected after observing results.",
        "",
        "## 11. Conclusion",
        "",
        f"Terminal status: `{summary['final_status']}`.",
        "Formal B remains unchanged; no B V2, prospective deployment, production dispatch, or runtime-state mutation is created.",
        "",
        "## Provenance",
        "",
        f"Protocol commit: `{summary['protocol_commit_sha']}`; source branch: `{summary['source_branch']}`; source head: `{summary['source_head']}`.",
        "Production dispatch=0; runtime-state mutation=0; Final OOS=SEALED / UNREAD.",
        "",
    ])
    return "\n".join(lines)


def run(
    *, raw_dir: Path = Path("data/validation/core_signal_validation/raw"),
    eligibility_path: Path = Path("data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"),
    false_events_path: Path = Path("data/validation/b_false_breakout_path_diagnostic_v1/events.jsonl.gz"),
    output: Path = Path("data/validation/b_pullback_volume_asymmetry_diagnostic_v1"),
    report: Path = Path("docs/research/b_pullback_volume_asymmetry_diagnostic_v1_report.md"),
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    raw_dir = raw_dir.resolve()
    eligibility_path = eligibility_path.resolve()
    false_events_path = false_events_path.resolve()
    output = output.resolve()
    report = report.resolve()
    expected_output = (root / "data/validation/b_pullback_volume_asymmetry_diagnostic_v1").resolve()
    expected_report = (root / "docs/research/b_pullback_volume_asymmetry_diagnostic_v1_report.md").resolve()
    if output != expected_output or report != expected_report:
        _blocked("output path is not the isolated task artifact path")
    if SPEC_SHA != false_path.STRATEGY_SPEC_SHA256:
        _blocked("Formal B spec SHA changed")
    _validate_source_ref(root)
    _validate_inputs(root, raw_dir, eligibility_path, false_events_path)
    frozen, cohort_reconciliation = _reconcile_cohort(eligibility_path, false_events_path)
    rows = _build_rows(root, frozen, raw_dir)
    if len(rows) != 17714:
        _blocked(f"rebuilt row count changed: {len(rows)}")
    features = {feature: _feature_summary(rows, feature) for feature in FEATURES}
    matrix_A = _matrix(rows, "down_volume_share")
    matrix_B = _matrix(rows, "worst_price_day_volume_ratio")
    falsification = _falsification(features, {"matrix_A": matrix_A, "matrix_B": matrix_B})
    missing_reasons = Counter(
        f"{feature}:{reason}"
        for row in rows
        for feature, reason in row["_feature_unavailable"].items()
    )
    summary: dict[str, Any] = {
        "study_id": STUDY_ID,
        "schema_version": STUDY_ID,
        "protocol_commit_sha": PROTOCOL_COMMIT,
        "protocol_sha256": false_path.sha(root / PROTOCOL),
        "source_branch": SOURCE_BRANCH,
        "source_head": SOURCE_HEAD,
        "cohort_rows": len(rows),
        "target_count": cohort_reconciliation["target_count"],
        "fast_stop_count": cohort_reconciliation["fast_stop_count"],
        "stop_count": cohort_reconciliation["stop_count"],
        "unique_episode_count": cohort_reconciliation["unique_episode_count"],
        "cohort_reconciliation": cohort_reconciliation,
        "exact_reconciliation": {
            "frozen_cohort": True,
            "pullback_window": "#66 _first_breakout_trace R=i+1:T-1; signal day T excluded",
            "pullback_window_exact": True,
            "breakout_level": "#66 trace base_hi = max(close[i-60:i])",
            "breakout_level_exact": True,
            "price_defense_control": "#66 max_retest_depth_vs_breakout_level",
        },
        "features": features,
        "matrix_A": matrix_A,
        "matrix_B": matrix_B,
        "reactivation_incremental_check": {
            "feature": "reactivation_vs_pullback_volume",
            "existing_equivalent": "reactivation_vs_retest_ratio",
            "equivalent": True,
            "incremental_information_established": False,
            "reason": "F5 is exactly #66 reactivation_vs_retest_ratio; no additional model or matrix is permitted.",
        },
        "descriptive_day_category_counts": _aggregate_categories(rows),
        "feature_unavailable_reason_counts": dict(sorted(missing_reasons.items())),
        "falsification": falsification,
        "final_status": falsification["final_status"],
        "boundaries": {
            "formal_b_unchanged": True,
            "threshold_search": False,
            "grid_search": False,
            "model_fitting": False,
            "turnover": False,
            "provider_calls": 0,
            "production_dispatch": 0,
            "runtime_state_mutation": 0,
            "final_oos": "SEALED / UNREAD",
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(summary), encoding="utf-8", newline="\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=Path("data/validation/core_signal_validation/raw"))
    parser.add_argument("--eligibility-events", type=Path, default=Path("data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"))
    parser.add_argument("--false-path-events", type=Path, default=Path("data/validation/b_false_breakout_path_diagnostic_v1/events.jsonl.gz"))
    parser.add_argument("--output", type=Path, default=Path("data/validation/b_pullback_volume_asymmetry_diagnostic_v1"))
    parser.add_argument("--report", type=Path, default=Path("docs/research/b_pullback_volume_asymmetry_diagnostic_v1_report.md"))
    args = parser.parse_args()
    try:
        summary = run(
            raw_dir=args.raw_dir,
            eligibility_path=args.eligibility_events,
            false_events_path=args.false_path_events,
            output=args.output,
            report=args.report,
        )
    except RuntimeError as exc:
        if str(exc).startswith(BLOCKED_STATUS):
            print(BLOCKED_STATUS)
            return 2
        raise
    print(summary["final_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
