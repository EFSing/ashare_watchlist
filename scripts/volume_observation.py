"""Pure, report-only volume observations from stock K-lines.

This module intentionally knows nothing about market-universe discovery,
snapshots, Formal B evaluation, or shadow-store persistence.  It consumes the
stock K-lines already present in a T-close generation package and produces a
small independent observation store for the renderer.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from b_phase_volume_path_diagnostic import _first_breakout_trace


VOLUME_OBSERVATION_STORE_SCHEMA = "B_VOLUME_OBSERVATION_STORE_V1"
VOLUME_OBSERVATION_VERSION = "B_VOLUME_PROSPECTIVE_REPORT_OBSERVATION_V1"
VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA = "cebda9ec8d8c085424e4b674a3353204e90bd7a0"
VOLUME_OBSERVATION_FIELDS = (
    "down_volume_share",
    "up_down_volume_ratio",
    "pullback_volume_decay_ratio",
)


def _empty_volume_observation(reason: str, *, window_days: int | None = None) -> dict[str, Any]:
    return {
        "observation_version": VOLUME_OBSERVATION_VERSION,
        "protocol_commit_sha": VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
        "window_days": window_days,
        **{field: None for field in VOLUME_OBSERVATION_FIELDS},
        "missing_reason": {field: reason for field in VOLUME_OBSERVATION_FIELDS},
    }


def _safe_volume_ratio(numerator: float, denominator: float) -> tuple[float | None, str | None]:
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None, "NON_FINITE_NUMERATOR_OR_DENOMINATOR"
    if denominator == 0:
        return None, "ZERO_DENOMINATOR"
    result = numerator / denominator
    if not math.isfinite(result):
        return None, "NON_FINITE_RESULT"
    return float(result), None


def _finite_volume_mean(values: np.ndarray) -> float | None:
    if len(values) == 0 or not np.all(np.isfinite(values)):
        return None
    result = float(np.mean(values))
    return result if math.isfinite(result) else None


def calculate_pullback_volume_observation(
    close: np.ndarray,
    volume: np.ndarray,
    breakout_index: int,
) -> dict[str, Any]:
    """Calculate the frozen observables for the pullback window ``R=i+1:T-1``."""

    signal_index = len(close) - 1
    pullback_close = np.asarray(close[breakout_index + 1:signal_index], dtype=float)
    pullback_volume = np.asarray(volume[breakout_index + 1:signal_index], dtype=float)
    result: dict[str, Any] = {
        "observation_version": VOLUME_OBSERVATION_VERSION,
        "protocol_commit_sha": VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
        "window_days": int(len(pullback_volume)),
        **{field: None for field in VOLUME_OBSERVATION_FIELDS},
        "missing_reason": {},
    }

    if len(pullback_close) == 0:
        result["missing_reason"] = {
            field: "NO_PULLBACK_WINDOW" for field in VOLUME_OBSERVATION_FIELDS
        }
        return result

    previous_close = np.asarray(close[breakout_index:signal_index], dtype=float)[:len(pullback_close)]
    up = pullback_close > previous_close
    down = pullback_close < previous_close

    total_volume = float(np.sum(pullback_volume)) if np.all(np.isfinite(pullback_volume)) else math.nan
    if not math.isfinite(total_volume) or total_volume <= 0:
        result["missing_reason"]["down_volume_share"] = "INVALID_PULLBACK_VOLUME_SUM"
    else:
        value, reason = _safe_volume_ratio(float(np.sum(pullback_volume[down])), total_volume)
        result["down_volume_share"] = value
        if reason:
            result["missing_reason"]["down_volume_share"] = reason

    if not np.any(up) or not np.any(down):
        result["missing_reason"]["up_down_volume_ratio"] = "NO_UP_OR_DOWN_DAY"
    else:
        up_mean = _finite_volume_mean(pullback_volume[up])
        down_mean = _finite_volume_mean(pullback_volume[down])
        if up_mean is None or down_mean is None or down_mean <= 0:
            result["missing_reason"]["up_down_volume_ratio"] = "INVALID_UP_OR_DOWN_VOLUME"
        else:
            value, reason = _safe_volume_ratio(up_mean, down_mean)
            result["up_down_volume_ratio"] = value
            if reason:
                result["missing_reason"]["up_down_volume_ratio"] = reason

    if len(pullback_volume) < 4:
        result["missing_reason"]["pullback_volume_decay_ratio"] = "PULLBACK_WINDOW_LT_4"
    else:
        split = len(pullback_volume) // 2
        first_mean = _finite_volume_mean(pullback_volume[:split])
        second_mean = _finite_volume_mean(pullback_volume[split:])
        if first_mean is None or second_mean is None or first_mean <= 0:
            result["missing_reason"]["pullback_volume_decay_ratio"] = "INVALID_PULLBACK_HALF_VOLUME"
        else:
            value, reason = _safe_volume_ratio(second_mean, first_mean)
            result["pullback_volume_decay_ratio"] = value
            if reason:
                result["missing_reason"]["pullback_volume_decay_ratio"] = reason
    return result


def _number(value: Any, field: str, *, non_negative: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field}: boolean is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field}: non-finite")
    if non_negative and number < 0:
        raise ValueError(f"{field}: negative")
    return number


def calculate_stock_volume_observation(
    bars: Sequence[Mapping[str, Any]] | None,
    signal_date: str,
    *,
    code: str = "UNKNOWN",
) -> dict[str, Any]:
    """Calculate one observation from one stock's already-acquired K-lines."""

    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)) or not bars:
        return _empty_volume_observation("STOCK_KLINE_NOT_IN_INPUT_PACKAGE")
    normalized: list[Mapping[str, Any]] = []
    previous_date: str | None = None
    try:
        for index, raw in enumerate(bars):
            if not isinstance(raw, Mapping):
                return _empty_volume_observation(f"INVALID_STOCK_KLINE:{code}:BAR_NOT_OBJECT")
            bar_date = str(raw.get("date") or "")
            if not bar_date or (previous_date is not None and bar_date < previous_date):
                return _empty_volume_observation(f"INVALID_STOCK_KLINE:{code}:DATE_ORDER")
            if bar_date > signal_date:
                return _empty_volume_observation(f"FUTURE_DATA_DETECTED:{bar_date}")
            _number(raw.get("close"), f"{code}[{index}].close")
            _number(raw.get("high"), f"{code}[{index}].high")
            _number(raw.get("low"), f"{code}[{index}].low")
            _number(raw.get("volume"), f"{code}[{index}].volume", non_negative=True)
            normalized.append(raw)
            previous_date = bar_date
    except (TypeError, ValueError) as exc:
        return _empty_volume_observation(f"INVALID_STOCK_KLINE:{code}:{type(exc).__name__}")

    if not normalized or str(normalized[-1].get("date")) != signal_date:
        latest = str(normalized[-1].get("date")) if normalized else "NONE"
        return _empty_volume_observation(f"STOCK_KLINE_T_CLOSE_UNAVAILABLE:{latest}")
    try:
        close = np.asarray([_number(item.get("close"), f"{code}.close") for item in normalized], dtype=float)
        high = np.asarray([_number(item.get("high"), f"{code}.high") for item in normalized], dtype=float)
        low = np.asarray([_number(item.get("low"), f"{code}.low") for item in normalized], dtype=float)
        volume = np.asarray([_number(item.get("volume"), f"{code}.volume", non_negative=True) for item in normalized], dtype=float)
        trace = _first_breakout_trace(close, volume, high, low, [str(item["date"]) for item in normalized])
    except (TypeError, ValueError, ZeroDivisionError, FloatingPointError) as exc:
        return _empty_volume_observation(f"VOLUME_PATH_CALCULATION_FAILED:{type(exc).__name__}")
    if trace is None:
        return _empty_volume_observation("B_BREAKOUT_TRACE_UNAVAILABLE")
    return calculate_pullback_volume_observation(close, volume, int(trace["breakout_index"]))


def build_volume_observation_store(
    candidates: Sequence[Mapping[str, Any]],
    generation_input_manifest: Mapping[str, Any],
    signal_date: str,
    *,
    source_mode: str = "LIVE_T_CLOSE_STOCK_KLINE",
) -> dict[str, Any]:
    """Build independent observations without requiring an index K-line."""

    stock_klines = generation_input_manifest.get("stock_klines")
    by_code: dict[str, Any] = {}
    if isinstance(stock_klines, list):
        for item in stock_klines:
            if isinstance(item, Mapping):
                by_code[str(item.get("symbol", "")).zfill(6)] = item.get("bars")

    observations: dict[str, dict[str, Any]] = {}
    complete = 0
    for candidate in candidates:
        code = str(candidate.get("code", "")).zfill(6)
        signal_id = str(candidate.get("signal_id") or "")
        observation = calculate_stock_volume_observation(
            by_code.get(code), signal_date, code=code,
        )
        if all(observation.get(field) is not None for field in VOLUME_OBSERVATION_FIELDS):
            complete += 1
        observations[signal_id] = {
            "signal_id": signal_id,
            "code": code,
            "name": candidate.get("name"),
            "observation": observation,
        }
    return {
        "schema_version": VOLUME_OBSERVATION_STORE_SCHEMA,
        "report_date": signal_date,
        "source_mode": source_mode,
        "observational_only": True,
        "participates_in_ranking": False,
        "candidate_count": len(observations),
        "complete_count": complete,
        "status": "COMPLETE" if complete == len(observations) else "PARTIAL",
        "observations": observations,
    }


def write_volume_observation_store(path: str | Path, store: Mapping[str, Any]) -> Path:
    """Atomically persist the small independent durable observation store."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(store, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target


def load_volume_observation_store(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None
