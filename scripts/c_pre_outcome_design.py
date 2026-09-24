"""Independent, outcome-blind design primitives for the new A-share C strategy.

This module is intentionally smaller than a strategy runner.  It defines
observable price/volume states and a deterministic synthetic-data/data-contract
check.  It does not import Formal B, a B evaluator, a B watchlist, a tracker,
or any outcome reader.  It never writes canonical production state.

The rule candidates in this file are proposals for Sol review.  They are not
selected from returns and are not an authorization to run a historical replay.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import unicodedata
from typing import Any

from universe_policy import BOARD_MAIN, BOARD_UNKNOWN, classify_board


C_RESEARCH_NAMESPACE = "C_PRE_OUTCOME_DESIGN_V1"
C_STRATEGY_VERSION = "C_MAIN_TREND_RETEST_RESEARCH_V1"
C_ENTRY_SCHEMA = "C_ENTRY_OBSERVATION_DESIGN_V1"
C_EXIT_SCHEMA = "C_EXIT_OBSERVATION_DESIGN_V1"
C_DATA_CHECK_SCHEMA = "C_DATA_DEPENDENCY_CHECK_V1"
C_OUTPUT_ROOT = Path("data/research/c_pre_outcome_design_v1")
C_SIGNAL_OUTPUT_ROOT = C_OUTPUT_ROOT / "signals"
C_EXIT_OUTPUT_ROOT = C_OUTPUT_ROOT / "exits"
C_MAIN_BOARD_NON_ST_POLICY = "C_MAIN_BOARD_NON_ST_V1"

SIGNAL_TIMING = "T_CLOSE_SIGNAL"
EARLIEST_EXECUTION = "T_PLUS_ONE_XSHG_REFERENCE_EXECUTION"
SAME_DAY_SELL_POLICY = "PROHIBITED_FOR_NEW_POSITION"
REFERENCE_EXECUTION_NOT_ACTUAL_FILL = "REFERENCE_EXECUTION_NOT_ACTUAL_FILL"
EXECUTION_UNCERTAIN = "EXECUTION_UNCERTAIN"
UNAVAILABLE = "UNAVAILABLE"
MIN_DIRECTIONAL_VOLUME_DAYS = 2
SUPPORT_TOLERANCE_ROLE = "DISPLAY_ONLY"
PRICE_ONLY_EARLY_DEFENSE = "PRICE_ONLY_EARLY_DEFENSE"
PRICE_VOLUME_EARLY_DEFENSE = "PRICE_VOLUME_EARLY_DEFENSE"
EARLY_DEFENSE_VERSIONS = (PRICE_ONLY_EARLY_DEFENSE, PRICE_VOLUME_EARLY_DEFENSE)
DEFAULT_EARLY_DEFENSE_VERSION = PRICE_ONLY_EARLY_DEFENSE
VOLUME_THRESHOLD_STATUS = "PRE_REGISTERED_CANDIDATE_NOT_OUTCOME_SELECTED"

REQUIRED_OHLCV_FIELDS = ("open", "high", "low", "close", "volume")
_ST_PREFIX = re.compile(r"^\*?ST(?:$|[^A-Z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class RuleCandidate:
    """A small pre-outcome candidate matrix; values are not tuned by outcomes."""

    rule_id: str
    trend_window: int
    fast_average_window: int
    slow_average_window: int
    minimum_up_close_fraction: float
    pivot_radius: int
    minimum_pivot_separation: int
    maximum_pullback_sessions: int
    shallow_depth_min: float
    shallow_depth_max: float
    support_tolerance: float
    rebound_size_min: float
    rebound_size_max: float
    resistance_tolerance: float
    confirmation_close_location: float
    volume_baseline_window: int = 20
    anomaly_ratio_candidate: float = 2.0
    anomaly_robust_z_candidate: float = 3.0
    failed_push_window: int = 5
    failed_push_count_candidate: int = 2


RULE_CANDIDATES: dict[str, RuleCandidate] = {
    "BALANCED_A": RuleCandidate(
        rule_id="BALANCED_A",
        trend_window=60,
        fast_average_window=20,
        slow_average_window=60,
        minimum_up_close_fraction=0.55,
        pivot_radius=2,
        minimum_pivot_separation=3,
        maximum_pullback_sessions=20,
        shallow_depth_min=0.03,
        shallow_depth_max=0.12,
        support_tolerance=0.01,
        rebound_size_min=0.02,
        rebound_size_max=0.08,
        resistance_tolerance=0.01,
        confirmation_close_location=0.60,
    ),
    "CONSERVATIVE_B": RuleCandidate(
        rule_id="CONSERVATIVE_B",
        trend_window=90,
        fast_average_window=20,
        slow_average_window=90,
        minimum_up_close_fraction=0.60,
        pivot_radius=3,
        minimum_pivot_separation=4,
        maximum_pullback_sessions=25,
        shallow_depth_min=0.04,
        shallow_depth_max=0.15,
        support_tolerance=0.015,
        rebound_size_min=0.02,
        rebound_size_max=0.10,
        resistance_tolerance=0.015,
        confirmation_close_location=0.60,
    ),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _positive(value: Any) -> float:
    result = _finite(value)
    if result is None or result <= 0:
        raise ValueError("value must be finite and positive")
    return result


def _bar_date(bar: Mapping[str, Any]) -> str:
    value = bar.get("date", bar.get("trade_date"))
    if value is None:
        raise ValueError("invalid bar date: None")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) != 10:
        raise ValueError(f"invalid bar date: {value!r}")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid bar date: {value!r}") from exc


def validate_ohlcv_bars(bars: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Validate a chronological daily OHLCV prefix without using future rows."""

    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)):
        raise ValueError("bars must be a sequence")
    normalized: list[dict[str, Any]] = []
    previous_date: str | None = None
    for raw in bars:
        if not isinstance(raw, Mapping):
            raise ValueError("each bar must be a mapping")
        row: dict[str, Any] = {"date": _bar_date(raw)}
        for field in REQUIRED_OHLCV_FIELDS:
            number = _finite(raw.get(field))
            if number is None or number < 0 or (field != "volume" and number <= 0):
                raise ValueError(f"invalid {field} in bar {row['date']}")
            row[field] = number
        if row["high"] < max(row["open"], row["close"]) or row["low"] > min(row["open"], row["close"]):
            raise ValueError(f"OHLC bounds are invalid in bar {row['date']}")
        if previous_date is not None and row["date"] <= previous_date:
            raise ValueError("bars must be strictly chronological")
        previous_date = row["date"]
        for optional in ("limit_up_price", "tick_size"):
            if optional in raw and raw[optional] is not None:
                row[optional] = _positive(raw[optional])
        normalized.append(row)
    return tuple(normalized)


def _sma(values: Sequence[float], window: int) -> float | None:
    if window < 1 or len(values) < window:
        return None
    return float(statistics.fmean(values[-window:]))


def _log_slope(values: Sequence[float]) -> float | None:
    if len(values) < 2 or any(value <= 0 or not math.isfinite(value) for value in values):
        return None
    y = [math.log(value) for value in values]
    x_mean = (len(y) - 1) / 2.0
    y_mean = statistics.fmean(y)
    denominator = sum((index - x_mean) ** 2 for index in range(len(y)))
    if denominator == 0:
        return None
    return float(sum((index - x_mean) * (value - y_mean) for index, value in enumerate(y)) / denominator)


def _pivot_indices(values: Sequence[float], radius: int, *, low: bool) -> list[int]:
    if radius < 1:
        raise ValueError("pivot radius must be positive")
    result: list[int] = []
    for index in range(radius, len(values) - radius):
        left = values[index - radius:index]
        right = values[index + 1:index + radius + 1]
        if low:
            qualifies = values[index] <= min(left) and values[index] <= min(right)
        else:
            qualifies = values[index] >= max(left) and values[index] >= max(right)
        if qualifies:
            result.append(index)
    return result


def _bar_geometry(bar: Mapping[str, Any], previous_close: float | None) -> dict[str, float | None]:
    opening = _positive(bar["open"])
    high = _positive(bar["high"])
    low = _positive(bar["low"])
    close = _positive(bar["close"])
    span = high - low
    if span == 0:
        close_location = 1.0 if close >= opening else 0.0
        upper_shadow = lower_shadow = 0.0
    else:
        close_location = (close - low) / span
        upper_shadow = (high - max(opening, close)) / span
        lower_shadow = (min(opening, close) - low) / span
    previous_return = None if previous_close is None else close / previous_close - 1.0
    return {
        "body_return": close / opening - 1.0,
        "body_abs_fraction": abs(close - opening) / span if span else 0.0,
        "range_return": span / previous_close if previous_close else None,
        "close_location": close_location,
        "upper_shadow_fraction": upper_shadow,
        "lower_shadow_fraction": lower_shadow,
        "previous_close_return": previous_return,
    }


def relative_volume_features(
    bars: Sequence[Mapping[str, Any]],
    index: int,
    *,
    baseline_window: int = 20,
) -> dict[str, Any]:
    """Return volume anomaly observables using only bars strictly before ``index``."""

    normalized = validate_ohlcv_bars(bars)
    if index < 0 or index >= len(normalized):
        raise IndexError("volume index is outside bars")
    if baseline_window < 2 or index < baseline_window:
        return {"status": "INSUFFICIENT_BASELINE", "index": index, "baseline_window": baseline_window}
    baseline = [float(row["volume"]) for row in normalized[index - baseline_window:index]]
    current = float(normalized[index]["volume"])
    median = float(statistics.median(baseline))
    mad = float(statistics.median([abs(value - median) for value in baseline]))
    ratio = None if median <= 0 else current / median
    robust_z = None if mad == 0 else (current - median) / (1.4826 * mad)
    return {
        "status": "OK" if ratio is not None else "ZERO_BASELINE",
        "index": index,
        "baseline_window": baseline_window,
        "baseline_median": median,
        "baseline_mad": mad,
        "volume_t": current,
        "relative_volume_ratio": ratio,
        "robust_volume_z": robust_z,
        "anomaly_ratio_candidate": ratio is not None and ratio >= 2.0,
        "anomaly_robust_z_candidate": robust_z is not None and robust_z >= 3.0,
        "observable_only": True,
    }


def _median_or_none(values: Sequence[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def volume_path_features(
    bars: Sequence[Mapping[str, Any]],
    *,
    pullback_start: int,
    pullback_end_exclusive: int,
    reference_start: int,
    reference_end_exclusive: int,
) -> dict[str, Any]:
    """Describe volume path and up/down asymmetry; never infer a mechanism."""

    normalized = validate_ohlcv_bars(bars)
    ranges = (pullback_start, pullback_end_exclusive, reference_start, reference_end_exclusive)
    if any(value < 0 for value in ranges) or pullback_start >= pullback_end_exclusive or reference_start >= reference_end_exclusive:
        raise ValueError("invalid volume path interval")
    pullback = normalized[pullback_start:pullback_end_exclusive]
    reference = normalized[reference_start:reference_end_exclusive]
    pullback_median = _median_or_none([float(row["volume"]) for row in pullback])
    reference_median = _median_or_none([float(row["volume"]) for row in reference])
    if reference_median is None:
        path_status = "INSUFFICIENT_REFERENCE_DAYS"
        ratio = None
    elif reference_median == 0:
        path_status = "ZERO_REFERENCE_VOLUME"
        ratio = None
    else:
        path_status = "OK"
        ratio = pullback_median / reference_median
    if ratio is None:
        path_label = "UNDETERMINED"
    elif ratio <= 0.80:
        path_label = "CONTRACTED_OBSERVABLE"
    elif ratio >= 1.20:
        path_label = "EXPANDED_OBSERVABLE"
    else:
        path_label = "MIXED_OBSERVABLE"

    up_volumes: list[float] = []
    down_volumes: list[float] = []
    for index in range(max(1, pullback_start), pullback_end_exclusive):
        previous = float(normalized[index - 1]["close"])
        close = float(normalized[index]["close"])
        if close > previous:
            up_volumes.append(float(normalized[index]["volume"]))
        elif close < previous:
            down_volumes.append(float(normalized[index]["volume"]))
    directional_days_sufficient = (
        len(up_volumes) >= MIN_DIRECTIONAL_VOLUME_DAYS
        and len(down_volumes) >= MIN_DIRECTIONAL_VOLUME_DAYS
    )
    up_median = _median_or_none(up_volumes) if directional_days_sufficient else None
    down_median = _median_or_none(down_volumes) if directional_days_sufficient else None
    if not directional_days_sufficient:
        up_down_ratio_status = "INSUFFICIENT_DIRECTIONAL_DAYS"
        up_down_ratio = None
    elif down_median == 0:
        up_down_ratio_status = "ZERO_DOWN_DIRECTIONAL_VOLUME"
        up_down_ratio = None
    else:
        up_down_ratio_status = "OK"
        up_down_ratio = up_median / down_median
    return {
        "pullback_volume_median": pullback_median,
        "reference_volume_median": reference_median,
        "pullback_to_reference_median_ratio": ratio,
        "path_status": path_status,
        "path_label": path_label,
        "minimum_directional_days": MIN_DIRECTIONAL_VOLUME_DAYS,
        "up_day_count": len(up_volumes),
        "down_day_count": len(down_volumes),
        "up_day_volume_median": up_median,
        "down_day_volume_median": down_median,
        "up_to_down_volume_median_ratio": up_down_ratio,
        "up_down_ratio_status": up_down_ratio_status,
        "mechanism_claim": "UNKNOWN; observable volume path only",
    }


def _higher_low_pair(lows: Sequence[float], pivots: Sequence[int], config: RuleCandidate) -> tuple[int, int] | None:
    candidates = [index for index in pivots if index < len(lows) - config.pivot_radius]
    for second_position in range(len(candidates) - 1, 0, -1):
        second = candidates[second_position]
        for first_position in range(second_position - 1, -1, -1):
            first = candidates[first_position]
            if second - first >= config.minimum_pivot_separation and lows[second] > lows[first]:
                return first, second
    return None


def _latest_rebound_high(highs: Sequence[float], pivot_highs: Sequence[int], low_index: int, end_index: int) -> int | None:
    candidates = [index for index in pivot_highs if low_index < index < end_index]
    return candidates[-1] if candidates else None


def find_pullback_structure(
    bars: Sequence[Mapping[str, Any]],
    config: RuleCandidate,
) -> dict[str, Any]:
    """Find a pre-T pair of distinct higher lows and a confirmed rebound high."""

    normalized = validate_ohlcv_bars(bars)
    if len(normalized) < max(config.slow_average_window, config.maximum_pullback_sessions + config.pivot_radius * 2 + 2):
        return {"status": "INSUFFICIENT_HISTORY"}
    t_index = len(normalized) - 1
    lows = [float(row["low"]) for row in normalized]
    highs = [float(row["high"]) for row in normalized]
    # A pivot used by the T-close signal must be confirmed by bars ending at
    # T-1.  Computing pivots on the strict pre-T prefix prevents the T bar
    # from becoming part of the right confirmation window.
    pre_t_lows = lows[:t_index]
    pre_t_highs = highs[:t_index]
    low_pivots = _pivot_indices(pre_t_lows, config.pivot_radius, low=True)
    high_pivots = _pivot_indices(pre_t_highs, config.pivot_radius, low=False)
    candidate_lows = list(low_pivots)
    pair_candidates = [
        (first, second)
        for second_position, second in reversed(list(enumerate(candidate_lows)))
        for first in reversed(candidate_lows[:second_position])
        if second - first >= config.minimum_pivot_separation and lows[second] > lows[first]
    ]
    if not pair_candidates:
        return {"status": "NO_DISTINCT_HIGHER_LOW_PAIR"}
    selected: tuple[int, int, int, float, float, int] | None = None
    saw_peak = False
    saw_depth = False
    for low_one, low_two in pair_candidates:
        peak_candidates = [index for index in high_pivots if index < low_one]
        if not peak_candidates:
            continue
        saw_peak = True
        peak_index = peak_candidates[-1]
        if t_index - peak_index > config.maximum_pullback_sessions + config.pivot_radius * 2:
            continue
        pullback_start = peak_index + 1
        pullback_end = t_index
        pullback_lows = lows[pullback_start:pullback_end]
        if not pullback_lows:
            continue
        peak_high = highs[peak_index]
        depth = (peak_high - min(pullback_lows)) / peak_high
        if not config.shallow_depth_min <= depth <= config.shallow_depth_max:
            continue
        saw_depth = True
        rebound_index = _latest_rebound_high(highs, high_pivots, low_two, t_index)
        if rebound_index is None:
            continue
        rebound_size = (highs[rebound_index] - lows[low_two]) / lows[low_two]
        if not config.rebound_size_min <= rebound_size <= config.rebound_size_max:
            continue
        selected = (low_one, low_two, peak_index, depth, rebound_size, rebound_index)
        break
    if selected is None:
        if not saw_peak:
            return {"status": "NO_PRE_PULLBACK_PEAK"}
        if not saw_depth:
            return {"status": "PULLBACK_DEPTH_OUTSIDE_CANDIDATE"}
        return {"status": "NO_CONFIRMED_REBOUND_HIGH"}
    low_one, low_two, peak_index, depth, rebound_size, rebound_index = selected
    pullback_start = peak_index + 1
    pullback_end = t_index
    peak_high = highs[peak_index]
    return {
        "status": "OK",
        "peak_index": peak_index,
        "peak_high": peak_high,
        "low_one_index": low_one,
        "low_one": lows[low_one],
        "low_two_index": low_two,
        "low_two": lows[low_two],
        "higher_low_delta": lows[low_two] / lows[low_one] - 1.0,
        "rebound_high_index": rebound_index,
        "rebound_high": highs[rebound_index],
        "rebound_size": rebound_size,
        "pullback_start_index": pullback_start,
        "pullback_end_exclusive": pullback_end,
        "depth": depth,
        "support_floor": min(lows[low_one], lows[low_two]),
        "support_ceiling": max(lows[low_one], lows[low_two]),
        "support_tolerance": config.support_tolerance,
        "stage_prior_high": peak_high,
        "stage_prior_high_index": peak_index,
        "pivot_confirmation_timing": "T_MINUS_ONE_CLOSE",
        "pivot_uses_t_bar": False,
        "pivot_confirmation_end_exclusive": t_index,
    }


def trend_features(bars: Sequence[Mapping[str, Any]], config: RuleCandidate) -> dict[str, Any]:
    normalized = validate_ohlcv_bars(bars)
    closes = [float(row["close"]) for row in normalized]
    if len(closes) < config.trend_window:
        return {"status": "INSUFFICIENT_HISTORY"}
    window = closes[-config.trend_window:]
    fast = _sma(closes, config.fast_average_window)
    slow = _sma(closes, config.slow_average_window)
    slope = _log_slope(window)
    up_close_fraction = sum(window[index] > window[index - 1] for index in range(1, len(window))) / (len(window) - 1)
    close_t = closes[-1]
    return {
        "status": "OK",
        "close_t": close_t,
        "fast_average": fast,
        "slow_average": slow,
        "log_close_slope_per_session": slope,
        "up_close_fraction": up_close_fraction,
        "ma_order_ok": fast is not None and slow is not None and fast > slow,
        "close_above_fast_average": fast is not None and close_t > fast,
        "positive_slope": slope is not None and slope > 0,
        "up_close_fraction_ok": up_close_fraction >= config.minimum_up_close_fraction,
        "trend_qualified": (
            fast is not None
            and slow is not None
            and close_t > fast > slow
            and slope is not None
            and slope > 0
            and up_close_fraction >= config.minimum_up_close_fraction
        ),
        "observable_only": True,
    }


def _rebound_confirmation(normalized: Sequence[Mapping[str, Any]], structure: Mapping[str, Any], config: RuleCandidate) -> dict[str, Any]:
    t_index = len(normalized) - 1
    t_bar = normalized[t_index]
    previous_close = float(normalized[t_index - 1]["close"])
    geometry = _bar_geometry(t_bar, previous_close)
    close = float(t_bar["close"])
    rebound_high = float(structure["rebound_high"])
    return {
        "close_t": close,
        "close_above_rebound_high": close > rebound_high,
        "close_above_previous_close": close > previous_close,
        "positive_body": close > float(t_bar["open"]),
        "close_location": geometry["close_location"],
        "close_location_ok": float(geometry["close_location"]) >= config.confirmation_close_location,
        "confirmation_qualified": (
            close > rebound_high
            and close > previous_close
            and close > float(t_bar["open"])
            and float(geometry["close_location"]) >= config.confirmation_close_location
        ),
        "no_stage_breakout_required": True,
    }


def high_volume_low_progress(
    bars: Sequence[Mapping[str, Any]],
    index: int,
    *,
    baseline_window: int = 20,
    ratio_threshold: float = 2.0,
    body_return_cap: float = 0.005,
    close_location_cap: float = 0.60,
) -> dict[str, Any]:
    normalized = validate_ohlcv_bars(bars)
    if index <= 0 or index >= len(normalized):
        raise IndexError("stall index is outside bars")
    volume = relative_volume_features(normalized, index, baseline_window=baseline_window)
    geometry = _bar_geometry(normalized[index], float(normalized[index - 1]["close"]))
    ratio = volume.get("relative_volume_ratio")
    close_location = float(geometry["close_location"])
    qualifies = (
        isinstance(ratio, (int, float))
        and ratio >= ratio_threshold
        and abs(float(geometry["body_return"])) <= body_return_cap
        and close_location <= close_location_cap
    )
    return {
        "status": volume.get("status"),
        "relative_volume": ratio,
        "ratio_threshold_candidate": ratio_threshold,
        "body_return": geometry["body_return"],
        "close_location": close_location,
        "upper_shadow_fraction": geometry["upper_shadow_fraction"],
        "high_volume_low_price_progress": qualifies,
        "threshold_status": VOLUME_THRESHOLD_STATUS,
        "mechanism_claim": "UNKNOWN; no distribution inference",
    }


def failed_push_features(
    bars: Sequence[Mapping[str, Any]],
    resistance: float,
    *,
    window: int = 5,
    tolerance: float = 0.01,
    start_index: int = 0,
) -> dict[str, Any]:
    normalized = validate_ohlcv_bars(bars)
    if resistance <= 0 or window < 1 or start_index < 0 or start_index > len(normalized):
        raise ValueError("invalid resistance or window")
    start = max(start_index, len(normalized) - window)
    flags: list[bool] = []
    indices = list(range(start, len(normalized)))
    for row in normalized[start:]:
        geometry = _bar_geometry(row, None)
        flags.append(
            float(row["high"]) >= resistance * (1.0 - tolerance)
            and float(row["close"]) < resistance
            and float(geometry["close_location"]) <= 0.60
        )
    consecutive = 0
    for flag in reversed(flags):
        if not flag:
            break
        consecutive += 1
    return {
        "window": window,
        "tolerance": tolerance,
        "requested_start_index": start_index,
        "observed_start_index": start,
        "observed_indices": indices,
        "failed_push_count": sum(flags),
        "consecutive_failed_pushes_at_end": consecutive,
        "failed_pushes": flags,
        "observable_only": True,
    }


def _support_observation(
    normalized: Sequence[Mapping[str, Any]],
    structure: Mapping[str, Any],
    config: RuleCandidate,
) -> dict[str, Any]:
    """Separate support wicks, close breaks, and pre-T support destruction."""

    t_index = len(normalized) - 1
    floor = float(structure["support_floor"])
    pullback_start = int(structure["pullback_start_index"])
    pullback_end = int(structure["pullback_end_exclusive"])
    pullback_rows = normalized[pullback_start:pullback_end]
    pullback_close_break_indices = [
        pullback_start + offset
        for offset, row in enumerate(pullback_rows)
        if float(row["close"]) < floor
    ]
    pullback_puncture_recovery_indices = [
        pullback_start + offset
        for offset, row in enumerate(pullback_rows)
        if float(row["low"]) < floor and float(row["close"]) >= floor
    ]
    current = normalized[t_index]
    t_close_break = float(current["close"]) < floor
    t_intraday_puncture_recovered = float(current["low"]) < floor and not t_close_break
    pullback_support_destroyed = bool(pullback_close_break_indices)
    if t_close_break:
        status = "T_CLOSE_BREAK"
    elif pullback_support_destroyed:
        status = "PULLBACK_SUPPORT_DESTROYED"
    elif t_intraday_puncture_recovered:
        status = "T_INTRADAY_PUNCTURE_RECOVERED"
    elif pullback_puncture_recovery_indices:
        status = "PULLBACK_INTRADAY_PUNCTURE_RECOVERED"
    else:
        status = "INTACT"
    return {
        "status": status,
        "support_floor": floor,
        "support_ceiling": float(structure["support_ceiling"]),
        "support_tolerance": config.support_tolerance,
        "support_tolerance_role": SUPPORT_TOLERANCE_ROLE,
        "support_display_buffer": floor * config.support_tolerance,
        "t_intraday_puncture_recovered": t_intraday_puncture_recovered,
        "t_close_break": t_close_break,
        "pullback_intraday_puncture_recovery_indices": pullback_puncture_recovery_indices,
        "pullback_close_break_indices": pullback_close_break_indices,
        "pullback_support_destroyed": pullback_support_destroyed,
        "entry_support_ok": not pullback_support_destroyed and not t_close_break,
        "pullback_interval": {
            "start_index": pullback_start,
            "end_index_exclusive": pullback_end,
            "includes_t_bar": False,
        },
    }


def _resistance_rejection(
    row: Mapping[str, Any],
    resistance: float,
    tolerance: float,
) -> tuple[bool, dict[str, float | None]]:
    geometry = _bar_geometry(row, None)
    qualifies = (
        float(row["high"]) >= resistance * (1.0 - tolerance)
        and float(row["close"]) < resistance
        and float(geometry["close_location"]) <= 0.60
    )
    return qualifies, geometry


def limit_up_failure_status(bar: Mapping[str, Any]) -> dict[str, Any]:
    """Classify daily limit-up touch only when the limit price is supplied."""

    limit_up = _finite(bar.get("limit_up_price"))
    tick = _finite(bar.get("tick_size"))
    high = _finite(bar.get("high"))
    close = _finite(bar.get("close"))
    if limit_up is None or tick is None or high is None or close is None:
        return {
            "status": UNAVAILABLE,
            "reason": "LIMIT_PRICE_OR_TICK_NOT_SUPPLIED; daily OHLCV cannot reconstruct intraday sequence",
            "limit_up_touched": None,
            "limit_up_failed_to_hold": None,
        }
    tolerance = tick / 2.0
    touched = high >= limit_up - tolerance
    failed = touched and close < limit_up - tolerance
    return {
        "status": "AVAILABLE_DAILY_PROXY",
        "limit_up_price": limit_up,
        "tick_size": tick,
        "limit_up_touched": touched,
        "limit_up_failed_to_hold": failed,
        "intraday_order_known": False,
    }


def normalize_security_name(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "").strip().upper()


def classify_c_universe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Apply C's independent Main Board + non-ST identity gate fail-closed."""

    symbol = str(row.get("symbol", "")).strip().upper()
    board = classify_board(symbol)
    if board != BOARD_MAIN:
        return {"status": "EXCLUDED_BOARD", "symbol": symbol, "board": board}
    name = normalize_security_name(row.get("name"))
    if not name:
        return {"status": "UNRESOLVED_ST_STATUS", "symbol": symbol, "board": board, "reason": "missing name"}
    if row.get("st_status_known_at_t") is not True:
        return {"status": "UNRESOLVED_ST_STATUS", "symbol": symbol, "board": board, "reason": "status is not PIT-attested"}
    if _ST_PREFIX.match(name):
        return {"status": "EXCLUDED_ST_OR_STAR_ST", "symbol": symbol, "board": board, "name": name}
    return {"status": "ELIGIBLE", "symbol": symbol, "board": board, "name": name}


def build_entry_observation(
    bars: Sequence[Mapping[str, Any]],
    *,
    rule_id: str,
) -> dict[str, Any]:
    """Build an outcome-blind C entry observation for a synthetic or future T prefix."""

    try:
        config = RULE_CANDIDATES[rule_id]
    except KeyError as exc:
        raise ValueError(f"unknown C rule candidate: {rule_id}") from exc
    normalized = validate_ohlcv_bars(bars)
    trend = trend_features(normalized, config)
    structure = find_pullback_structure(normalized, config)
    if trend.get("status") != "OK" or structure.get("status") != "OK":
        return {
            "schema_version": C_ENTRY_SCHEMA,
            "namespace": C_RESEARCH_NAMESPACE,
            "strategy_version": C_STRATEGY_VERSION,
            "rule_id": rule_id,
            "signal_timing": SIGNAL_TIMING,
            "earliest_execution": EARLIEST_EXECUTION,
            "same_day_sell": SAME_DAY_SELL_POLICY,
            "entry_candidate": False,
            "trend": trend,
            "structure": structure,
            "future_data_used": False,
        }
    confirmation = _rebound_confirmation(normalized, structure, config)
    support = _support_observation(normalized, structure, config)
    pullback_start = int(structure["pullback_start_index"])
    pullback_end = int(structure["pullback_end_exclusive"])
    reference_start = max(0, pullback_start - config.volume_baseline_window)
    volume = volume_path_features(
        normalized,
        pullback_start=pullback_start,
        pullback_end_exclusive=pullback_end,
        reference_start=reference_start,
        reference_end_exclusive=pullback_start,
    )
    t_volume = relative_volume_features(normalized, len(normalized) - 1, baseline_window=config.volume_baseline_window)
    stage_high = float(structure["stage_prior_high"])
    close_t = float(normalized[-1]["close"])
    resistance_distance = stage_high / close_t - 1.0
    return {
        "schema_version": C_ENTRY_SCHEMA,
        "namespace": C_RESEARCH_NAMESPACE,
        "strategy_version": C_STRATEGY_VERSION,
        "rule_id": rule_id,
        "signal_timing": SIGNAL_TIMING,
        "earliest_execution": EARLIEST_EXECUTION,
        "same_day_sell": SAME_DAY_SELL_POLICY,
        "entry_candidate": bool(
            trend["trend_qualified"]
            and confirmation["confirmation_qualified"]
            and support["entry_support_ok"]
        ),
        "trend": trend,
        "structure": structure,
        "confirmation": confirmation,
        "support": {
            **support,
            "support_pre_determined_before_t": True,
            "pivot_confirmation_timing": structure["pivot_confirmation_timing"],
            "pivot_uses_t_bar": structure["pivot_uses_t_bar"],
        },
        "stage_resistance": {
            "stage_prior_high": stage_high,
            "distance_from_close": resistance_distance,
            "near_resistance": resistance_distance >= 0 and resistance_distance <= config.resistance_tolerance,
            "headroom_is_diagnostic_not_breakout_gate": True,
        },
        "volume": {
            "t_day_relative_volume": t_volume,
            "pullback_path": volume,
            "interpretation": "OBSERVABLE_ONLY; contraction is not accumulation proof",
            "volume_is_not_a_required_gate_in_PRICE_STRUCTURE_BASELINE": True,
        },
        "execution": {
            "entry_reference": "T_PLUS_ONE_OPEN_OR_OTHER_PRE_REGISTERED_REFERENCE",
            "reference_execution_semantics": REFERENCE_EXECUTION_NOT_ACTUAL_FILL,
            "intraday_exit_simulation_allowed": False,
        },
        "future_data_used": False,
    }


def classify_exit_observation(
    bars: Sequence[Mapping[str, Any]],
    *,
    entry_index: int,
    entry_price: float,
    stage_prior_high: float,
    support_floor: float,
    rule_id: str,
    early_defense_version: str = DEFAULT_EARLY_DEFENSE_VERSION,
) -> dict[str, Any]:
    """Classify one explicit early-defense observation version; never claims a fill."""

    config = RULE_CANDIDATES.get(rule_id)
    if config is None:
        raise ValueError(f"unknown C rule candidate: {rule_id}")
    if early_defense_version not in EARLY_DEFENSE_VERSIONS:
        raise ValueError(f"unknown early defense version: {early_defense_version}")
    normalized = validate_ohlcv_bars(bars)
    t_index = len(normalized) - 1
    if entry_index < 0 or entry_index >= len(normalized):
        raise ValueError("entry_index is outside bars")
    entry = _positive(entry_price)
    floor = _positive(support_floor)
    resistance = _positive(stage_prior_high)
    if t_index <= entry_index:
        return {
            "schema_version": C_EXIT_SCHEMA,
            "namespace": C_RESEARCH_NAMESPACE,
            "strategy_version": C_STRATEGY_VERSION,
            "exit_state": "ENTRY_SESSION_NOT_SELLABLE",
            "exit_action": "NONE",
            "same_day_sell": SAME_DAY_SELL_POLICY,
            "early_defense_version": early_defense_version,
            "price_only_early_defense_candidate": False,
            "price_volume_early_defense_candidate": False,
            "early_profit_taking_candidate": False,
            "early_profit_taking_confirmed": False,
            "future_data_used": False,
        }
    current = normalized[t_index]
    current_resistance_rejection, geometry = _resistance_rejection(
        current,
        resistance,
        config.resistance_tolerance,
    )
    failed = failed_push_features(
        normalized,
        resistance,
        window=config.failed_push_window,
        tolerance=config.resistance_tolerance,
        start_index=entry_index + 1,
    )
    stall = high_volume_low_progress(
        normalized,
        t_index,
        baseline_window=config.volume_baseline_window,
        ratio_threshold=config.anomaly_ratio_candidate,
    )
    current_failed_push = bool(current_resistance_rejection)
    post_entry_prior_failed_push_count = int(failed["failed_push_count"]) - int(current_failed_push)
    first_resistance_rejection_warning = current_failed_push and post_entry_prior_failed_push_count == 0
    repeated_resistance_rejection = current_failed_push and post_entry_prior_failed_push_count >= 1
    high_volume_low_progress_near_resistance = (
        current_resistance_rejection and bool(stall["high_volume_low_price_progress"])
    )
    support_intraday_puncture_recovered = float(current["low"]) < floor and float(current["close"]) >= floor
    support_break = float(current["close"]) < floor
    price_only_early_defense = (
        float(current["close"]) > entry
        and repeated_resistance_rejection
        and int(failed["failed_push_count"]) >= config.failed_push_count_candidate
    )
    price_volume_early_defense = price_only_early_defense and high_volume_low_progress_near_resistance
    early_profit = (
        price_only_early_defense
        if early_defense_version == PRICE_ONLY_EARLY_DEFENSE
        else price_volume_early_defense
    )
    repeated_resistance_rejection_risk = repeated_resistance_rejection and not early_profit
    if support_break:
        exit_state = "KEY_SUPPORT_BREAK"
        exit_class = "PROFIT_PROTECTION" if float(current["close"]) > entry else "ENTRY_RISK"
        action = "NEXT_SESSION_REFERENCE_EXIT"
    elif early_profit:
        exit_state = "EARLY_PROFIT_TAKING_CANDIDATE"
        exit_class = "PROFIT_EXIT"
        action = "NEXT_SESSION_REFERENCE_EXIT"
    elif first_resistance_rejection_warning:
        exit_state = "FIRST_RESISTANCE_REJECTION_WARNING"
        exit_class = "WARNING_ONLY"
        action = "NONE"
    elif repeated_resistance_rejection_risk:
        exit_state = "REPEATED_RESISTANCE_REJECTION_RISK"
        exit_class = "WARNING_ONLY"
        action = "NONE"
    else:
        exit_state = "HOLD_OR_REOBSERVE"
        exit_class = "NONE"
        action = "NONE"
    return {
        "schema_version": C_EXIT_SCHEMA,
        "namespace": C_RESEARCH_NAMESPACE,
        "strategy_version": C_STRATEGY_VERSION,
        "as_of_index": t_index,
        "as_of_date": current["date"],
        "entry_index": entry_index,
        "early_defense_version": early_defense_version,
        "exit_state": exit_state,
        "exit_class": exit_class,
        "exit_action": action,
        "warning": first_resistance_rejection_warning,
        "current_resistance_rejection": current_resistance_rejection,
        "current_resistance_geometry": geometry,
        "first_resistance_rejection_warning": first_resistance_rejection_warning,
        "repeated_resistance_rejection": repeated_resistance_rejection,
        "repeated_resistance_rejection_risk": repeated_resistance_rejection_risk,
        "post_entry_prior_failed_push_count": post_entry_prior_failed_push_count,
        "price_only_early_defense_candidate": price_only_early_defense,
        "price_volume_early_defense_candidate": price_volume_early_defense,
        "early_profit_taking_candidate": early_profit,
        "early_profit_taking_confirmed": early_profit,
        "failed_push_features": failed,
        "high_volume_low_progress": stall,
        "high_volume_low_progress_near_resistance": high_volume_low_progress_near_resistance,
        "volume_confirmation_required": early_defense_version == PRICE_VOLUME_EARLY_DEFENSE,
        "volume_confirmation": {
            "status": "QUALIFIED" if high_volume_low_progress_near_resistance else "NOT_QUALIFIED",
            "observable": "HIGH_VOLUME_LOW_PRICE_PROGRESS_AT_STAGE_RESISTANCE",
            "ratio_threshold_candidate": config.anomaly_ratio_candidate,
            "robust_z_threshold_candidate": config.anomaly_robust_z_candidate,
            "threshold_status": VOLUME_THRESHOLD_STATUS,
            "used_for_selected_version": early_defense_version == PRICE_VOLUME_EARLY_DEFENSE,
        },
        "support_intraday_puncture_recovered": support_intraday_puncture_recovered,
        "support_break": support_break,
        "entry_price": entry,
        "close_t": float(current["close"]),
        "same_day_sell": SAME_DAY_SELL_POLICY,
        "earliest_execution": "NEXT_XSHG_SESSION_AFTER_AS_OF_T",
        "reference_execution_semantics": REFERENCE_EXECUTION_NOT_ACTUAL_FILL,
        "intraday_exit_simulation_allowed": False,
        "future_data_used": False,
    }


def _guarded_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def build_data_dependency_check(
    manifest_path: Path,
    *,
    project_root: Path,
) -> dict[str, Any]:
    """Inspect only the frozen input manifest and local file presence."""

    manifest_path = manifest_path.resolve()
    project_root = project_root.resolve()
    path_text = str(manifest_path).lower().replace("\\", "/")
    if "continuous_speed_probe" in path_text or "final_oos" in path_text:
        raise RuntimeError("forbidden research path")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    adjustment = manifest.get("adjustment_semantics", {})
    provenance = manifest.get("provenance", {})
    raw_inputs = provenance.get("raw_inputs", {})
    raw_files = raw_inputs.get("files", [])
    artifact_rows: list[dict[str, Any]] = []
    for raw in raw_files:
        logical = str(raw.get("path", ""))
        local = project_root / logical
        local_present = local.is_file()
        local_sha256 = file_sha256(local) if local_present else None
        declared_sha256 = raw.get("sha256")
        if not local_present:
            sha256_status = "NOT_VERIFIABLE_MISSING"
        elif not declared_sha256:
            sha256_status = "NOT_VERIFIABLE_NO_DECLARED_SHA256"
        elif local_sha256 == declared_sha256:
            sha256_status = "MATCH"
        else:
            sha256_status = "MISMATCH"
        artifact_rows.append({
            "logical_path": logical,
            "declared_sha256": declared_sha256,
            "declared_bytes": raw.get("bytes"),
            "local_present": local_present,
            "local_sha256": local_sha256,
            "local_sha256_status": sha256_status,
            "local_path": _guarded_relative(local, project_root),
        })
    daily_k = next((row for row in artifact_rows if row["logical_path"].endswith("daily_k.parquet")), None)
    if daily_k is None:
        local_replay_status = "DAILY_K_NOT_DECLARED"
    elif daily_k["local_sha256_status"] == "NOT_VERIFIABLE_MISSING":
        local_replay_status = "NOT_READY_IN_THIS_WORKTREE"
    elif daily_k["local_sha256_status"] == "MISMATCH":
        local_replay_status = "LOCAL_ARTIFACT_HASH_MISMATCH"
    elif daily_k["local_sha256_status"] == "MATCH":
        local_replay_status = "LOCAL_ARTIFACT_HASH_MATCH"
    else:
        local_replay_status = "LOCAL_ARTIFACT_HASH_UNVERIFIED"
    checks = {
        "ohlcv": {
            "status": "DECLARED_IN_FROZEN_MANIFEST",
            "required_fields": list(REQUIRED_OHLCV_FIELDS),
            "price_basis": adjustment.get("name"),
            "volume_basis": adjustment.get("volume_semantics"),
            "no_turnover_requirement": True,
        },
        "local_replay": {
            "scope": "THIS_WORKTREE_ONLY",
            "status": local_replay_status,
            "daily_k_local_present": bool(daily_k and daily_k["local_present"]),
            "daily_k_local_sha256_status": daily_k["local_sha256_status"] if daily_k else "NOT_DECLARED",
            "formal_history_not_fetched": True,
        },
        "calendar": {
            "status": "PASS_METADATA",
            "schedule": manifest.get("signal_date_schedule"),
            "window": "769 frozen continuous XSHG sessions from 2023-06-30 through 2026-08-28",
            "timezone": "Asia/Shanghai",
            "execution": EARLIEST_EXECUTION,
        },
        "known_at": {
            "historical_per_bar_vintage_proof": provenance.get("known_at_vintage_proof"),
            "status": "PARTIAL_UNVERIFIED",
            "restriction": "no retrospective C outcome research until per-bar timing evidence is resolved or scope is explicitly limited",
        },
        "corporate_actions": {
            "status": "SIGNAL_PRICE_DEFINITION_AVAILABLE",
            "event_filter": adjustment.get("event_filter"),
            "future_event_rows_after_dataset_end": provenance.get("corporate_actions", {}).get("future_event_rows_after_dataset_end"),
            "signal_policy": "use only T-known/raw or T-anchor evidence; never let future events change a T signal",
        },
        "universe": {
            "board_policy": C_MAIN_BOARD_NON_ST_POLICY,
            "board_classifier": "ASHARE_BOARD_TAXONOMY_V1 / Main=00,60; ChiNext=30; STAR=68",
            "st_status": "UNRESOLVED_FOR_HISTORICAL_PIT_UNIVERSE",
            "rule": "C requires explicit T-known ST/*ST status; current names cannot backfill historical status",
        },
        "volume": {
            "daily_volume": "AVAILABLE_AS_RAW_UNADJUSTED_VOLUME_METADATA",
            "relative_volume": "COMPUTABLE_FROM_PRE_T_DAILY_VOLUME",
            "up_down_median_ratio": "COMPUTABLE_ONLY_WITH_AT_LEAST_TWO_EFFECTIVE_DAYS_PER_DIRECTION",
            "intraday_sequence": "UNAVAILABLE",
            "order_book_or_fill": "UNAVAILABLE",
            "limit_up_ban_or_blast": "ONLY_IF_VALID_LIMIT_PRICE_AND_TICK_ARE_SUPPLIED; otherwise UNKNOWN",
        },
        "execution": {
            "signal": SIGNAL_TIMING,
            "earliest_execution": EARLIEST_EXECUTION,
            "new_position_same_day_sell": SAME_DAY_SELL_POLICY,
            "no_close_after_signal_simulation": True,
            "unknown_fill_policy": EXECUTION_UNCERTAIN,
        },
    }
    return {
        "schema_version": C_DATA_CHECK_SCHEMA,
        "namespace": C_RESEARCH_NAMESPACE,
        "strategy_version": C_STRATEGY_VERSION,
        "source_manifest": {
            "path": _guarded_relative(manifest_path, project_root),
            "file_sha256": file_sha256(manifest_path),
            "schema_version": manifest.get("schema_version"),
            "source": provenance.get("source"),
            "acquisition_date": provenance.get("acquisition_date"),
        },
        "artifact_identities": artifact_rows,
        "checks": checks,
        "c_outcome_accessed": False,
        "formal_historical_return_research_run": False,
        "final_oos_read": False,
        "forbidden_directory_touched": False,
        "b_code_or_runtime_state_modified": False,
        "output_namespace": C_OUTPUT_ROOT.as_posix(),
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("data-check", help="inspect frozen input metadata and local presence only")
    check.add_argument("--manifest", type=Path, default=Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"))
    check.add_argument("--project-root", type=Path, default=Path("."))
    check.add_argument("--output", type=Path, default=C_OUTPUT_ROOT / "data_dependency_check.json")
    rules = subparsers.add_parser("rules", help="print the outcome-blind candidate matrix")
    rules.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "data-check":
        result = build_data_dependency_check(args.manifest, project_root=args.project_root)
        write_json(args.output, result)
        print(json.dumps({"status": "WRITTEN", "path": args.output.as_posix(), "schema_version": C_DATA_CHECK_SCHEMA}, ensure_ascii=False, sort_keys=True))
        return 0
    payload = {
        "namespace": C_RESEARCH_NAMESPACE,
        "strategy_version": C_STRATEGY_VERSION,
        "rule_candidates": {key: asdict(value) for key, value in RULE_CANDIDATES.items()},
        "outcome_accessed": False,
    }
    if args.output is not None:
        write_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "C_DATA_CHECK_SCHEMA",
    "C_ENTRY_SCHEMA",
    "C_EXIT_SCHEMA",
    "C_OUTPUT_ROOT",
    "C_RESEARCH_NAMESPACE",
    "C_SIGNAL_OUTPUT_ROOT",
    "C_EXIT_OUTPUT_ROOT",
    "C_STRATEGY_VERSION",
    "DEFAULT_EARLY_DEFENSE_VERSION",
    "EARLY_DEFENSE_VERSIONS",
    "EARLIEST_EXECUTION",
    "PRICE_ONLY_EARLY_DEFENSE",
    "PRICE_VOLUME_EARLY_DEFENSE",
    "RULE_CANDIDATES",
    "RuleCandidate",
    "build_data_dependency_check",
    "build_entry_observation",
    "canonical_json",
    "classify_c_universe_row",
    "classify_exit_observation",
    "failed_push_features",
    "find_pullback_structure",
    "high_volume_low_progress",
    "limit_up_failure_status",
    "relative_volume_features",
    "trend_features",
    "validate_ohlcv_bars",
    "volume_path_features",
]


if __name__ == "__main__":
    raise SystemExit(main())
