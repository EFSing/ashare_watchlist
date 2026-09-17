"""Prospective, observational shadow monitoring for frozen B V1_1 signals.

The monitor is deliberately downstream of canonical generation.  It records
T-close context and later replays only the existing trigger/stop/target rule
price semantics.  Nothing in this module is consulted by qualification,
ranking, trigger, stop, target, RR, or canonical watchlist generation.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import tempfile
from typing import Any, Mapping

import numpy as np

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
from b_phase_volume_path_diagnostic import _board, _first_breakout_trace
from data_paths import DataPaths
from trading_calendar import TradingCalendar, default_calendar
from watchlist_schema import load_watchlist


MONITOR_VERSION = "PROSPECTIVE_B_SHADOW_MONITOR_V1"
STORE_SCHEMA_VERSION = "B_SHADOW_MONITOR_STORE_V1"
CAPTURE_PROSPECTIVE = "PROSPECTIVE_CAPTURED"
CAPTURE_RETROSPECTIVE = "RETROSPECTIVE_RECONSTRUCTED"
CAPTURE_COMPLETE = "COMPLETE"
CAPTURE_INCOMPLETE = "SHADOW_CAPTURE_INCOMPLETE"
STATUS_EVIDENCE_ACCUMULATING = "EVIDENCE_ACCUMULATING"

TREND_UP = "TREND_UP"
TREND_NEUTRAL = "TREND_NEUTRAL"
TREND_DOWN = "TREND_DOWN"
VOL_LOW = "VOL_LOW"
VOL_NORMAL = "VOL_NORMAL"
VOL_HIGH = "VOL_HIGH"

OUTCOME_TARGET = "TARGET"
OUTCOME_STOP = "STOP"
OUTCOME_OPEN = "OPEN"
OUTCOME_UNTRIGGERED = "UNTRIGGERED"
OUTCOME_AMBIGUOUS = "AMBIGUOUS"

REGIME_DEFINITION_VERSION = "B_SHADOW_MARKET_REGIME_DEFINITION_V1"
VOLUME_DEFINITION_VERSION = "B_SHADOW_REACTIVATION_VOLUME_PATH_V1"
VOLUME_OBSERVATION_VERSION = "B_VOLUME_PROSPECTIVE_REPORT_OBSERVATION_V1"
VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA = "cebda9ec8d8c085424e4b674a3353204e90bd7a0"
FAST_STOP_DEFINITION = "STOP on first or second sellable XSHG session (D+1 or D+2)"
RECOVERY_HORIZONS = (3, 5, 10)
VOL_LOW_MAX_DAILY_STD_PCT = 1.0
VOL_HIGH_MIN_DAILY_STD_PCT = 2.0

REFERENCE_FAST_STOP_RATE = 46.221786
REFERENCE_RECENT_FAST_STOP_RATE = 79.487179
REFERENCE_ARTIFACT = "recent_b_underperformance_diagnostic/stop_timing.json"
REFERENCE_ARTIFACT_SHA256 = "2b5c168ead3a99f993188e3051b09e8c8b82c418d1bc59180c248920128acd3f"
REFERENCE_DECISION_SHA256 = "6dd4080da55b196dc0decd20aa2956a28eb51dad0fccaea9802f86049e3119d6"

_BJT = timezone(timedelta(hours=8))
_PRE_OUTCOME_IGNORED_FIELDS = {"captured_at_bjt"}
_CONTEXT_FIELDS = (
    "score",
    "distance_from_base_hi_pct",
    "signal_day_return_pct",
    "close_position_in_day_range",
    "close_vs_ma5",
    "pos250",
    "pullback_stage",
    "board",
)
_REACTIVATION_FIELDS = (
    "breakout_volume_ratio",
    "pre_t_retest_volume_ratio",
    "reactivation_vs_retest_ratio",
    "reactivation_vs_breakout_ratio",
)
_VOLUME_OBSERVATION_FIELDS = (
    "down_volume_share",
    "up_down_volume_ratio",
    "pullback_volume_decay_ratio",
)


class ShadowMonitorError(ValueError):
    """Fail-closed shadow identity or input error."""

    def __init__(self, status: str, message: str) -> None:
        self.status = status
        super().__init__(f"{status}: {message}")


def _canonical_json(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ShadowMonitorError("SHADOW_NON_CANONICAL_VALUE", str(exc)) from exc
    return (text + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ShadowMonitorError("SHADOW_SOURCE_READ_FAILURE", f"{path}: {exc}") from exc
    return digest.hexdigest()


def _parse_date(value: Any) -> date:
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        parsed = date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise ShadowMonitorError("SHADOW_DATE_INVALID", f"invalid date {value!r}") from exc
    return parsed


def _date_text(value: Any) -> str:
    return _parse_date(value).isoformat()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _required_number(value: Any, field: str) -> float:
    result = _number(value)
    if result is None:
        raise ShadowMonitorError("SHADOW_FEATURE_UNAVAILABLE", f"{field} is not finite")
    return result


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _code(value: Any) -> str:
    text = str(value).strip().lower()
    if "." in text:
        text = text.split(".", 1)[0]
    if text[:2] in {"sh", "sz", "bj"}:
        text = text[2:]
    return text


def _now_bjt(value: datetime | str | None = None) -> str:
    if value is None:
        parsed = datetime.now(_BJT)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_BJT)
    return parsed.astimezone(_BJT).isoformat()


def _store_path(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / "b_shadow_monitor.json"


def _definitions() -> dict[str, Any]:
    return {
        "market_regime": {
            "version": REGIME_DEFINITION_VERSION,
            "trend": "close > MA20 and MA20 > MA60 => TREND_UP; close < MA20 and MA20 < MA60 => TREND_DOWN; otherwise TREND_NEUTRAL",
            "volatility": "sample standard deviation of the last 20 daily close returns, in daily percentage points",
            "volatility_thresholds_daily_pct_std": {
                "VOL_LOW": f"<{VOL_LOW_MAX_DAILY_STD_PCT}",
                "VOL_NORMAL": f">={VOL_LOW_MAX_DAILY_STD_PCT} and <{VOL_HIGH_MIN_DAILY_STD_PCT}",
                "VOL_HIGH": f">={VOL_HIGH_MIN_DAILY_STD_PCT}",
            },
            "threshold_selection": "fixed_stable_non_outcome_tuned",
        },
        "reactivation": {
            "version": VOLUME_DEFINITION_VERSION,
            "implementation": "scripts/b_phase_volume_path_diagnostic.py::_first_breakout_trace",
            "threshold_selection": "descriptive_only_no_outcome_threshold",
            "report_grouping": "continuous_median_only_when_no_frozen_bins",
        },
        "volume_observation": {
            "version": VOLUME_OBSERVATION_VERSION,
            "protocol_commit_sha": VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
            "window": "R=i+1:T-1; signal day T excluded",
            "fields": list(_VOLUME_OBSERVATION_FIELDS),
            "observational_only": True,
        },
        "outcome": {
            "entry": "first post-signal XSHG session with high >= canonical trigger; entry price is canonical trigger",
            "exit": "sellable session low <= stop or high >= target at canonical rule price",
            "entry_day": "entry day cannot sell",
            "same_bar": "stop and target on one sellable bar => AMBIGUOUS",
            "time_exit": False,
        },
        "fast_stop": FAST_STOP_DEFINITION,
        "recovery_horizons": [f"+{h} XSHG sessions" for h in RECOVERY_HORIZONS],
    }


def _reference_only() -> dict[str, Any]:
    return {
        "label": "REFERENCE_ONLY",
        "source": "recent_b_underperformance_diagnostic",
        "historical_fast_stop_rate": REFERENCE_FAST_STOP_RATE,
        "recent_fast_stop_rate": REFERENCE_RECENT_FAST_STOP_RATE,
        "artifact": REFERENCE_ARTIFACT,
        "artifact_sha256": REFERENCE_ARTIFACT_SHA256,
        "decision_json_sha256": REFERENCE_DECISION_SHA256,
        "used_for_thresholds": False,
        "used_for_candidate_selection": False,
    }


def new_store() -> dict[str, Any]:
    return {
        "schema_version": STORE_SCHEMA_VERSION,
        "monitor_version": MONITOR_VERSION,
        "status": STATUS_EVIDENCE_ACCUMULATING,
        "strategy": {
            "version": STRATEGY_VERSION,
            "spec_sha256": STRATEGY_SPEC_SHA256,
            "formal_strategy_frozen": True,
            "observational_only": True,
        },
        "prospective_epoch": {
            "start_date": None,
            "capture_mode": CAPTURE_PROSPECTIVE,
            "no_backfill": True,
        },
        "definitions": _definitions(),
        "reference_only": _reference_only(),
        "last_capture": None,
        "updated_at_bjt": None,
        "signals": {},
    }


def _validate_store(store: Any) -> dict[str, Any]:
    if not isinstance(store, dict):
        raise ShadowMonitorError("SHADOW_STORE_CORRUPT", "store must be an object")
    if store.get("schema_version") != STORE_SCHEMA_VERSION or store.get("monitor_version") != MONITOR_VERSION:
        raise ShadowMonitorError("SHADOW_STORE_CORRUPT", "unsupported shadow store schema")
    strategy = store.get("strategy")
    if not isinstance(strategy, Mapping) or strategy.get("version") != STRATEGY_VERSION or strategy.get("spec_sha256") != STRATEGY_SPEC_SHA256:
        raise ShadowMonitorError("SHADOW_STRATEGY_IDENTITY_CONFLICT", "store strategy is not frozen B V1_1")
    if not isinstance(store.get("signals"), dict):
        raise ShadowMonitorError("SHADOW_STORE_CORRUPT", "signals must be keyed by signal_id")
    for signal_id, record in store["signals"].items():
        if not isinstance(record, dict) or record.get("signal_id") != signal_id:
            raise ShadowMonitorError("SHADOW_STORE_CORRUPT", f"signal identity mismatch: {signal_id}")
        if record.get("strategy_version") != STRATEGY_VERSION:
            raise ShadowMonitorError("SHADOW_STRATEGY_IDENTITY_CONFLICT", signal_id)
        if not isinstance(record.get("pre_outcome"), Mapping) or not isinstance(record.get("outcomes"), Mapping):
            raise ShadowMonitorError("SHADOW_STORE_CORRUPT", f"incomplete signal record: {signal_id}")
    return store


def load_store(root: str | Path, *, missing_ok: bool = True) -> dict[str, Any] | None:
    path = _store_path(root)
    if not path.exists():
        return new_store() if missing_ok else None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowMonitorError("SHADOW_STORE_READ_FAILURE", f"{path}: {exc}") from exc
    return _validate_store(value)


def save_store(store: Mapping[str, Any], root: str | Path) -> Path:
    payload = _validate_store(deepcopy(dict(store)))
    destination = _store_path(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(_canonical_json(payload))
            handle.flush()
        temporary.replace(destination)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ShadowMonitorError("SHADOW_STORE_WRITE_FAILURE", f"{destination}: {exc}") from exc
    return destination


def _validated_bars(raw: Any, signal_date: str, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ShadowMonitorError("SHADOW_FEATURE_UNAVAILABLE", f"{label}.bars is unavailable")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ShadowMonitorError("SHADOW_INPUT_CONFLICT", f"{label}.bars[{index}] is not an object")
        bar_date = _date_text(item.get("date"))
        if bar_date in seen:
            raise ShadowMonitorError("SHADOW_INPUT_CONFLICT", f"duplicate {label} bar: {bar_date}")
        seen.add(bar_date)
        if bar_date > signal_date:
            raise ShadowMonitorError("SHADOW_FUTURE_BAR_IN_PRE_OUTCOME", f"{label} includes {bar_date} after {signal_date}")
        result.append({**dict(item), "date": bar_date})
    result.sort(key=lambda item: item["date"])
    return result


def _market_snapshot(index_manifest: Mapping[str, Any], signal_date: str) -> dict[str, Any]:
    unavailable: dict[str, str] = {}
    fields = (
        "index_close_vs_ma20",
        "index_close_vs_ma60",
        "index_return_5d",
        "index_return_20d",
        "index_realized_vol_20d",
        "trend_regime",
        "vol_regime",
    )
    result: dict[str, Any] = {field: None for field in fields}
    result["definition_version"] = REGIME_DEFINITION_VERSION
    try:
        bars = _validated_bars(index_manifest.get("bars"), signal_date, label="index")
    except ShadowMonitorError:
        raise
    if len(bars) < 61:
        reason = f"INDEX_HISTORY_TOO_SHORT:{len(bars)}<61"
        unavailable.update({field: reason for field in fields})
        result["feature_unavailable"] = unavailable
        return result
    try:
        closes = [_required_number(item.get("close"), f"index.close[{item['date']}]") for item in bars]
        close = closes[-1]
        ma20 = statistics.fmean(closes[-20:])
        ma60 = statistics.fmean(closes[-60:])
        returns = [(closes[index] / closes[index - 1] - 1.0) * 100.0 for index in range(1, len(closes))]
        vol20 = statistics.stdev(returns[-20:])
        result.update({
            "index_close_vs_ma20": _round((close / ma20 - 1.0) * 100.0),
            "index_close_vs_ma60": _round((close / ma60 - 1.0) * 100.0),
            "index_return_5d": _round((close / closes[-6] - 1.0) * 100.0),
            "index_return_20d": _round((close / closes[-21] - 1.0) * 100.0),
            "index_realized_vol_20d": _round(vol20),
            "trend_regime": (
                TREND_UP if close > ma20 and ma20 > ma60
                else TREND_DOWN if close < ma20 and ma20 < ma60
                else TREND_NEUTRAL
            ),
            "vol_regime": (
                VOL_LOW if vol20 < VOL_LOW_MAX_DAILY_STD_PCT
                else VOL_HIGH if vol20 >= VOL_HIGH_MIN_DAILY_STD_PCT
                else VOL_NORMAL
            ),
        })
    except ShadowMonitorError as exc:
        unavailable.update({field: exc.status for field in fields})
    except (statistics.StatisticsError, ZeroDivisionError, ValueError) as exc:
        unavailable.update({field: f"MARKET_REGIME_CALCULATION_FAILED:{type(exc).__name__}" for field in fields})
    if unavailable:
        result["feature_unavailable"] = unavailable
    return result


def _empty_volume_observation(reason: str, *, window_days: int | None = None) -> dict[str, Any]:
    return {
        "observation_version": VOLUME_OBSERVATION_VERSION,
        "protocol_commit_sha": VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
        "window_days": window_days,
        **{field: None for field in _VOLUME_OBSERVATION_FIELDS},
        "missing_reason": {field: reason for field in _VOLUME_OBSERVATION_FIELDS},
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


def _pullback_volume_observation(
    close: np.ndarray,
    volume: np.ndarray,
    trace: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate the frozen report-only volume observables for ``R=i+1:T-1``."""

    breakout_index = int(trace["breakout_index"])
    signal_index = len(close) - 1
    pullback_close = np.asarray(close[breakout_index + 1:signal_index], dtype=float)
    pullback_volume = np.asarray(volume[breakout_index + 1:signal_index], dtype=float)
    result: dict[str, Any] = {
        "observation_version": VOLUME_OBSERVATION_VERSION,
        "protocol_commit_sha": VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
        "window_days": int(len(pullback_volume)),
        **{field: None for field in _VOLUME_OBSERVATION_FIELDS},
        "missing_reason": {},
    }

    if len(pullback_close) == 0:
        result["missing_reason"] = {
            field: "NO_PULLBACK_WINDOW" for field in _VOLUME_OBSERVATION_FIELDS
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


def _stock_snapshot(
    candidate: Mapping[str, Any], stock_klines: Any, signal_date: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    code = _code(candidate.get("code"))
    unavailable: dict[str, str] = {}
    trace: dict[str, Any] | None = None
    volume_observation = _empty_volume_observation("STOCK_KLINE_NOT_IN_INPUT_PACKAGE")
    matching: Mapping[str, Any] | None = None
    if isinstance(stock_klines, list):
        for item in stock_klines:
            if isinstance(item, Mapping) and _code(item.get("symbol")) == code:
                matching = item
                break
    if matching is None:
        reason = "STOCK_KLINE_NOT_IN_INPUT_PACKAGE"
        unavailable.update({field: reason for field in (*_REACTIVATION_FIELDS, *_CONTEXT_FIELDS[1:-1])})
    else:
        bars = _validated_bars(matching.get("bars"), signal_date, label=f"stock[{code}]")
        if not bars or bars[-1]["date"] != signal_date:
            reason = f"STOCK_KLINE_T_CLOSE_UNAVAILABLE:{bars[-1]['date'] if bars else 'NONE'}"
            unavailable.update({field: reason for field in (*_REACTIVATION_FIELDS, *_CONTEXT_FIELDS[1:-1])})
            volume_observation = _empty_volume_observation(reason)
        else:
            try:
                close = np.asarray([_required_number(item.get("close"), f"stock[{code}].close") for item in bars], dtype=float)
                high = np.asarray([_required_number(item.get("high"), f"stock[{code}].high") for item in bars], dtype=float)
                low = np.asarray([_required_number(item.get("low"), f"stock[{code}].low") for item in bars], dtype=float)
                volume = np.asarray([_required_number(item.get("volume"), f"stock[{code}].volume") for item in bars], dtype=float)
                trace = _first_breakout_trace(close, volume, high, low, [item["date"] for item in bars])
            except ShadowMonitorError:
                raise
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                unavailable.update({field: f"VOLUME_PATH_CALCULATION_FAILED:{type(exc).__name__}" for field in (*_REACTIVATION_FIELDS, *_CONTEXT_FIELDS[1:-1])})
                volume_observation = _empty_volume_observation(f"VOLUME_PATH_CALCULATION_FAILED:{type(exc).__name__}")
            if trace is None:
                unavailable.update({field: "B_BREAKOUT_TRACE_UNAVAILABLE" for field in (*_REACTIVATION_FIELDS, *_CONTEXT_FIELDS[1:-1])})
                volume_observation = _empty_volume_observation("B_BREAKOUT_TRACE_UNAVAILABLE")
            else:
                volume_observation = _pullback_volume_observation(close, volume, trace)

    reactivation = {field: (trace.get(field) if trace else None) for field in _REACTIVATION_FIELDS}
    reactivation["feature_unavailable"] = {
        **unavailable,
        **(trace.get("feature_unavailable", {}) if trace else {}),
    }
    structural = {
        "score": candidate.get("score"),
        "distance_from_base_hi_pct": trace.get("distance_from_base_hi_pct") if trace else None,
        "signal_day_return_pct": trace.get("signal_day_return_pct") if trace else None,
        "close_position_in_day_range": trace.get("close_position_in_day_range") if trace else None,
        "close_vs_ma5": trace.get("close_vs_ma5") if trace else None,
        "pos250": trace.get("pos250") if trace else None,
        "pullback_stage": trace.get("pullback_stage") if trace else None,
        "board": _board(str(candidate.get("code", ""))),
        "feature_unavailable": {
            **unavailable,
            **({field: "B_BREAKOUT_TRACE_UNAVAILABLE" for field in _CONTEXT_FIELDS[1:-1]} if trace is None else {}),
        },
    }
    return reactivation, structural, volume_observation


def _pre_outcome_semantic(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("captured_at_bjt", None)
    source = result.get("source")
    if isinstance(source, dict):
        source.pop("captured_at_bjt", None)
    return result


def _empty_outcome() -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": OUTCOME_UNTRIGGERED,
        "eligible": False,
        "capture_status": "PENDING_T_PLUS_1",
        "updated_as_of": None,
        "entry_date": None,
        "sellable_from": None,
        "exit_date": None,
        "exit_price": None,
        "holding_sessions": None,
        "realized_return_pct": None,
        "realized_r": None,
        "mfe": None,
        "mae": None,
        "mfe_pct": None,
        "mae_pct": None,
        "entry_day_stop_touched": False,
        "entry_day_target_touched": False,
        "stop_session_index": None,
        "fast_stop": False,
        "missing_sessions": [],
        "last_observation_date": None,
    }
    for horizon in RECOVERY_HORIZONS:
        result[f"post_stop_max_high_{horizon}"] = None
        result[f"recovered_to_entry_{horizon}"] = None
        result[f"reached_original_target_{horizon}"] = None
        result[f"recovery_status_{horizon}"] = "NOT_APPLICABLE"
    return result


def _next_session(value: date, calendar: TradingCalendar) -> date:
    current = value + timedelta(days=1)
    while not calendar.is_trading_day(current):
        current += timedelta(days=1)
    return current


def _sessions_after(value: date, count: int, calendar: TradingCalendar) -> list[date]:
    result: list[date] = []
    current = value
    for _ in range(count):
        current = _next_session(current, calendar)
        result.append(current)
    return result


def _session_index(start: date, end: date, calendar: TradingCalendar) -> int:
    if end <= start:
        return 0
    current = start
    count = 0
    while True:
        current = _next_session(current, calendar)
        if current > end:
            return count
        count += 1


def _observation_map(signal_date: str, tracker_signal: Mapping[str, Any] | None, as_of: date) -> dict[date, Mapping[str, Any]]:
    if not isinstance(tracker_signal, Mapping):
        return {}
    result: dict[date, Mapping[str, Any]] = {}
    for item in tracker_signal.get("observations", []) if isinstance(tracker_signal.get("observations"), list) else []:
        if not isinstance(item, Mapping) or item.get("date") is None:
            continue
        observed = _parse_date(item["date"])
        if observed <= _parse_date(signal_date) or observed > as_of:
            continue
        if observed in result and dict(result[observed]) != dict(item):
            raise ShadowMonitorError("SHADOW_OUTCOME_INPUT_CONFLICT", f"duplicate observation conflict: {observed}")
        result[observed] = item
    return result


def _bar_value(bar: Mapping[str, Any], name: str) -> float | None:
    if name == "close":
        return _number(bar.get("close", bar.get("price")))
    return _number(bar.get(name))


def _recovery_fields(
    result: dict[str, Any],
    *,
    signal: Mapping[str, Any],
    observations: Mapping[date, Mapping[str, Any]],
    as_of: date,
    calendar: TradingCalendar,
) -> None:
    if result.get("status") != OUTCOME_STOP or not result.get("exit_date"):
        return
    stop_date = _parse_date(result["exit_date"])
    entry = _number(signal.get("entry_price")) or _number(signal.get("trigger"))
    target = _number(signal.get("target"))
    for horizon in RECOVERY_HORIZONS:
        days = _sessions_after(stop_date, horizon, calendar)
        if as_of < days[-1]:
            result[f"recovery_status_{horizon}"] = "PENDING"
            continue
        missing = [day.isoformat() for day in days if day not in observations]
        if missing:
            result[f"recovery_status_{horizon}"] = CAPTURE_INCOMPLETE
            result.setdefault("missing_sessions", []).extend(missing)
            continue
        highs = [_bar_value(observations[day], "high") for day in days]
        if any(value is None for value in highs):
            result[f"recovery_status_{horizon}"] = CAPTURE_INCOMPLETE
            continue
        max_high = max(value for value in highs if value is not None)
        result[f"post_stop_max_high_{horizon}"] = _round(max_high)
        result[f"recovered_to_entry_{horizon}"] = entry is not None and max_high >= entry
        result[f"reached_original_target_{horizon}"] = target is not None and max_high >= target
        result[f"recovery_status_{horizon}"] = CAPTURE_COMPLETE


def evaluate_shadow_outcome(
    signal: Mapping[str, Any],
    tracker_signal: Mapping[str, Any] | None,
    as_of_date: date | datetime | str,
    *,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Evaluate one signal without time exit and without mutating its input."""

    cal = calendar or default_calendar()
    as_of = _parse_date(as_of_date)
    signal_date = _parse_date(signal.get("signal_date", signal.get("date")))
    result = _empty_outcome()
    result["updated_as_of"] = as_of.isoformat()
    if as_of <= signal_date:
        return result
    expected_sessions: list[date] = []
    current = _next_session(signal_date, cal)
    while current <= as_of:
        expected_sessions.append(current)
        current = _next_session(current, cal)
    result["eligible"] = bool(expected_sessions)
    result["capture_status"] = CAPTURE_COMPLETE
    observations = _observation_map(signal_date.isoformat(), tracker_signal, as_of)
    result["last_observation_date"] = max(observations).isoformat() if observations else None
    trigger = _number(signal.get("trigger"))
    stop = _number(signal.get("stop"))
    target = _number(signal.get("target"))
    if trigger is None or stop is None or target is None or trigger <= stop or target <= trigger:
        result["capture_status"] = CAPTURE_INCOMPLETE
        result["missing_sessions"] = ["INVALID_FORMAL_RULE_PARAMS"]
        return result

    entry_date: date | None = None
    entry_price: float | None = None
    path: list[Mapping[str, Any]] = []
    terminal = False
    for day in expected_sessions:
        bar = observations.get(day)
        if bar is None:
            result["capture_status"] = CAPTURE_INCOMPLETE
            result["missing_sessions"].append(day.isoformat())
            break
        high = _bar_value(bar, "high")
        low = _bar_value(bar, "low")
        if high is None or low is None:
            result["capture_status"] = CAPTURE_INCOMPLETE
            result["missing_sessions"].append(day.isoformat())
            break
        if entry_date is None:
            if high >= trigger:
                entry_date = day
                entry_price = trigger
                result["entry_date"] = day.isoformat()
                result["sellable_from"] = _next_session(day, cal).isoformat()
                result["entry_day_stop_touched"] = low <= stop
                result["entry_day_target_touched"] = high >= target
                path.append(bar)
            else:
                path.append(bar)
            continue

        path.append(bar)
        sellable_from = _parse_date(result["sellable_from"])
        if day < sellable_from:
            continue
        stop_hit = low <= stop
        target_hit = high >= target
        if stop_hit and target_hit:
            result["status"] = OUTCOME_AMBIGUOUS
            result["exit_date"] = day.isoformat()
            terminal = True
            break
        if stop_hit or target_hit:
            result["status"] = OUTCOME_STOP if stop_hit else OUTCOME_TARGET
            result["exit_date"] = day.isoformat()
            result["exit_price"] = stop if stop_hit else target
            result["holding_sessions"] = _session_index(entry_date, day, cal) + 1
            result["stop_session_index"] = _session_index(entry_date, day, cal) if stop_hit else None
            result["fast_stop"] = bool(stop_hit and result["stop_session_index"] in (1, 2))
            terminal = True
            break

    if entry_date is None:
        result["status"] = OUTCOME_UNTRIGGERED
    elif not terminal:
        result["status"] = OUTCOME_OPEN

    if entry_date is not None and result["status"] in {OUTCOME_TARGET, OUTCOME_STOP}:
        exit_price = _number(result.get("exit_price"))
        if exit_price is not None:
            result["realized_return_pct"] = _round((exit_price / entry_price - 1.0) * 100.0)
            result["realized_r"] = _round((exit_price - entry_price) / (entry_price - stop))
    if entry_date is not None and result["capture_status"] == CAPTURE_COMPLETE and path:
        highs = [_bar_value(bar, "high") for bar in path]
        lows = [_bar_value(bar, "low") for bar in path]
        if all(value is not None for value in highs + lows):
            result["mfe"] = _round(max((value / entry_price - 1.0) * 100.0 for value in highs if value is not None))
            result["mae"] = _round(min((value / entry_price - 1.0) * 100.0 for value in lows if value is not None))
            result["mfe_pct"] = result["mfe"]
            result["mae_pct"] = result["mae"]

    recovery_signal = {"entry_price": entry_price, "trigger": trigger, "target": target}
    _recovery_fields(result, signal=recovery_signal, observations=observations, as_of=as_of, calendar=cal)
    result["missing_sessions"] = sorted(set(result["missing_sessions"]))
    return result


def _capture_record(
    candidate: Mapping[str, Any],
    *,
    signal_date: str,
    market: Mapping[str, Any],
    reactivation: Mapping[str, Any],
    structural: Mapping[str, Any],
    volume_observation: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    signal_id = str(candidate.get("signal_id", ""))
    if not signal_id or candidate.get("strategy_version") != STRATEGY_VERSION:
        raise ShadowMonitorError("SHADOW_SIGNAL_IDENTITY_INVALID", f"invalid canonical candidate {signal_id!r}")
    pre_outcome = {
        "capture_mode": CAPTURE_PROSPECTIVE,
        "capture_status": CAPTURE_INCOMPLETE if market.get("feature_unavailable") or reactivation.get("feature_unavailable") or structural.get("feature_unavailable") else CAPTURE_COMPLETE,
        "signal_date": signal_date,
        "strategy_version": STRATEGY_VERSION,
        "market_regime": deepcopy(dict(market)),
        "reactivation": deepcopy(dict(reactivation)),
        "structural_context": deepcopy(dict(structural)),
        "volume_observation": deepcopy(dict(volume_observation)),
        "captured_at_bjt": source.get("captured_at_bjt"),
        "source": deepcopy(dict(source)),
    }
    return {
        "signal_id": signal_id,
        "signal_date": signal_date,
        "strategy_version": STRATEGY_VERSION,
        "code": candidate.get("code"),
        "name": candidate.get("name"),
        "formal_context": {
            "score": candidate.get("score"),
            "trigger": candidate.get("trigger"),
            "stop": candidate.get("stop"),
            "target": candidate.get("target"),
            "rr": candidate.get("rr"),
        },
        "pre_outcome": pre_outcome,
        "outcomes": _empty_outcome(),
    }


def _upsert_record(store: dict[str, Any], record: Mapping[str, Any]) -> str:
    signal_id = str(record["signal_id"])
    existing = store["signals"].get(signal_id)
    if existing is None:
        store["signals"][signal_id] = deepcopy(dict(record))
        return "ADDED"
    identity_fields = ("signal_date", "strategy_version", "code", "formal_context")
    if any(existing.get(field) != record.get(field) for field in identity_fields):
        raise ShadowMonitorError("SHADOW_PRE_OUTCOME_IDENTITY_CONFLICT", f"formal identity changed for {signal_id}")
    if _pre_outcome_semantic(existing["pre_outcome"]) != _pre_outcome_semantic(record["pre_outcome"]):
        raise ShadowMonitorError("SHADOW_PRE_OUTCOME_IDENTITY_CONFLICT", f"pre_outcome changed for {signal_id}")
    return "IDEMPOTENT"


def record_capture_failure(root: str | Path, *, signal_date: str, expected: int, detail: str) -> dict[str, Any]:
    store = load_store(root) or new_store()
    store["last_capture"] = {
        "signal_date": _date_text(signal_date),
        "expected": int(expected),
        "complete": 0,
        "incomplete": int(expected),
        "status": CAPTURE_INCOMPLETE,
        "detail": str(detail)[:2000],
        "captured_at_bjt": _now_bjt(),
    }
    store["updated_at_bjt"] = _now_bjt()
    save_store(store, root)
    return dict(store["last_capture"])


def capture_t_close_signals(
    *,
    watchlist_path: str | Path,
    run_manifest_path: str | Path | None,
    generation_input_manifest: Mapping[str, Any],
    market_env: Mapping[str, Any],
    input_package_sha256: str | None,
    store_root: str | Path,
    captured_at_bjt: datetime | str | None = None,
) -> dict[str, Any]:
    """Capture one real T-close canonical output and its pre-outcome context."""

    watchlist = load_watchlist(Path(watchlist_path))
    signal_date = _date_text(watchlist.get("date"))
    if watchlist.get("strategy_version") != STRATEGY_VERSION:
        raise ShadowMonitorError("SHADOW_SIGNAL_IDENTITY_INVALID", "watchlist is not frozen B V1_1")
    if generation_input_manifest.get("signal_date") != signal_date:
        raise ShadowMonitorError("SHADOW_INPUT_DATE_MISMATCH", "input package and watchlist dates differ")
    if generation_input_manifest.get("status") != "READY_FOR_STRATEGY_EVALUATION":
        raise ShadowMonitorError("SHADOW_INPUT_NOT_READY", "input package is not READY")

    store = load_store(store_root) or new_store()
    epoch = store["prospective_epoch"].get("start_date")
    if epoch is None:
        store["prospective_epoch"]["start_date"] = signal_date
    elif signal_date < epoch:
        raise ShadowMonitorError("SHADOW_RETROSPECTIVE_SIGNAL_REFUSED", f"{signal_date} precedes epoch {epoch}")

    watchlist_sha = _sha256_file(Path(watchlist_path))
    run_sha = _sha256_file(Path(run_manifest_path)) if run_manifest_path and Path(run_manifest_path).exists() else None
    source = {
        "capture_mode": CAPTURE_PROSPECTIVE,
        "source_type": "formal_t_close_generation_input_package",
        "watchlist_path": Path(watchlist_path).as_posix(),
        "watchlist_sha256": watchlist_sha,
        "run_manifest_path": Path(run_manifest_path).as_posix() if run_manifest_path else None,
        "run_manifest_sha256": run_sha,
        "input_package_sha256": input_package_sha256,
        "input_fingerprint": generation_input_manifest.get("input_fingerprint"),
        "captured_at_bjt": _now_bjt(captured_at_bjt),
    }
    index_manifest = generation_input_manifest.get("index")
    stock_klines = generation_input_manifest.get("stock_klines")
    if not isinstance(index_manifest, Mapping):
        raise ShadowMonitorError("SHADOW_FEATURE_UNAVAILABLE", "generation input index is missing")

    actions = {"added": 0, "idempotent": 0, "complete": 0, "incomplete": 0, "expected": len(watchlist["candidates"])}
    for candidate in watchlist["candidates"]:
        market = _market_snapshot(index_manifest, signal_date)
        reactivation, structural, volume_observation = _stock_snapshot(candidate, stock_klines, signal_date)
        record = _capture_record(
            candidate,
            signal_date=signal_date,
            market=market,
            reactivation=reactivation,
            structural=structural,
            volume_observation=volume_observation,
            source=source,
        )
        action = _upsert_record(store, record)
        actions["added" if action == "ADDED" else "idempotent"] += 1
        if record["pre_outcome"]["capture_status"] == CAPTURE_COMPLETE:
            actions["complete"] += 1
        else:
            actions["incomplete"] += 1
    actions["status"] = CAPTURE_INCOMPLETE if actions["incomplete"] else CAPTURE_COMPLETE
    store["last_capture"] = {
        "signal_date": signal_date,
        "expected": actions["expected"],
        "complete": actions["complete"],
        "incomplete": actions["incomplete"],
        "status": actions["status"],
        "captured_at_bjt": source["captured_at_bjt"],
    }
    store["updated_at_bjt"] = source["captured_at_bjt"]
    save_store(store, store_root)
    return {"monitor_version": MONITOR_VERSION, **actions, "path": str(_store_path(store_root))}


def _record_signal_for_evaluation(record: Mapping[str, Any]) -> dict[str, Any]:
    context = record.get("formal_context") if isinstance(record.get("formal_context"), Mapping) else {}
    return {
        "signal_date": record.get("signal_date"),
        "trigger": context.get("trigger"),
        "stop": context.get("stop"),
        "target": context.get("target"),
    }


def update_store_from_tracker(
    store: dict[str, Any],
    tracker: Mapping[str, Any],
    as_of_date: date | datetime | str,
    *,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Update mutable outcomes only; never rewrite any pre_outcome field."""

    _validate_store(store)
    cal = calendar or default_calendar()
    as_of = _parse_date(as_of_date)
    tracker_signals = tracker.get("signals", {}) if isinstance(tracker, Mapping) else {}
    if not isinstance(tracker_signals, Mapping):
        tracker_signals = {}
    changed = 0
    incomplete = 0
    for signal_id, record in store["signals"].items():
        signal_date = _parse_date(record["signal_date"])
        if signal_date > as_of or record["pre_outcome"].get("capture_mode") != CAPTURE_PROSPECTIVE:
            continue
        old = record.get("outcomes")
        tracker_signal = tracker_signals.get(signal_id)
        outcome = evaluate_shadow_outcome(
            _record_signal_for_evaluation(record),
            tracker_signal if isinstance(tracker_signal, Mapping) else None,
            as_of,
            calendar=cal,
        )
        if old != outcome:
            record["outcomes"] = outcome
            changed += 1
        if outcome.get("capture_status") == CAPTURE_INCOMPLETE:
            incomplete += 1
    store["updated_at_bjt"] = _now_bjt()
    return {"changed": changed, "incomplete": incomplete, "as_of_date": as_of.isoformat()}


def update_from_tracker(
    *,
    store_root: str | Path,
    tracker_path: str | Path,
    as_of_date: date | datetime | str,
) -> dict[str, Any]:
    store = load_store(store_root, missing_ok=False)
    if store is None:
        return {"status": "EMPTY", "changed": 0, "incomplete": 0}
    try:
        from track_perf import load_tracker

        tracker = load_tracker(tracker_path)
    except Exception as exc:
        record_capture_failure(store_root, signal_date=_date_text(as_of_date), expected=len(store["signals"]), detail=f"tracker: {type(exc).__name__}: {exc}")
        return {"status": CAPTURE_INCOMPLETE, "changed": 0, "incomplete": len(store["signals"]), "detail": str(exc)[:1000]}
    result = update_store_from_tracker(store, tracker, as_of_date)
    result["status"] = CAPTURE_INCOMPLETE if result["incomplete"] else CAPTURE_COMPLETE
    save_store(store, store_root)
    return result


def _aggregate(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    outcomes = [record.get("outcomes", {}) for record in records]
    resolved = [row for row in outcomes if row.get("status") in {OUTCOME_TARGET, OUTCOME_STOP}]
    returns = [_number(row.get("realized_return_pct")) for row in resolved]
    returns = [value for value in returns if value is not None]
    r_values = [_number(row.get("realized_r")) for row in resolved]
    r_values = [value for value in r_values if value is not None]
    wins = [value for row in resolved if row.get("status") == OUTCOME_TARGET for value in [_number(row.get("realized_return_pct"))] if value is not None]
    losses = [value for row in resolved if row.get("status") == OUTCOME_STOP for value in [_number(row.get("realized_return_pct"))] if value is not None]
    stop_count = sum(row.get("status") == OUTCOME_STOP for row in outcomes)
    fast_count = sum(row.get("status") == OUTCOME_STOP and row.get("fast_stop") is True for row in outcomes)
    positive = sum(value for value in wins if value > 0)
    negative = sum(value for value in losses if value < 0)
    return {
        "n": len(records),
        "signals": len(records),
        "eligible": sum(bool(row.get("eligible")) for row in outcomes),
        "triggered": sum(row.get("status") in {OUTCOME_TARGET, OUTCOME_STOP, OUTCOME_OPEN, OUTCOME_AMBIGUOUS} for row in outcomes),
        "resolved": len(resolved),
        "target": sum(row.get("status") == OUTCOME_TARGET for row in outcomes),
        "stop": stop_count,
        "open": sum(row.get("status") == OUTCOME_OPEN for row in outcomes),
        "untriggered": sum(row.get("status") == OUTCOME_UNTRIGGERED for row in outcomes),
        "ambiguous": sum(row.get("status") == OUTCOME_AMBIGUOUS for row in outcomes),
        "fast_stop_count": fast_count,
        "fast_stop_rate": _round(fast_count / stop_count * 100.0) if stop_count else None,
        "win_rate": _round(sum(row.get("status") == OUTCOME_TARGET for row in outcomes) / len(resolved) * 100.0) if resolved else None,
        "profit_factor": _round(positive / abs(negative)) if negative < 0 else None,
        "pf": _round(positive / abs(negative)) if negative < 0 else None,
        "expectancy": _round(statistics.fmean(returns)) if returns else None,
        "expectancy_pct": _round(statistics.fmean(returns)) if returns else None,
        "avg_r": _round(statistics.fmean(r_values)) if r_values else None,
    }


def _median(values: list[float]) -> float | None:
    return _round(statistics.median(values)) if values else None


def build_shadow_summary(
    store: Mapping[str, Any],
    as_of_date: date | datetime | str,
    *,
    calendar: TradingCalendar | None = None,
    current_signal_ids: set[str] | None = None,
) -> dict[str, Any]:
    _validate_store(dict(store))
    as_of = _parse_date(as_of_date)
    records = [
        record for record in store["signals"].values()
        if isinstance(record, Mapping)
        and record.get("pre_outcome", {}).get("capture_mode") == CAPTURE_PROSPECTIVE
        and _parse_date(record.get("signal_date")) <= as_of
    ]
    # Do not let a report for an earlier date consume a later mutable outcome.
    visible: list[dict[str, Any]] = []
    for raw in records:
        record = deepcopy(dict(raw))
        updated = record.get("outcomes", {}).get("updated_as_of")
        if updated and _parse_date(updated) > as_of:
            record["outcomes"] = _empty_outcome()
        visible.append(record)
    overall = _aggregate(visible)
    by_trend: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_vol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in visible:
        market = record.get("pre_outcome", {}).get("market_regime", {})
        if market.get("trend_regime"):
            by_trend[str(market["trend_regime"])].append(record)
        if market.get("vol_regime"):
            by_vol[str(market["vol_regime"])].append(record)
    trend_rows = [{"environment": label, **_aggregate(rows)} for label, rows in sorted(by_trend.items())]
    vol_rows = [{"environment": label, **_aggregate(rows)} for label, rows in sorted(by_vol.items())]
    reactivation_groups: dict[str, list[float]] = defaultdict(list)
    for record in visible:
        status = str(record.get("outcomes", {}).get("status", OUTCOME_UNTRIGGERED))
        value = _number(record.get("pre_outcome", {}).get("reactivation", {}).get("reactivation_vs_breakout_ratio"))
        if value is not None:
            reactivation_groups[status].append(value)
    reactivation_rows = [
        {
            "bucket": status,
            "sample": len(values),
            "median_reactivation_vs_breakout_ratio": _median(values),
        }
        for status, values in sorted(reactivation_groups.items())
    ]
    current_ids = current_signal_ids or set()
    current_records = [record for record in visible if record.get("signal_id") in current_ids]
    regimes = sorted({
        f"{record.get('pre_outcome', {}).get('market_regime', {}).get('trend_regime')} / {record.get('pre_outcome', {}).get('market_regime', {}).get('vol_regime')}"
        for record in current_records
        if record.get("pre_outcome", {}).get("market_regime", {}).get("trend_regime")
        and record.get("pre_outcome", {}).get("market_regime", {}).get("vol_regime")
    })
    return {
        "status": store.get("status", STATUS_EVIDENCE_ACCUMULATING),
        "epoch_start": store.get("prospective_epoch", {}).get("start_date"),
        "as_of_date": as_of.isoformat(),
        "overall": overall,
        "trend_rows": trend_rows,
        "vol_rows": vol_rows,
        "reactivation_rows": reactivation_rows,
        "reactivation_mode": "CONTINUOUS_MEDIAN_NO_FROZEN_BINS",
        "current_regime": ", ".join(regimes) if regimes else "—",
        "current_signal_context": {
            record["signal_id"]: {
                "market": f"{record.get('pre_outcome', {}).get('market_regime', {}).get('trend_regime') or '—'} / {record.get('pre_outcome', {}).get('market_regime', {}).get('vol_regime') or '—'}",
                "reactivation_vs_breakout_ratio": record.get("pre_outcome", {}).get("reactivation", {}).get("reactivation_vs_breakout_ratio"),
                "volume_observation": deepcopy(
                    dict(record.get("pre_outcome", {}).get("volume_observation", {}))
                ) if isinstance(record.get("pre_outcome", {}).get("volume_observation"), Mapping) else {},
                "capture_status": record.get("pre_outcome", {}).get("capture_status"),
            }
            for record in current_records
        },
        "reference_only": deepcopy(dict(store.get("reference_only", {}))),
        "definition_version": REGIME_DEFINITION_VERSION,
    }


def build_report_view(
    store: Mapping[str, Any] | None,
    report_date: date | datetime | str,
    *,
    watchlist: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if store is None:
        return {
            "status": STATUS_EVIDENCE_ACCUMULATING,
            "epoch_start": None,
            "as_of_date": _date_text(report_date),
            "empty": True,
            "overall": _aggregate([]),
            "trend_rows": [],
            "vol_rows": [],
            "reactivation_rows": [],
            "reactivation_mode": "CONTINUOUS_MEDIAN_NO_FROZEN_BINS",
            "current_regime": "—",
            "current_signal_context": {},
            "reference_only": _reference_only(),
            "capture": {"expected": 0, "complete": 0, "incomplete": 0, "status": "EMPTY"},
        }
    current_ids = {
        str(candidate.get("signal_id"))
        for candidate in (watchlist.get("candidates", []) if isinstance(watchlist, Mapping) else [])
        if isinstance(candidate, Mapping)
    }
    summary = build_shadow_summary(store, report_date, current_signal_ids=current_ids)
    expected = len(current_ids)
    matching = [record for record in store["signals"].values() if record.get("signal_id") in current_ids]
    complete = sum(record.get("pre_outcome", {}).get("capture_status") == CAPTURE_COMPLETE for record in matching)
    incomplete = max(expected - complete, 0) + sum(record.get("pre_outcome", {}).get("capture_status") == CAPTURE_INCOMPLETE for record in matching)
    last_capture = store.get("last_capture") if isinstance(store.get("last_capture"), Mapping) else {}
    if last_capture.get("signal_date") == _date_text(report_date) and last_capture.get("status") == CAPTURE_INCOMPLETE:
        incomplete = max(incomplete, int(last_capture.get("incomplete", 0) or 0))
    summary["capture"] = {
        "expected": expected,
        "complete": complete,
        "incomplete": incomplete,
        "status": CAPTURE_INCOMPLETE if incomplete else (CAPTURE_COMPLETE if expected else "EMPTY"),
    }
    summary["empty"] = not bool(summary["overall"]["signals"])
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["update"], nargs="?", default="update")
    parser.add_argument("--date", required=True)
    parser.add_argument("--data-root", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = (args.data_root or DataPaths.from_env().root).expanduser().resolve()
    try:
        result = update_from_tracker(
            store_root=data_root / "shadow_monitor",
            tracker_path=data_root / "perf_tracker.json",
            as_of_date=args.date,
        )
    except (OSError, ValueError, ShadowMonitorError) as exc:
        print(json.dumps({"status": CAPTURE_INCOMPLETE, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
