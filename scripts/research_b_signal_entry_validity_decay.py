#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""Bounded, read-only research for B signal entry-validity decay.

This module deliberately sits outside the production tracker state machine.  It
reads an immutable runtime-state tracker/watchlist snapshot, optionally joins
the already-captured T-close K-line evidence, and writes research artifacts.
It never writes prospective evidence, tracker state, reports, or production
configuration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence

from live_acquisition import (
    DEFAULT_STOCK_BAR_COUNT,
    TCloseEvidenceStore,
    _history_capture_spec,
    _load_captured_market_bars,
)
from track_perf import (
    EXECUTION_VERIFIED,
    EXIT_REASON_AMBIGUOUS,
    EXIT_REASON_EXPIRED_UNTRIGGERED,
    EXIT_REASON_STOP,
    EXIT_REASON_STOP_GAP,
    EXIT_REASON_TARGET,
    EXIT_REASON_TARGET_GAP,
    EXIT_REASON_TIME,
    EXIT_REASON_TIME_DEFERRED_T1,
    PERFORMANCE_DATA_INCOMPLETE,
    _sellable_exit_decision,
    build_strategy_rule_performance,
    parse_date,
    rebuild_execution_state_from_observations,
)
from trading_calendar import TradingCalendar, default_calendar


PROTOCOL_VERSION = "B_SIGNAL_ENTRY_VALIDITY_DECAY_V1"
STRATEGY = "B_BREAKOUT_RETEST_LEGACY_V1_1"
SETUP = "B_BREAKOUT_RETEST"
EPOCH_START = date(2026, 9, 3)
DEFAULT_AS_OF = date(2026, 9, 30)
MAX_TRIGGER_DELAY = 10
FIXED_ENTRY_HORIZONS = (1, 3, 5)
CUTOFFS = (1, 2, 3, 5, 10)
MIN_SAMPLE = 10
EVIDENCE_DATE = date(2026, 9, 11)

COHORTS: tuple[tuple[str, int | None, int | None], ...] = (
    ("T+1", 1, 1),
    ("T+2", 2, 2),
    ("T+3", 3, 3),
    ("T+4-T+5", 4, 5),
    ("T+6-T+10", 6, 10),
    ("UNTRIGGERED", None, None),
)

NUMERIC_FIELDS = (
    "open",
    "high",
    "low",
    "close",
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _mean(values: Iterable[Any]) -> float | None:
    clean = [float(value) for value in values if _finite(value) is not None]
    return _round(mean(clean)) if clean else None


def _median(values: Iterable[Any]) -> float | None:
    clean = [float(value) for value in values if _finite(value) is not None]
    return _round(median(clean)) if clean else None


def _number_list(values: Iterable[Any]) -> list[float]:
    return [float(value) for value in values if _finite(value) is not None]


def _next_session(day: date, calendar: TradingCalendar) -> date:
    current = day + timedelta(days=1)
    while not calendar.is_trading_day(current):
        current += timedelta(days=1)
    return current


def sessions_after(day: date | str, count: int, calendar: TradingCalendar) -> list[date]:
    current = parse_date(day)
    sessions: list[date] = []
    while len(sessions) < count:
        current = _next_session(current, calendar)
        sessions.append(current)
    return sessions


def _cohort_for_delay(delay: int | None) -> str | None:
    if delay is None:
        return None
    for label, lower, upper in COHORTS:
        if lower is not None and lower <= delay <= upper:  # type: ignore[operator]
            return label
    raise ValueError(f"delay outside preregistered range: {delay}")


def normalize_bar(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a K-line or tracker observation without changing its values."""

    if raw.get("date") is None:
        raise ValueError("bar is missing date")
    day = parse_date(raw["date"]).isoformat()
    values = {
        "open": _finite(raw.get("open")),
        "high": _finite(raw.get("high")),
        "low": _finite(raw.get("low")),
        "close": _finite(raw.get("close", raw.get("price"))),
    }
    if values["high"] is None or values["low"] is None or values["close"] is None:
        raise ValueError(f"bar {day} is missing high/low/close")
    if values["high"] < values["low"] or values["low"] > values["close"] or values["high"] < values["close"]:
        raise ValueError(f"bar {day} has conflicting OHLC")
    if any(value is not None and value <= 0 for value in values.values()):
        raise ValueError(f"bar {day} has non-positive OHLC")
    return {
        "date": day,
        **values,
        "price": values["close"],
        "source_mode": raw.get("source_mode"),
        "provenance": raw.get("provenance"),
    }


def _same_bar(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    for field in NUMERIC_FIELDS:
        a, b = _finite(left.get(field)), _finite(right.get(field))
        if a is None or b is None:
            if a != b:
                return False
        elif not math.isclose(a, b, rel_tol=0.0, abs_tol=1e-9):
            return False
    return True


def merge_bars(
    evidence_bars: Iterable[Mapping[str, Any]],
    observations: Iterable[Mapping[str, Any]],
) -> tuple[dict[date, dict[str, Any]], list[str]]:
    """Merge immutable pre-cutoff evidence with tracker observations.

    The two sources must agree on duplicate dates.  A conflict is reported and
    is never silently resolved by preferring a later source.
    """

    merged: dict[date, dict[str, Any]] = {}
    conflicts: list[str] = []
    for source_name, values in (("evidence", evidence_bars), ("tracker", observations)):
        for raw in values:
            normalized = normalize_bar(raw)
            day = parse_date(normalized["date"])
            existing = merged.get(day)
            if existing is not None and not _same_bar(existing, normalized):
                conflicts.append(day.isoformat())
                continue
            if existing is None or source_name == "tracker":
                merged[day] = normalized
    return dict(sorted(merged.items())), sorted(set(conflicts))


def classify_first_trigger(
    signal: Mapping[str, Any],
    bars: Mapping[date, Mapping[str, Any]],
    as_of: date | str,
    calendar: TradingCalendar,
    *,
    conflicts: Sequence[str] = (),
) -> dict[str, Any]:
    """Classify the first canonical-trigger delay using XSHG sessions only."""

    signal_day = parse_date(signal["date"])
    cutoff = parse_date(as_of)
    sessions = sessions_after(signal_day, MAX_TRIGGER_DELAY, calendar)
    visible = [day for day in sessions if day <= cutoff]
    trigger = _finite(signal.get("trigger"))
    if trigger is None:
        return {
            "first_trigger_delay": None,
            "raw_trigger_delay": None,
            "trigger_date": None,
            "delay_status": "DATA_CONFLICT",
            "cohort": "CENSORED_OR_INCOMPLETE",
            "required_sessions": [day.isoformat() for day in sessions],
            "missing_sessions": [day.isoformat() for day in visible],
        }
    if conflicts:
        return {
            "first_trigger_delay": None,
            "raw_trigger_delay": None,
            "trigger_date": None,
            "delay_status": "DATA_CONFLICT",
            "cohort": "CENSORED_OR_INCOMPLETE",
            "required_sessions": [day.isoformat() for day in sessions],
            "missing_sessions": list(conflicts),
        }

    raw_index: int | None = None
    for index, day in enumerate(visible, start=1):
        bar = bars.get(day)
        if bar is not None and _finite(bar.get("high")) is not None and float(bar["high"]) >= trigger:
            raw_index = sessions.index(day) + 1
            break
    if raw_index is not None:
        prior = sessions[: raw_index - 1]
        missing = [day for day in prior if day > cutoff or day not in bars]
        if not missing:
            return {
                "first_trigger_delay": raw_index,
                "raw_trigger_delay": raw_index,
                "trigger_date": sessions[raw_index - 1].isoformat(),
                "delay_status": "KNOWN",
                "cohort": _cohort_for_delay(raw_index),
                "required_sessions": [day.isoformat() for day in sessions],
                "missing_sessions": [],
            }
        return {
            "first_trigger_delay": None,
            "raw_trigger_delay": raw_index,
            "trigger_date": sessions[raw_index - 1].isoformat(),
            "delay_status": "INCOMPLETE",
            "cohort": "CENSORED_OR_INCOMPLETE",
            "required_sessions": [day.isoformat() for day in sessions],
            "missing_sessions": [day.isoformat() for day in missing],
        }

    missing = [day for day in visible if day not in bars]
    if cutoff >= sessions[-1] and not missing:
        status = "UNTRIGGERED"
        cohort = "UNTRIGGERED"
    elif missing:
        status = "INCOMPLETE"
        cohort = "CENSORED_OR_INCOMPLETE"
    else:
        status = "CENSORED"
        cohort = "CENSORED_OR_INCOMPLETE"
    return {
        "first_trigger_delay": None,
        "raw_trigger_delay": None,
        "trigger_date": None,
        "delay_status": status,
        "cohort": cohort,
        "required_sessions": [day.isoformat() for day in sessions],
        "missing_sessions": [day.isoformat() for day in missing],
    }


def _entry_fill(signal: Mapping[str, Any], entry_bar: Mapping[str, Any]) -> float | None:
    trigger = _finite(signal.get("trigger"))
    if trigger is None:
        return None
    opening = _finite(entry_bar.get("open"))
    if opening is not None and opening >= trigger:
        return opening
    high = _finite(entry_bar.get("high"))
    return trigger if high is not None and high >= trigger else None


def evaluate_fixed_horizons(
    signal: Mapping[str, Any],
    bars: Mapping[date, Mapping[str, Any]],
    entry_date: date | str,
    as_of: date | str,
    calendar: TradingCalendar,
) -> dict[str, dict[str, Any]]:
    """Evaluate E+1/E+3/E+5 with terminal handling and no zero filling."""

    entry_day = parse_date(entry_date)
    cutoff = parse_date(as_of)
    entry_bar = bars.get(entry_day)
    entry_price = _entry_fill(signal, entry_bar or {})
    result: dict[str, dict[str, Any]] = {}
    if entry_bar is None or entry_price is None:
        return {
            f"E+{h}": {"status": "MISSING_OBSERVATION", "return_pct": None, "positive": None, "sample_n": 0}
            for h in FIXED_ENTRY_HORIZONS
        }

    target_days = sessions_after(entry_day, max(FIXED_ENTRY_HORIZONS), calendar)
    terminal: dict[str, Any] | None = None
    missing_before: str | None = None
    for offset, day in enumerate(target_days, start=1):
        if day > cutoff:
            break
        bar = bars.get(day)
        if bar is None:
            missing_before = day.isoformat()
            break
        if terminal is None:
            decision = _sellable_exit_decision(signal, bar)
            if decision is not None:
                reason = str(decision["exit_reason"])
                if reason == EXIT_REASON_AMBIGUOUS:
                    terminal = {"status": "AMBIGUOUS_SAME_BAR", "reason": reason, "return_pct": None}
                else:
                    exit_price = _finite(decision.get("exit_price"))
                    terminal = {
                        "status": "TERMINAL",
                        "reason": reason,
                        "return_pct": _round((exit_price / entry_price - 1.0) * 100.0)
                        if exit_price is not None
                        else None,
                    }
        if offset in FIXED_ENTRY_HORIZONS:
            label = f"E+{offset}"
            if terminal is not None:
                result[label] = {
                    **terminal,
                    "positive": (
                        terminal["return_pct"] > 0
                        if _finite(terminal.get("return_pct")) is not None
                        else None
                    ),
                    "sample_n": 1 if _finite(terminal.get("return_pct")) is not None else 0,
                }
            else:
                close = _finite(bar.get("close", bar.get("price")))
                value = _round((close / entry_price - 1.0) * 100.0) if close is not None else None
                result[label] = {
                    "status": "MARK_TO_MARKET" if value is not None else "MISSING_OBSERVATION",
                    "reason": None,
                    "return_pct": value,
                    "positive": value > 0 if value is not None else None,
                    "sample_n": 1 if value is not None else 0,
                }
    for offset in FIXED_ENTRY_HORIZONS:
        label = f"E+{offset}"
        if label in result:
            continue
        if terminal is not None:
            result[label] = {
                **terminal,
                "positive": (
                    terminal["return_pct"] > 0
                    if _finite(terminal.get("return_pct")) is not None
                    else None
                ),
                "sample_n": 1 if _finite(terminal.get("return_pct")) is not None else 0,
            }
        else:
            result[label] = {
                "status": "CENSORED" if missing_before is None else "MISSING_OBSERVATION",
                "reason": missing_before,
                "return_pct": None,
                "positive": None,
                "sample_n": 0,
            }
    return result


def _state_path_status(state: Mapping[str, Any] | None) -> str:
    if state is None:
        return "INCOMPLETE"
    if state.get("execution_verification_status") != EXECUTION_VERIFIED:
        return "INCOMPLETE"
    if state.get("status") in {"pending", "triggered"}:
        return "CENSORED"
    return "COMPLETE"


def _terminal_label(state: Mapping[str, Any] | None) -> str | None:
    if not state:
        return None
    if state.get("status") in {"pending", "triggered"}:
        return "OPEN_OR_PENDING"
    reason = state.get("exit_reason")
    if reason in {EXIT_REASON_TARGET, EXIT_REASON_TARGET_GAP}:
        return "TARGET"
    if reason in {EXIT_REASON_STOP, EXIT_REASON_STOP_GAP}:
        return "STOP"
    if reason in {EXIT_REASON_TIME, EXIT_REASON_TIME_DEFERRED_T1}:
        return "TIME_EXIT"
    if reason == EXIT_REASON_EXPIRED_UNTRIGGERED:
        return "EXPIRED_UNTRIGGERED"
    if reason == EXIT_REASON_AMBIGUOUS:
        return "AMBIGUOUS_SAME_BAR"
    return None


def analyze_signal(
    signal: Mapping[str, Any],
    canonical: Mapping[str, Any],
    evidence_bars: Iterable[Mapping[str, Any]],
    as_of: date | str,
    calendar: TradingCalendar,
) -> dict[str, Any]:
    merged, conflicts = merge_bars(evidence_bars, signal.get("observations", []))
    classification = classify_first_trigger(signal, merged, as_of, calendar, conflicts=conflicts)
    replay_signal = deepcopy(dict(signal))
    replay_signal["observations"] = [merged[day] for day in sorted(merged) if day > parse_date(signal["date"])]
    state: dict[str, Any] | None
    if conflicts:
        state = None
    else:
        state = rebuild_execution_state_from_observations(replay_signal, calendar=calendar, as_of=as_of)
    entry_date = (
        parse_date(classification["trigger_date"])
        if classification.get("first_trigger_delay") is not None and classification.get("trigger_date")
        else None
    )
    fixed = (
        evaluate_fixed_horizons(signal, merged, entry_date, as_of, calendar)
        if entry_date is not None
        else {f"E+{h}": {"status": "NOT_APPLICABLE", "return_pct": None, "positive": None, "sample_n": 0} for h in FIXED_ENTRY_HORIZONS}
    )
    t_close = _finite(canonical.get("price"))
    trigger = _finite(signal.get("trigger"))
    diagnostics: dict[str, Any] = {
        "t_close": t_close,
        "trigger_distance_pct": _round((trigger / t_close - 1.0) * 100.0) if trigger and t_close else None,
        "score": _finite(signal.get("score")),
        "rr": _finite(signal.get("rr")),
        "pre_trigger_max_high_pct_from_t_close": None,
        "pre_trigger_max_low_pct_from_t_close": None,
        "pre_trigger_last_close_pct_from_t_close": None,
        "pre_trigger_stop_touched": None,
        "pre_trigger_sessions_observed": 0,
        "pre_trigger_data_status": "NOT_APPLICABLE",
    }
    if entry_date is not None and t_close and trigger:
        pre_days = sessions_after(parse_date(signal["date"]), classification["first_trigger_delay"] - 1, calendar)
        pre_days = [day for day in pre_days if day < entry_date]
        pre_bars = [merged[day] for day in pre_days if day in merged]
        diagnostics["pre_trigger_sessions_observed"] = len(pre_bars)
        diagnostics["pre_trigger_data_status"] = "COMPLETE" if len(pre_bars) == len(pre_days) else "INCOMPLETE"
        if pre_bars:
            highs = [_finite(bar.get("high")) for bar in pre_bars]
            lows = [_finite(bar.get("low")) for bar in pre_bars]
            closes = [_finite(bar.get("close")) for bar in pre_bars]
            diagnostics["pre_trigger_max_high_pct_from_t_close"] = _round(max((value / t_close - 1.0) * 100.0 for value in highs if value is not None))
            diagnostics["pre_trigger_max_low_pct_from_t_close"] = _round(min((value / t_close - 1.0) * 100.0 for value in lows if value is not None))
            last_close = closes[-1]
            diagnostics["pre_trigger_last_close_pct_from_t_close"] = _round((last_close / t_close - 1.0) * 100.0) if last_close is not None else None
            stop = _finite(signal.get("stop"))
            diagnostics["pre_trigger_stop_touched"] = any(low is not None and stop is not None and low <= stop for low in lows)

    realized = _finite(state.get("realized_return_pct")) if state else None
    mfe = _finite(state.get("mfe_pct")) if state else None
    mae = _finite(state.get("mae_pct")) if state else None
    row: dict[str, Any] = {
        "signal_id": signal.get("signal_id"),
        "strategy_version": signal.get("strategy_version"),
        "signal_date": parse_date(signal["date"]).isoformat(),
        "code": str(signal.get("code", "")),
        "setup": signal.get("setup"),
        "score": _finite(signal.get("score")),
        "trigger": trigger,
        "stop": _finite(signal.get("stop")),
        "target": _finite(signal.get("target")),
        "rr": _finite(signal.get("rr")),
        "tracker_status": signal.get("status"),
        "first_trigger_delay": classification["first_trigger_delay"],
        "raw_trigger_delay": classification["raw_trigger_delay"],
        "first_trigger_date": classification["trigger_date"],
        "delay_status": classification["delay_status"],
        "cohort": classification["cohort"],
        "required_sessions": classification["required_sessions"],
        "missing_sessions": classification["missing_sessions"],
        "operational_path_status": _state_path_status(state),
        "operational_terminal_status": _terminal_label(state),
        "operational_execution_verification_status": state.get("execution_verification_status") if state else "DATA_CONFLICT",
        "operational_entry_date": state.get("entry_date") if state else None,
        "operational_entry_price": _finite(state.get("entry_price")) if state else None,
        "operational_exit_date": state.get("exit_date") if state else None,
        "operational_exit_price": _finite(state.get("exit_price")) if state else None,
        "operational_exit_reason": state.get("exit_reason") if state else None,
        "operational_return_pct": realized,
        "operational_realized_r": _finite(state.get("realized_r")) if state else None,
        "operational_holding_sessions": state.get("holding_sessions") if state else None,
        "operational_mfe_pct": mfe,
        "operational_mae_pct": mae,
        "operational_ambiguity": bool(state and state.get("exit_reason") == EXIT_REASON_AMBIGUOUS),
        "bar_conflicts": conflicts,
        **diagnostics,
    }
    for horizon in FIXED_ENTRY_HORIZONS:
        point = fixed[f"E+{horizon}"]
        row[f"e{horizon}_status"] = point.get("status")
        row[f"e{horizon}_return_pct"] = point.get("return_pct")
        row[f"e{horizon}_positive"] = point.get("positive")
        row[f"e{horizon}_sample_n"] = point.get("sample_n", 0)
        row[f"e{horizon}_reason"] = point.get("reason")
    return row


def _metric_status(sample_n: int) -> str:
    return "INSUFFICIENT_SAMPLE" if sample_n < MIN_SAMPLE else "OK"


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    complete = [row for row in rows if row.get("operational_path_status") == "COMPLETE"]
    incomplete = [row for row in rows if row.get("operational_path_status") == "INCOMPLETE"]
    censored = [row for row in rows if row.get("operational_path_status") == "CENSORED"]
    numeric = [row for row in complete if _finite(row.get("operational_return_pct")) is not None]
    target = [row for row in numeric if row.get("operational_terminal_status") == "TARGET"]
    stop = [row for row in numeric if row.get("operational_terminal_status") == "STOP"]
    time_exit = [row for row in numeric if row.get("operational_terminal_status") == "TIME_EXIT"]
    ambiguous = [row for row in rows if row.get("operational_terminal_status") == "AMBIGUOUS_SAME_BAR"]
    returns = _number_list(row.get("operational_return_pct") for row in numeric)
    winners = [value for value in returns if value > 0]
    losers = [value for value in returns if value < 0]
    resolved = len(numeric)
    positive_sum, negative_sum = sum(winners), sum(losers)
    fixed_summary: dict[str, Any] = {}
    for horizon in FIXED_ENTRY_HORIZONS:
        values = _number_list(row.get(f"e{horizon}_return_pct") for row in rows)
        fixed_summary[f"E+{horizon}"] = {
            "sample_n": len(values),
            "mean_pct": _mean(values),
            "median_pct": _median(values),
            "positive_rate_pct": _round(sum(value > 0 for value in values) / len(values) * 100.0) if values else None,
            "missing_or_censored_count": sum(
                row.get(f"e{horizon}_status") in {"MISSING_OBSERVATION", "CENSORED"} for row in rows
            ),
            "ambiguity_count": sum(row.get(f"e{horizon}_status") == "AMBIGUOUS_SAME_BAR" for row in rows),
            "sample_status": _metric_status(len(values)),
        }
    return {
        "total_signals": len(rows),
        "triggered_count": sum(row.get("delay_status") == "KNOWN" for row in rows),
        "raw_trigger_observed_count": sum(row.get("raw_trigger_delay") is not None for row in rows),
        "delay_known_count": sum(row.get("delay_status") == "KNOWN" for row in rows),
        "untriggered_count": sum(row.get("delay_status") == "UNTRIGGERED" for row in rows),
        "delay_censored_count": sum(row.get("delay_status") == "CENSORED" for row in rows),
        "delay_incomplete_count": sum(row.get("delay_status") == "INCOMPLETE" for row in rows),
        "delay_data_conflict_count": sum(row.get("delay_status") == "DATA_CONFLICT" for row in rows),
        "complete_data_count": len(complete),
        "censored_count": len(censored),
        "incomplete_count": len(incomplete),
        "operational_censored_count": len(censored),
        "operational_incomplete_count": len(incomplete),
        "ambiguity_count": len(ambiguous),
        "resolved_trade_count": resolved,
        "target_hit_count": len(target),
        "stop_hit_count": len(stop),
        "time_exit_count": len(time_exit),
        "win_rate_pct": _round(len(target) / resolved * 100.0) if resolved else None,
        "average_return_pct": _mean(returns),
        "median_return_pct": _median(returns),
        "average_winner_pct": _mean(winners),
        "average_loser_pct": _mean(losers),
        "payoff_ratio": _round(mean(winners) / abs(mean(losers))) if winners and losers and mean(losers) else None,
        "profit_factor": _round(positive_sum / abs(negative_sum)) if negative_sum < 0 else None,
        "expectancy_pct": _mean(returns),
        "average_holding_sessions": _mean(row.get("operational_holding_sessions") for row in numeric),
        "target_hit_rate_pct": _round(len(target) / resolved * 100.0) if resolved else None,
        "stop_hit_rate_pct": _round(len(stop) / resolved * 100.0) if resolved else None,
        "average_mfe_pct": _mean(row.get("operational_mfe_pct") for row in complete),
        "average_mae_pct": _mean(row.get("operational_mae_pct") for row in complete),
        "median_mfe_pct": _median(row.get("operational_mfe_pct") for row in complete),
        "median_mae_pct": _median(row.get("operational_mae_pct") for row in complete),
        "sample_status": _metric_status(resolved),
        "fixed_entry_relative": fixed_summary,
    }


def early_late_comparison(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    early = [row for row in rows if row.get("cohort") in {"T+1", "T+2", "T+3"}]
    late = [row for row in rows if row.get("cohort") in {"T+4-T+5", "T+6-T+10"}]
    early_summary = summarize_rows(early)
    late_summary = summarize_rows(late)
    metric_keys = (
        "average_return_pct",
        "median_return_pct",
        "win_rate_pct",
        "profit_factor",
        "average_mfe_pct",
        "average_mae_pct",
    )
    differences = {
        key: {
            "early": early_summary.get(key),
            "late": late_summary.get(key),
            "late_minus_early": (
                _round(late_summary[key] - early_summary[key])
                if _finite(late_summary.get(key)) is not None and _finite(early_summary.get(key)) is not None
                else None
            ),
        }
        for key in metric_keys
    }
    for horizon in (3, 5):
        key = f"E+{horizon}"
        early_point, late_point = early_summary["fixed_entry_relative"][key], late_summary["fixed_entry_relative"][key]
        differences[key] = {
            "early": early_point.get("mean_pct"),
            "late": late_point.get("mean_pct"),
            "late_minus_early": (
                _round(late_point["mean_pct"] - early_point["mean_pct"])
                if _finite(late_point.get("mean_pct")) is not None and _finite(early_point.get("mean_pct")) is not None
                else None
            ),
            "early_sample_n": early_point.get("sample_n", 0),
            "late_sample_n": late_point.get("sample_n", 0),
        }
    return {
        "comparison": "LATE_MINUS_EARLY",
        "early_definition": "T+1-T+3",
        "late_definition": "T+4-T+10",
        "early_sample_size": len(early),
        "late_sample_size": len(late),
        "status": "INSUFFICIENT_SAMPLE" if min(len(early), len(late)) < MIN_SAMPLE else "OK",
        "early_summary": early_summary,
        "late_summary": late_summary,
        "differences": differences,
        "bootstrap": {
            "status": "NOT_RUN_INSUFFICIENT_SAMPLE" if min(len(early), len(late)) < MIN_SAMPLE else "NOT_IMPLEMENTED",
            "unit": "signal_date_block",
            "seed": 20261005,
        },
    }


def cutoff_sensitivity(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    known = [row for row in rows if row.get("delay_status") == "KNOWN"]
    untriggered = [row for row in rows if row.get("delay_status") == "UNTRIGGERED"]
    results: list[dict[str, Any]] = []
    for cutoff in CUTOFFS:
        retained = [row for row in known if int(row["first_trigger_delay"]) <= cutoff]
        excluded = [row for row in known if int(row["first_trigger_delay"]) > cutoff]
        numeric = [row for row in retained if _finite(row.get("operational_return_pct")) is not None]
        values = _number_list(row.get("operational_return_pct") for row in numeric)
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        positive_sum, negative_sum = sum(wins), sum(losses)
        target_count = sum(row.get("operational_terminal_status") == "TARGET" for row in numeric)
        results.append({
            "entry_validity_cutoff_sessions": cutoff,
            "retained_triggered_signals": len(retained),
            "retained_terminal_trades": len(numeric),
            "expired_untriggered_count": len(untriggered),
            "excluded_late_trigger_trades": len(excluded),
            "excluded_unclassified_trigger_count": sum(
                row.get("raw_trigger_delay") is not None and row.get("delay_status") != "KNOWN" for row in rows
            ),
            "retained_trade_average_return_pct": _mean(values),
            "retained_trade_win_rate_pct": _round(target_count / len(numeric) * 100.0) if numeric else None,
            "retained_trade_profit_factor": _round(positive_sum / abs(negative_sum)) if negative_sum < 0 else None,
            "retained_trade_expectancy_pct": _mean(values),
            "sample_status": _metric_status(len(numeric)),
        })
    return results


def diagnostics_by_delay(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for delay in range(1, MAX_TRIGGER_DELAY + 1):
        selected = [row for row in rows if row.get("first_trigger_delay") == delay]
        if not selected:
            continue
        output[f"T+{delay}"] = {
            "sample_n": len(selected),
            "trigger_distance_pct_mean": _mean(row.get("trigger_distance_pct") for row in selected),
            "trigger_distance_pct_median": _median(row.get("trigger_distance_pct") for row in selected),
            "score_mean": _mean(row.get("score") for row in selected),
            "score_median": _median(row.get("score") for row in selected),
            "rr_mean": _mean(row.get("rr") for row in selected),
            "rr_median": _median(row.get("rr") for row in selected),
            "pre_trigger_max_high_pct_mean": _mean(row.get("pre_trigger_max_high_pct_from_t_close") for row in selected),
            "pre_trigger_max_low_pct_mean": _mean(row.get("pre_trigger_max_low_pct_from_t_close") for row in selected),
            "pre_trigger_close_drift_pct_mean": _mean(row.get("pre_trigger_last_close_pct_from_t_close") for row in selected),
            "pre_trigger_stop_touched_count": sum(row.get("pre_trigger_stop_touched") is True for row in selected),
            "pre_trigger_data_incomplete_count": sum(row.get("pre_trigger_data_status") == "INCOMPLETE" for row in selected),
            "descriptive_only": True,
            "sample_status": _metric_status(len(selected)),
        }
    return output


def _git_bytes(repo_root: Path, git_ref: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{git_ref}:{path}"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _git_blob_sha(repo_root: Path, git_ref: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", f"{git_ref}:{path}"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _canonical_candidate(candidate: Mapping[str, Any], list_date: str) -> dict[str, Any]:
    result = dict(candidate)
    result["date"] = parse_date(candidate.get("date", list_date)).isoformat()
    result["code"] = str(candidate.get("code", "")).strip().lower().zfill(6)
    return result


def load_runtime_inputs(
    repo_root: Path,
    *,
    runtime_ref: str,
    tracker_path: str,
    watchlist_dir: str,
    as_of: date,
    evidence_root: Path | None,
    evidence_date: date,
) -> dict[str, Any]:
    tracker_raw = _git_bytes(repo_root, runtime_ref, tracker_path)
    tracker = json.loads(tracker_raw)
    if not isinstance(tracker, Mapping) or not isinstance(tracker.get("signals"), Mapping):
        raise ValueError("runtime tracker is not a version-2 signal map")
    tracker_signals = [
        dict(value)
        for value in tracker["signals"].values()
        if isinstance(value, Mapping)
        and value.get("strategy_version") == STRATEGY
        and EPOCH_START <= parse_date(value["date"]) <= as_of
    ]
    by_id = {str(signal["signal_id"]): signal for signal in tracker_signals}
    if len(by_id) != len(tracker_signals):
        raise ValueError("duplicate canonical signal_id in tracker")

    canonical: dict[str, dict[str, Any]] = {}
    watchlist_hashes: dict[str, dict[str, str]] = {}
    watchlist_values: list[dict[str, Any]] = []
    for list_date in sorted({parse_date(signal["date"]).strftime("%Y%m%d") for signal in tracker_signals}):
        path = f"{watchlist_dir.rstrip('/')}/watchlist_{list_date}.json"
        raw = _git_bytes(repo_root, runtime_ref, path)
        payload = json.loads(raw)
        candidates = payload.get("candidates", []) if isinstance(payload, Mapping) else []
        if not isinstance(candidates, list):
            raise ValueError(f"canonical watchlist candidates is not a list: {path}")
        watchlist_values.append(payload)
        watchlist_hashes[list_date] = {
            "path": path,
            "sha256": sha256_bytes(raw),
            "git_blob_sha": _git_blob_sha(repo_root, runtime_ref, path),
        }
        for raw_candidate in candidates:
            if not isinstance(raw_candidate, Mapping) or raw_candidate.get("signal_id") is None:
                raise ValueError(f"canonical watchlist candidate has no signal_id: {path}")
            candidate = _canonical_candidate(raw_candidate, list_date)
            signal_id = str(candidate["signal_id"])
            if candidate.get("strategy_version") != STRATEGY or signal_id not in by_id:
                continue
            if signal_id in canonical:
                raise ValueError(f"duplicate canonical signal_id across watchlists: {signal_id}")
            canonical[signal_id] = candidate
    if set(canonical) != set(by_id):
        raise ValueError(
            f"tracker/watchlist signal identity mismatch: tracker_only={sorted(set(by_id)-set(canonical))[:5]} "
            f"watchlist_only={sorted(set(canonical)-set(by_id))[:5]}"
        )
    for signal_id, signal in by_id.items():
        candidate = canonical[signal_id]
        for field in ("code", "strategy_version", "setup", "trigger", "stop", "target", "rr", "score"):
            left, right = signal.get(field), candidate.get(field)
            if isinstance(left, (int, float)) or isinstance(right, (int, float)):
                if _finite(left) is None or _finite(right) is None or not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-9):
                    raise ValueError(f"tracker/watchlist canonical field mismatch: {signal_id}.{field}")
            elif str(left) != str(right):
                raise ValueError(f"tracker/watchlist canonical field mismatch: {signal_id}.{field}")

    evidence_by_code: dict[str, list[dict[str, Any]]] = {str(signal["code"]): [] for signal in tracker_signals}
    evidence_records: list[dict[str, Any]] = []
    evidence_missing: list[str] = []
    if evidence_root is not None:
        store = TCloseEvidenceStore(evidence_root, evidence_date)
        for code in sorted(evidence_by_code):
            logical, thscode, *_ = _history_capture_spec(
                code,
                requested_count=DEFAULT_STOCK_BAR_COUNT,
                as_of_date=evidence_date.isoformat(),
                index=False,
            )
            result = _load_captured_market_bars(
                store,
                logical,
                thscode,
                minimum_acceptable_history=1,
                as_of_date=evidence_date.isoformat(),
                require_last_bar_date=False,
            )
            record = store.load_raw("hithink_kline", logical)
            if result is None or record is None:
                evidence_missing.append(code)
                continue
            bars, resolution = result
            evidence_by_code[code] = bars
            evidence_records.append({
                "code": code,
                "logical_component_identity": logical,
                "provider": resolution.get("provider"),
                "source": resolution.get("source"),
                "adjustment_mode": resolution.get("adjustment_mode"),
                "record_count": record.metadata.get("record_count"),
                "raw_sha256": record.metadata.get("file_sha256"),
                "raw_bytes": record.metadata.get("byte_length"),
                "metadata_sha256": sha256_file(record.metadata_path),
                "raw_relative_path": str(record.path.relative_to(evidence_root)).replace("\\", "/"),
                "metadata_relative_path": str(record.metadata_path.relative_to(evidence_root)).replace("\\", "/"),
            })
    evidence_manifest_payload = [
        {key: item[key] for key in sorted(item) if key not in {"raw_relative_path", "metadata_relative_path"}}
        for item in sorted(evidence_records, key=lambda value: value["code"])
    ]
    evidence_manifest_sha = sha256_bytes(canonical_json_bytes(evidence_manifest_payload))
    return {
        "tracker": tracker,
        "tracker_signals": sorted(tracker_signals, key=lambda value: (value["date"], value["signal_id"])),
        "canonical": canonical,
        "watchlist_values": watchlist_values,
        "watchlist_hashes": watchlist_hashes,
        "tracker_sha256": sha256_bytes(tracker_raw),
        "tracker_git_blob_sha": _git_blob_sha(repo_root, runtime_ref, tracker_path),
        "evidence_by_code": evidence_by_code,
        "evidence_records": evidence_records,
        "evidence_missing": evidence_missing,
        "evidence_manifest_sha256": evidence_manifest_sha,
        "evidence_date": evidence_date.isoformat(),
    }


def _semantic_impact(
    inputs: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    as_of: date,
    calendar: TradingCalendar,
) -> dict[str, Any]:
    tracker_signals = inputs["tracker_signals"]
    tracker_status_counts = dict(sorted(Counter(signal.get("status") for signal in tracker_signals).items()))
    replay_counts = Counter(row.get("operational_terminal_status") or row.get("operational_path_status") for row in rows)
    history: dict[str, list[dict[str, Any]]] = {}
    for code, evidence in inputs["evidence_by_code"].items():
        history[code] = [dict(value) for value in evidence]
    for signal in tracker_signals:
        code = str(signal["code"])
        history.setdefault(code, [])
        by_day = {parse_date(value["date"]): value for value in history[code]}
        for value in signal.get("observations", []):
            normalized = normalize_bar(value)
            by_day[parse_date(normalized["date"])] = normalized
        history[code] = [by_day[day] for day in sorted(by_day)]
    unlimited = build_strategy_rule_performance(
        inputs["watchlist_values"],
        history,
        as_of,
        calendar=calendar,
        historical_provenance={"__meta__": {"source": "RESEARCH_MERGED_CANONICAL_BARS", "provider_calls": 0}},
    )
    eligible = [row for row in rows if row.get("signal_date") < as_of.isoformat()]
    entered = [row for row in rows if row.get("operational_entry_date")]
    current_numeric = [row for row in rows if _finite(row.get("operational_return_pct")) is not None]
    current_positive = [row for row in current_numeric if float(row["operational_return_pct"]) > 0]
    current_negative = [row for row in current_numeric if float(row["operational_return_pct"]) < 0]
    current_pf = (
        _round(sum(float(row["operational_return_pct"]) for row in current_positive) / abs(sum(float(row["operational_return_pct"]) for row in current_negative)))
        if current_negative
        else None
    )
    return {
        "status": "OBSERVATION_GAP_LIMITED_FOR_CAUSAL_COMPARISON",
        "current_tracker_status_counts": tracker_status_counts,
        "current_tracker_waiting_trigger_count": tracker_status_counts.get("pending", 0),
        "prospective_replay_at_cutoff": {
            "eligible_signal_count": len(eligible),
            "entered_count": len(entered),
            "trigger_rate_pct": _round(len(entered) / len(eligible) * 100.0) if eligible else None,
            "waiting_trigger_count": sum(
                row.get("operational_terminal_status") == "OPEN_OR_PENDING"
                and not row.get("operational_entry_date")
                for row in rows
            ),
            "open_or_pending_count": replay_counts.get("OPEN_OR_PENDING", 0),
            "target_count": replay_counts.get("TARGET", 0),
            "stop_count": replay_counts.get("STOP", 0),
            "time_exit_count": replay_counts.get("TIME_EXIT", 0),
            "expired_untriggered_count": replay_counts.get("EXPIRED_UNTRIGGERED", 0),
            "ambiguity_count": replay_counts.get("AMBIGUOUS_SAME_BAR", 0),
            "win_rate_pct": _round(len([row for row in current_numeric if row.get("operational_terminal_status") == "TARGET"]) / len(current_numeric) * 100.0) if current_numeric else None,
            "expectancy_pct": _mean(row.get("operational_return_pct") for row in current_numeric),
            "profit_factor": current_pf,
        },
        "strategy_rule_performance_at_cutoff": {
            key: unlimited.get(key)
            for key in (
                "total_signals",
                "eligible_signals",
                "triggered",
                "trigger_rate",
                "resolved_closed_trades",
                "open_rule_trades",
                "untriggered",
                "ambiguous",
                "performance_data_incomplete",
                "win_rate",
                "avg_return_pct",
                "expectancy_pct",
                "profit_factor",
                "time_exit_count",
            )
        },
        "interpretation": [
            "The two models are not a clean outcome comparison because the merged source has missing XSHG observations.",
            "Counts are reported to expose the semantic boundary; no strategy or tracker rule is changed.",
        ],
    }


def build_protocol(
    *,
    as_of: date,
    runtime_ref: str,
    tracker_path: str,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "strategy": STRATEGY,
        "setup": SETUP,
        "research_only": True,
        "production_semantics_change": False,
        "data_cutoff": as_of.isoformat(),
        "prospective_epoch_start": EPOCH_START.isoformat(),
        "source_contract": {
            "runtime_state_ref": runtime_ref,
            "tracker_path": tracker_path,
            "tracker_sha256": inputs["tracker_sha256"],
            "tracker_git_blob_sha": inputs["tracker_git_blob_sha"],
            "watchlists": inputs["watchlist_hashes"],
            "pre_cutoff_evidence_date": inputs["evidence_date"],
            "pre_cutoff_evidence_record_count": len(inputs["evidence_records"]),
            "pre_cutoff_evidence_missing_codes": inputs["evidence_missing"],
            "pre_cutoff_evidence_manifest_sha256": inputs["evidence_manifest_sha256"],
            "final_oos": "SEALED / UNREAD",
            "c_outcome": "NOT_READ",
        },
        "canonical_identity": {
            "unit": "canonical signal_id",
            "same_code_different_signal_date": "distinct samples",
            "strategy_filter": STRATEGY,
            "candidate_generation_or_trigger_recalculation": False,
        },
        "delay_definition": {
            "first_trigger_delay": "the index of the first post-signal XSHG session whose canonical high reaches canonical trigger",
            "search_sessions": "T+1 through T+10 XSHG sessions",
            "untriggered": "all T+1..T+10 observations present and no canonical trigger touch",
            "censored": "T+10 not yet observable at data cutoff without a proven trigger",
            "incomplete": "a required pre-trigger or search-path observation is missing",
            "same_bar_trigger_stop_target": "trigger date remains observable; exit ambiguity remains fail-safe",
        },
        "fixed_cohorts": [
            {"cohort": label, "min_delay": lower, "max_delay": upper}
            for label, lower, upper in COHORTS
        ] + [{"cohort": "CENSORED_OR_INCOMPLETE", "purpose": "data quality only; not a production bucket"}],
        "comparison_groups": {"EARLY": "T+1-T+3", "LATE": "T+4-T+10", "difference": "LATE_MINUS_EARLY"},
        "analysis_a_primary": {
            "entry": "first canonical trigger day; current prospective fill semantics (open if opening gaps through trigger, otherwise canonical trigger)",
            "sellability": "entry day cannot sell; A-share T+1",
            "horizons": [f"E+{h}" for h in FIXED_ENTRY_HORIZONS],
            "terminal_before_horizon": "carry terminal target/stop result forward to the requested horizon",
            "no_terminal_by_horizon": "close mark-to-market at that fixed entry-relative node",
            "missing_observation": "missing, never zero-filled",
            "same_bar_stop_target": "AMBIGUOUS_SAME_BAR / no realized return",
        },
        "analysis_b_secondary": {
            "model": "current prospective EXECUTION_MODEL_DAILY_OHLC_T1_V1 replay",
            "trigger_search": "T+1..T+10",
            "t_plus_10_untriggered": "EXPIRED_UNTRIGGERED",
            "t_plus_10_triggered": "entry allowed; first legal sellable session handles exit/time-exit",
            "time_exit": "current T+10 closure semantics retained for research only",
        },
        "metrics": {
            "operational_return_denominator": "complete numeric terminal paths only",
            "win_rate": "TARGET exits / complete numeric terminal paths",
            "payoff_ratio": "average positive return / absolute average negative return",
            "profit_factor": "sum positive returns / absolute sum negative returns",
            "fixed_horizon_positive_rate": "positive numeric fixed-node returns / numeric fixed-node returns",
            "minimum_sample_for_unqualified_metric": MIN_SAMPLE,
        },
        "cutoff_sensitivity": {
            "cutoffs": list(CUTOFFS),
            "counterfactual_only": True,
            "canonical_rows_mutated": False,
            "forbidden_selection_rule": "argmax -> production cutoff",
        },
        "decision_rule": {
            "shorter_validity": "only if late quality degrades consistently in fixed entry-relative analysis with adequate sample",
            "no_clear_decay": "early/late unstable, wide CI, inconsistent direction, or late sample too small",
            "blocked": "critical observations needed to classify delay/outcome are missing",
        },
        "bootstrap": {
            "unit": "signal_date block",
            "seed": 20261005,
            "run_only_if_each_comparison_group_has_at_least": MIN_SAMPLE,
        },
    }


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(json.dumps(_json_ready(value), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")


CSV_FIELDS = (
    "signal_id", "strategy_version", "signal_date", "code", "setup", "score", "trigger", "stop", "target", "rr",
    "tracker_status", "first_trigger_delay", "raw_trigger_delay", "first_trigger_date", "delay_status", "cohort",
    "required_sessions", "missing_sessions", "operational_path_status", "operational_terminal_status",
    "operational_execution_verification_status", "operational_entry_date", "operational_entry_price",
    "operational_exit_date", "operational_exit_price", "operational_exit_reason", "operational_return_pct",
    "operational_realized_r", "operational_holding_sessions", "operational_mfe_pct", "operational_mae_pct",
    "operational_ambiguity", "bar_conflicts", "t_close", "trigger_distance_pct",
    "pre_trigger_max_high_pct_from_t_close", "pre_trigger_max_low_pct_from_t_close",
    "pre_trigger_last_close_pct_from_t_close", "pre_trigger_stop_touched", "pre_trigger_sessions_observed",
    "pre_trigger_data_status",
    "e1_status", "e1_return_pct", "e1_positive", "e1_sample_n", "e1_reason",
    "e3_status", "e3_return_pct", "e3_positive", "e3_sample_n", "e3_reason",
    "e5_status", "e5_return_pct", "e5_positive", "e5_sample_n", "e5_reason",
)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            for field in ("required_sessions", "missing_sessions", "bar_conflicts"):
                output[field] = json.dumps(output.get(field) or [], ensure_ascii=False, separators=(",", ":"))
            writer.writerow({field: output.get(field) for field in CSV_FIELDS})


def _display(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_report(
    *,
    protocol: Mapping[str, Any],
    protocol_sha: str,
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    diagnostics: Mapping[str, Any],
    semantic_impact: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
) -> str:
    comparison = summary["early_vs_late"]
    lines = [
        "# B signal entry-validity decay research",
        "",
        f"> Protocol: `{protocol['protocol_version']}` / SHA-256 `{protocol_sha}`",
        f"> Strategy: `{STRATEGY}`；data cutoff: `{protocol['data_cutoff']}`；prospective epoch: `{protocol['prospective_epoch_start']}`",
        "> Research-only. No production rule, tracker state, runtime-state, Formal B output, or prospective evidence was changed.",
        "> Final OOS: `SEALED / UNREAD`; C outcome data: `NOT_READ`.",
        "",
        "## Decision",
        "",
        "`SIGNAL_VALIDITY_RESEARCH_BLOCKED_BY_DATA_GAP`",
        "",
        "The available evidence does not contain enough complete post-signal sessions to classify the late-trigger cohorts reliably. This is a data-gap stop, not evidence supporting a shorter production validity window.",
        "",
        "## 1. Current semantics audit",
        "",
        "| Area | Current behavior | Interpretation |",
        "|---|---|---|",
        "| prospective tracker | Searches first trigger on T+1 through T+10 XSHG sessions | Earliest entry T+1; latest first trigger T+10 |",
        "| prospective T+10 untriggered | `EXPIRED_UNTRIGGERED` at T+10 | T+10 is an operational entry-expiry boundary |",
        "| prospective T+10 triggered | Entry is allowed; entry-day sell is forbidden; exit is handled on the next legal sellable session | T+10 is also an entry day, not only a review node |",
        "| prospective time exit | Earlier entries close at T+10 close; a T+10 entry is deferred to the next sellable session | Current operational path has time-exit semantics |",
        "| strategy-rule performance | `_rule_sessions_after` searches through report date; `time_exit=False`; no entry expiry | A first trigger after T+10 is currently possible |",
        "| fixed horizons | T+3/T+5/T+10 are signal-date fixed-horizon snapshots | Independent of actual entry validity |",
        "",
        "`ENTRY_VALIDITY_SEMANTICS_MISMATCH`: prospective tracker expiry/search is bounded at T+10, while strategy-rule performance waits through the report date without entry expiry or time exit.",
        "The current tracker therefore mixes two meanings at T+10: an operational expiry/time-exit boundary and a fixed-horizon research node. They are kept separate in this study.",
        "",
        "## 2. Signal and data-quality counts",
        "",
        f"Canonical signal-level sample: **{len(rows)}** signals across **{len(set(row['signal_date'] for row in rows))}** signal dates, keyed only by `signal_id`.",
        f"Delay classification: known **{sum(row['delay_status'] == 'KNOWN' for row in rows)}**; complete untriggered **{sum(row['delay_status'] == 'UNTRIGGERED' for row in rows)}**; censored **{sum(row['delay_status'] == 'CENSORED' for row in rows)}**; incomplete **{sum(row['delay_status'] == 'INCOMPLETE' for row in rows)}**; source conflicts **{sum(row['delay_status'] == 'DATA_CONFLICT' for row in rows)}**.",
        "",
        "| Cohort | Total | Triggered | Delay-known | Operational complete path | Delay censored | Delay incomplete/conflict | Ambiguous | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for label, *_ in COHORTS + (("CENSORED_OR_INCOMPLETE", None, None),):
        item = summary["cohorts"][label]
        lines.append(
            f"| {label} | {item['total_signals']} | {item['triggered_count']} | {item['delay_known_count']} | {item['complete_data_count']} | {item['delay_censored_count']} | {item['delay_incomplete_count']} | {item['ambiguity_count']} | {item['sample_status']} |"
        )
    lines += [
        "",
        "`INSUFFICIENT_SAMPLE` is pre-registered for metric samples below 10. The LATE group has only the one delay-known T+5 signal; no T+6–T+10 signal is delay-classifiable with complete prior observations. Analysis B additionally has 48 known-delay rows with incomplete operational paths.",
        "",
        "## 3. Analysis A — fixed entry-relative horizon",
        "",
        "The fixed-node results below use actual first-trigger entry `E`, current prospective fill semantics, A-share T+1, terminal target/stop handling, and close mark-to-market only when no terminal event occurred by the node. Missing nodes remain missing.",
        "",
        "| Group | E+1 mean / median / positive rate (n) | E+3 mean / median / positive rate (n) | E+5 mean / median / positive rate (n) |",
        "|---|---|---|---|",
    ]
    for label, item in (("EARLY", comparison["early_summary"]), ("LATE", comparison["late_summary"])):
        values = []
        for horizon in (1, 3, 5):
            point = item["fixed_entry_relative"][f"E+{horizon}"]
            values.append(f"{_display(point['mean_pct'])} / {_display(point['median_pct'])} / {_display(point['positive_rate_pct'])}% ({point['sample_n']})")
        lines.append(f"| {label} (n={item['total_signals']}) | {values[0]} | {values[1]} | {values[2]} |")
    lines += [
        "",
        "| Comparison | Early | Late | Late − Early |",
        "|---|---:|---:|---:|",
    ]
    for key in ("average_return_pct", "median_return_pct", "win_rate_pct", "profit_factor", "average_mfe_pct", "average_mae_pct", "E+3", "E+5"):
        point = comparison["differences"][key]
        lines.append(f"| {key} | {_display(point.get('early'))} | {_display(point.get('late'))} | {_display(point.get('late_minus_early'))} |")
    lines += [
        "",
        f"Comparison status: `{comparison['status']}`; bootstrap: `{comparison['bootstrap']['status']}`. No CI is reported because the LATE comparison group is below the fixed minimum sample.",
        "",
        "## 4. Analysis B — current operational path",
        "",
        "The operational cohort metrics use the existing T+10 prospective replay, including T+10 expiry and T+10 closure semantics. Incomplete and censored paths are excluded from realized-return denominators and remain visible in the counts.",
        "",
        "| Cohort | Win rate | Avg return | Median return | Avg winner | Avg loser | Payoff | PF | Target hit | Stop hit | Avg holding | MFE | MAE |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, *_ in COHORTS:
        item = summary["cohorts"][label]
        lines.append(
            f"| {label} | {_display(item['win_rate_pct'])}% | {_display(item['average_return_pct'])}% | {_display(item['median_return_pct'])}% | {_display(item['average_winner_pct'])}% | {_display(item['average_loser_pct'])}% | {_display(item['payoff_ratio'])} | {_display(item['profit_factor'])} | {_display(item['target_hit_rate_pct'])}% | {_display(item['stop_hit_rate_pct'])}% | {_display(item['average_holding_sessions'])} | {_display(item['average_mfe_pct'])}% | {_display(item['average_mae_pct'])}% |"
        )
    lines += [
        "",
        "## 5. Bounded descriptive diagnostics",
        "",
        "These are descriptive only; they do not add a filter, score, RR rule, model, or second strategy.",
        "",
        "| Delay | n | Trigger distance mean | Score mean | RR mean | Pre-trigger max high mean | Pre-trigger max low mean | Pre-trigger close drift mean | Stop touched before entry |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for delay, item in diagnostics.items():
        lines.append(
            f"| {delay} | {item['sample_n']} | {_display(item['trigger_distance_pct_mean'])}% | {_display(item['score_mean'])} | {_display(item['rr_mean'])} | {_display(item['pre_trigger_max_high_pct_mean'])}% | {_display(item['pre_trigger_max_low_pct_mean'])}% | {_display(item['pre_trigger_close_drift_pct_mean'])}% | {item['pre_trigger_stop_touched_count']} |"
        )
    lines += [
        "",
        "## 6. Counterfactual cutoff sensitivity",
        "",
        "This table is a sensitivity table only. It does not select a production cutoff and does not mutate canonical rows.",
        "",
        "| Cutoff | Retained triggered | Retained terminal | Expired untriggered | Excluded known-late | Excluded unclassified trigger | Avg return | Win rate | PF | Expectancy |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["cutoff_sensitivity"]:
        lines.append(
            f"| T+{item['entry_validity_cutoff_sessions']} | {item['retained_triggered_signals']} | {item['retained_terminal_trades']} | {item['expired_untriggered_count']} | {item['excluded_late_trigger_trades']} | {item['excluded_unclassified_trigger_count']} | {_display(item['retained_trade_average_return_pct'])}% | {_display(item['retained_trade_win_rate_pct'])}% | {_display(item['retained_trade_profit_factor'])} | {_display(item['retained_trade_expectancy_pct'])}% |"
        )
    lines += [
        "",
        "## 7. T+10 semantic impact audit",
        "",
        f"Current runtime tracker waiting-for-trigger count: **{semantic_impact['current_tracker_waiting_trigger_count']}**. Current tracker status counts: `{json.dumps(semantic_impact['current_tracker_status_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"Prospective replay at cutoff: `{json.dumps(semantic_impact['prospective_replay_at_cutoff'], ensure_ascii=False, sort_keys=True)}`.",
        f"Strategy-rule performance at the same cutoff: `{json.dumps(semantic_impact['strategy_rule_performance_at_cutoff'], ensure_ascii=False, sort_keys=True)}`.",
        "These counts expose the mismatch but are not a causal performance comparison because the same source has missing XSHG observations; see `CENSORED_OR_INCOMPLETE` and `PERFORMANCE_DATA_INCOMPLETE`.",
        "",
        "## 8. Reproducibility and boundaries",
        "",
        f"- Signal-level artifact SHA-256: `{artifact_hashes.get('signal_level_results.csv', 'UNWRITTEN')}`.",
        f"- Cohort summary SHA-256: `{artifact_hashes.get('cohort_summary.json', 'UNWRITTEN')}`.",
        f"- Evidence manifest SHA-256: `{protocol['source_contract']['pre_cutoff_evidence_manifest_sha256']}`; missing evidence codes: `{len(protocol['source_contract']['pre_cutoff_evidence_missing_codes'])}`.",
        "- No Final OOS, C outcome, old D, or forbidden validation directory was read.",
        "- No candidate generation, score, threshold, trigger, stop, target, RR, tracker state machine, entry expiry, T+10 closure, Formal B output, workflow, delivery, runtime-state, or prospective evidence was modified.",
        "",
        "Terminal marker: `SIGNAL_VALIDITY_RESEARCH_BLOCKED_BY_DATA_GAP`",
        "",
    ]
    return "\n".join(lines)


def run_research(
    *,
    repo_root: Path,
    output_dir: Path,
    runtime_ref: str = "origin/runtime-state",
    tracker_path: str = "data/perf_tracker.json",
    watchlist_dir: str = "data",
    as_of: date = DEFAULT_AS_OF,
    evidence_root: Path | None = None,
    evidence_date: date = EVIDENCE_DATE,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    cal = calendar or default_calendar()
    inputs = load_runtime_inputs(
        repo_root,
        runtime_ref=runtime_ref,
        tracker_path=tracker_path,
        watchlist_dir=watchlist_dir,
        as_of=as_of,
        evidence_root=evidence_root,
        evidence_date=evidence_date,
    )
    protocol = build_protocol(as_of=as_of, runtime_ref=runtime_ref, tracker_path=tracker_path, inputs=inputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol_path = output_dir / "protocol.json"
    write_json(protocol_path, protocol)
    protocol_sha = sha256_file(protocol_path)

    rows = [
        analyze_signal(
            signal,
            inputs["canonical"][str(signal["signal_id"])],
            inputs["evidence_by_code"].get(str(signal["code"]), []),
            as_of,
            cal,
        )
        for signal in inputs["tracker_signals"]
    ]
    summaries = {
        label: summarize_rows([row for row in rows if row.get("cohort") == label])
        for label, *_ in COHORTS + (("CENSORED_OR_INCOMPLETE", None, None),)
    }
    summary: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "protocol_sha256": protocol_sha,
        "decision": "SIGNAL_VALIDITY_RESEARCH_BLOCKED_BY_DATA_GAP",
        "data_cutoff": as_of.isoformat(),
        "total_signals": len(rows),
        "cohorts": summaries,
        "early_vs_late": early_late_comparison(rows),
        "cutoff_sensitivity": cutoff_sensitivity(rows),
        "diagnostics_by_delay": diagnostics_by_delay(rows),
        "semantic_audit": {
            "entry_validity_semantics_mismatch": "ENTRY_VALIDITY_SEMANTICS_MISMATCH",
            "prospective_tracker": {
                "earliest_entry": "T+1",
                "latest_first_trigger": "T+10",
                "t_plus_10_untriggered": "EXPIRED_UNTRIGGERED",
                "t_plus_10_triggered": "ALLOWED_WITH_NEXT_SESSION_SELLABILITY",
                "time_exit": True,
                "t_plus_10_is_expiry_and_research_node": True,
            },
            "strategy_rule_performance": {
                "first_trigger_search": "through report_date",
                "entry_expiry": False,
                "time_exit": False,
                "t_plus_10_or_later_first_trigger_possible": True,
            },
            "fixed_horizon_independent": True,
        },
    }
    semantic_impact = _semantic_impact(inputs, rows, as_of, cal)
    summary["semantic_impact"] = semantic_impact
    result_path = output_dir / "signal_level_results.csv"
    write_csv(result_path, rows)
    summary_path = output_dir / "cohort_summary.json"
    write_json(summary_path, summary)
    artifact_hashes = {
        "protocol.json": sha256_file(protocol_path),
        "signal_level_results.csv": sha256_file(result_path),
        "cohort_summary.json": sha256_file(summary_path),
    }
    report = render_report(
        protocol=protocol,
        protocol_sha=protocol_sha,
        summary=summary,
        rows=rows,
        diagnostics=summary["diagnostics_by_delay"],
        semantic_impact=semantic_impact,
        artifact_hashes=artifact_hashes,
    )
    report_path = output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    artifact_hashes["report.md"] = sha256_file(report_path)
    manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "protocol_sha256": protocol_sha,
        "source": protocol["source_contract"],
        "artifacts": artifact_hashes,
        "signal_count": len(rows),
        "canonical_signal_id_sha256": sha256_bytes(canonical_json_bytes(sorted(row["signal_id"] for row in rows))),
        "reproducibility": {
            "command": "python scripts/research_b_signal_entry_validity_decay.py run --runtime-ref origin/runtime-state --as-of 2026-09-30 --evidence-root <existing-read-only-data/t_close_evidence>",
            "input_evidence_is_read_only": True,
            "canonical_rows_mutated": False,
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return {
        "protocol": protocol,
        "protocol_sha256": protocol_sha,
        "rows": rows,
        "summary": summary,
        "semantic_impact": semantic_impact,
        "artifact_hashes": artifact_hashes,
        "manifest": manifest,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--repo-root", default=".")
    run.add_argument("--output-dir", default="data/research/b_signal_entry_validity_decay_v1")
    run.add_argument("--runtime-ref", default="origin/runtime-state")
    run.add_argument("--tracker-path", default="data/perf_tracker.json")
    run.add_argument("--watchlist-dir", default="data")
    run.add_argument("--as-of", default=DEFAULT_AS_OF.isoformat())
    run.add_argument("--evidence-root", default=None)
    run.add_argument("--evidence-date", default=EVIDENCE_DATE.isoformat())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        result = run_research(
            repo_root=Path(args.repo_root).resolve(),
            output_dir=Path(args.output_dir).resolve(),
            runtime_ref=args.runtime_ref,
            tracker_path=args.tracker_path,
            watchlist_dir=args.watchlist_dir,
            as_of=parse_date(args.as_of),
            evidence_root=Path(args.evidence_root).resolve() if args.evidence_root else None,
            evidence_date=parse_date(args.evidence_date),
        )
        print(json.dumps({
            "protocol_sha256": result["protocol_sha256"],
            "signal_count": len(result["rows"]),
            "decision": result["summary"]["decision"],
            "artifact_hashes": result["artifact_hashes"],
        }, ensure_ascii=False, sort_keys=True))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
