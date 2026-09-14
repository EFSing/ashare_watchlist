"""Observational volume focus and T+1 giveback diagnostics for formal B.

This module is deliberately downstream of the canonical watchlist and the
existing rule-price performance evaluator.  It never evaluates, filters, or
orders formal B candidates and it never writes canonical watchlists,
prospective observations, or formal outcomes.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
import math
import statistics
from typing import Any, Iterable, Mapping

from trading_calendar import TradingCalendar, default_calendar
from track_perf import (
    CURRENT_PROSPECTIVE_STRATEGY,
    EXIT_REASON_STOP,
    EXIT_REASON_TARGET,
    RULE_STATUS_CLOSED,
    _next_session_after,
    _rule_history_bars,
    _rule_history_value,
    build_strategy_rule_performance,
    parse_date,
)
from watchlist_schema import stable_signal_id


VOLUME_CONFIRM_FOCUS_VERSION = "B_VOLUME_CONFIRM_FOCUS_V1"
VOLUME_CONFIRM_FOCUS_THRESHOLD = 1.20
VOLUME_CONFIRM_FOCUS_CLASSIFICATION = "OBSERVATIONAL_ONLY"
VOLUME_CONFIRM_FOCUS_FORMAL_BOUNDARY = "NOT_FORMAL_B"
PROSPECTIVE_EPOCH_BOUNDARY = "FIRST_GENUINE_T_CLOSE_RUN_AFTER_DEPLOYMENT"
EVIDENCE_ACCUMULATING = "EVIDENCE_ACCUMULATING"
REVIEW_GATE_REACHED = "REVIEW_GATE_REACHED"
REVIEW_GATE_XSHG_SESSIONS = 20
REVIEW_GATE_FOCUS_TRIGGERED = 20
FAST_STOP_DEFINITION = "STOP on first or second sellable XSHG session (D+1 or D+2)"
EXPERIMENT_TRACKER_KEY = VOLUME_CONFIRM_FOCUS_VERSION


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalise_date(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    try:
        return parse_date(value).isoformat()
    except (TypeError, ValueError):
        return None


def _watchlists(source: Any) -> list[Mapping[str, Any]]:
    if isinstance(source, Mapping):
        return [source] if isinstance(source.get("candidates"), list) else []
    if isinstance(source, (str, bytes)):
        return []
    try:
        return [item for item in source if isinstance(item, Mapping)]
    except TypeError:
        return []


def _candidate_list(source: Any) -> list[Mapping[str, Any]]:
    if isinstance(source, Mapping) and isinstance(source.get("candidates"), list):
        return [item for item in source["candidates"] if isinstance(item, Mapping)]
    if isinstance(source, (str, bytes)):
        return []
    try:
        return [item for item in source if isinstance(item, Mapping)]
    except TypeError:
        return []


def is_volume_focus_candidate(candidate: Mapping[str, Any] | Any) -> bool:
    """Return whether a candidate passes the one frozen observational rule."""

    if not isinstance(candidate, Mapping):
        return False
    value = _finite_number(candidate.get("vol_ratio"))
    return value is not None and value >= VOLUME_CONFIRM_FOCUS_THRESHOLD


def focus_candidates(source: Any) -> list[dict[str, Any]]:
    """Return focus candidates in the input's canonical order."""

    return [dict(candidate) for candidate in _candidate_list(source) if is_volume_focus_candidate(candidate)]


def _candidate_records(canonical_watchlists: Any) -> list[dict[str, Any]]:
    """Build immutable signal-shaped candidate records without changing input."""

    records: list[dict[str, Any]] = []
    for watchlist in _watchlists(canonical_watchlists):
        list_date = _normalise_date(watchlist.get("date"))
        list_strategy = watchlist.get("strategy_version")
        for raw_candidate in _candidate_list(watchlist):
            strategy = raw_candidate.get("strategy_version", list_strategy)
            signal_date = _normalise_date(raw_candidate.get("date", list_date))
            setup = raw_candidate.get("setup") or raw_candidate.get("buy_type")
            if strategy != CURRENT_PROSPECTIVE_STRATEGY or signal_date is None or not setup:
                continue
            candidate = dict(raw_candidate)
            code = str(candidate.get("code", ""))
            candidate["signal_id"] = candidate.get("signal_id") or stable_signal_id(
                str(strategy), signal_date, code, str(setup)
            )
            candidate["strategy_version"] = str(strategy)
            candidate["date"] = signal_date
            candidate["setup"] = str(setup)
            records.append(candidate)
    return records


def _recent_repeat_codes(
    current_watchlist: Mapping[str, Any],
    canonical_watchlists: Any,
) -> set[str]:
    current_date = _normalise_date(current_watchlist.get("date"))
    if current_date is None:
        return set()
    current_codes = {
        str(candidate.get("code"))
        for candidate in _candidate_list(current_watchlist)
        if candidate.get("code") is not None
    }
    prior_codes = {
        str(candidate.get("code"))
        for candidate in _candidate_records(canonical_watchlists)
        if candidate.get("date") < current_date and candidate.get("code") is not None
    }
    return current_codes & prior_codes


def build_current_focus_summary(
    current_watchlist: Mapping[str, Any],
    canonical_watchlists: Any = (),
) -> dict[str, Any]:
    """Build the report-facing current focus summary.

    Membership is computed only from ``vol_ratio``.  Other fields are copied
    solely for descriptive display and cannot alter membership.
    """

    candidates = _candidate_list(current_watchlist)
    repeat_codes = _recent_repeat_codes(current_watchlist, canonical_watchlists)
    focused: list[dict[str, Any]] = []
    for candidate in candidates:
        if not is_volume_focus_candidate(candidate):
            continue
        focused.append({
            "code": candidate.get("code"),
            "name": candidate.get("name"),
            "signal_id": candidate.get("signal_id"),
            "score": candidate.get("score"),
            "vol_ratio": candidate.get("vol_ratio"),
            "trigger": candidate.get("trigger"),
            "stop": candidate.get("stop"),
            "target": candidate.get("target"),
            "rr": candidate.get("rr"),
            "stop_dist": candidate.get("stop_dist"),
            "sector": candidate.get("sector"),
            "chg": candidate.get("chg"),
            "target_type": candidate.get("target_type"),
            "recent_repeat": str(candidate.get("code")) in repeat_codes,
        })
    count = len(candidates)
    focus_count = len(focused)
    return {
        "experiment_version": VOLUME_CONFIRM_FOCUS_VERSION,
        "classification": VOLUME_CONFIRM_FOCUS_CLASSIFICATION,
        "formal_boundary": VOLUME_CONFIRM_FOCUS_FORMAL_BOUNDARY,
        "threshold": VOLUME_CONFIRM_FOCUS_THRESHOLD,
        "canonical_candidate_count": count,
        "focus_candidate_count": focus_count,
        "focus_ratio_pct": round(focus_count / count * 100.0, 6) if count else None,
        "focus_candidates": focused,
        "empty_state": "今日无量能确认候选" if not focused else None,
    }


def _epoch_record(tracker: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(tracker, Mapping):
        return None
    experiments = tracker.get("observational_experiments")
    if not isinstance(experiments, Mapping):
        return None
    raw = experiments.get(EXPERIMENT_TRACKER_KEY)
    if not isinstance(raw, Mapping):
        return None
    epoch_start = _normalise_date(raw.get("epoch_start"))
    threshold = _finite_number(raw.get("threshold"))
    if (
        raw.get("experiment_version") != VOLUME_CONFIRM_FOCUS_VERSION
        or threshold != VOLUME_CONFIRM_FOCUS_THRESHOLD
        or raw.get("epoch_boundary") != PROSPECTIVE_EPOCH_BOUNDARY
        or epoch_start is None
    ):
        return {
            "status": "EPOCH_METADATA_INVALID",
            "epoch_start": None,
            "error": "volume focus epoch metadata is missing or conflicts with the frozen experiment",
        }
    return {**dict(raw), "status": "STARTED", "epoch_start": epoch_start}


def ensure_volume_focus_epoch(
    tracker: dict[str, Any],
    signal_date: date | datetime | str,
    *,
    source_commit: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Register the first genuine runner date in existing tracker metadata.

    This is a single small metadata record in the existing tracker, not a
    second tracker or an outcome store.  Existing records are immutable once
    established; a later historical/backfill date cannot move the boundary.
    """

    if not isinstance(tracker, dict):
        raise ValueError("tracker must be an object")
    epoch_start = _normalise_date(signal_date)
    if epoch_start is None:
        raise ValueError("signal_date must be a canonical date")
    experiments = tracker.setdefault("observational_experiments", {})
    if not isinstance(experiments, dict):
        raise ValueError("tracker observational_experiments metadata is not an object")
    existing = experiments.get(EXPERIMENT_TRACKER_KEY)
    if existing is not None:
        if not isinstance(existing, dict):
            raise ValueError("volume focus epoch metadata is not an object")
        known = _epoch_record(tracker)
        if known is None or known.get("status") != "STARTED":
            raise ValueError("volume focus epoch metadata conflicts with the frozen experiment")
        return dict(existing), False
    record = {
        "experiment_version": VOLUME_CONFIRM_FOCUS_VERSION,
        "classification": VOLUME_CONFIRM_FOCUS_CLASSIFICATION,
        "formal_boundary": VOLUME_CONFIRM_FOCUS_FORMAL_BOUNDARY,
        "threshold": VOLUME_CONFIRM_FOCUS_THRESHOLD,
        "epoch_boundary": PROSPECTIVE_EPOCH_BOUNDARY,
        "epoch_start": epoch_start,
        "initialized_by": "first genuine successful T-close runner after deployment",
        "source_commit": source_commit or "UNKNOWN_ORIGIN",
        "no_pre_epoch_backfill": True,
        "review_gate": {
            "xshg_sessions": REVIEW_GATE_XSHG_SESSIONS,
            "focus_triggered_samples": REVIEW_GATE_FOCUS_TRIGGERED,
            "formal_strategy_change_before_gate": False,
        },
    }
    experiments[EXPERIMENT_TRACKER_KEY] = record
    return dict(record), True


def _performance_rows(performance: Any) -> list[Mapping[str, Any]]:
    if isinstance(performance, Mapping):
        rows = performance.get("all_rows")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    if isinstance(performance, (str, bytes)):
        return []
    try:
        return [row for row in performance if isinstance(row, Mapping)]
    except TypeError:
        return []


def _candidate_by_id(canonical_watchlists: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for candidate in _candidate_records(canonical_watchlists):
        signal_id = str(candidate.get("signal_id", ""))
        if signal_id:
            result[signal_id] = candidate
    return result


def _number_list(rows: Iterable[Mapping[str, Any]], key: str) -> list[float]:
    return [number for number in (_finite_number(row.get(key)) for row in rows) if number is not None]


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    value = ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    return round(value, 6)


def _distribution(values: Iterable[Any]) -> dict[str, Any]:
    numbers = sorted(number for number in (_finite_number(value) for value in values) if number is not None)
    return {
        "n": len(numbers),
        "mean": round(statistics.fmean(numbers), 6) if numbers else None,
        "median": round(statistics.median(numbers), 6) if numbers else None,
        "min": round(numbers[0], 6) if numbers else None,
        "q25": _quantile(numbers, 0.25),
        "q75": _quantile(numbers, 0.75),
        "max": round(numbers[-1], 6) if numbers else None,
    }


def _is_target(row: Mapping[str, Any]) -> bool:
    return row.get("exit_reason") == EXIT_REASON_TARGET


def _is_stop(row: Mapping[str, Any]) -> bool:
    return row.get("exit_reason") == EXIT_REASON_STOP


def _is_resolved(row: Mapping[str, Any]) -> bool:
    return row.get("status") == RULE_STATUS_CLOSED and (_is_target(row) or _is_stop(row))


def _is_triggered(row: Mapping[str, Any]) -> bool:
    if row.get("entry_date") or row.get("trigger_date"):
        return True
    return row.get("status") in {RULE_STATUS_CLOSED, "OPEN", "UNTRIGGERED", "AMBIGUOUS_SAME_BAR"} and row.get("status") != "UNTRIGGERED"


def _sellable_session_index(
    entry_date: Any,
    exit_date: Any,
    calendar: TradingCalendar,
) -> int | None:
    try:
        entry = parse_date(entry_date)
        exit_day = parse_date(exit_date)
    except (TypeError, ValueError):
        return None
    if exit_day <= entry:
        return None
    current = _next_session_after(entry, calendar)
    index = 1
    while current < exit_day:
        current = _next_session_after(current, calendar)
        index += 1
    return index if current == exit_day else None


def _outcome_metrics(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    resolved = [row for row in rows if _is_resolved(row)]
    targets = [row for row in resolved if _is_target(row)]
    stops = [row for row in resolved if _is_stop(row)]
    returns = _number_list(resolved, "realized_return_pct")
    r_values = _number_list(resolved, "realized_r")
    mfe_values = _number_list(resolved, "mfe_pct")
    mae_values = _number_list(resolved, "mae_pct")
    positive = sum(value for value in _number_list(targets, "realized_return_pct") if value > 0)
    negative = sum(value for value in _number_list(stops, "realized_return_pct") if value < 0)
    fast_stop_count = sum(bool(row.get("fast_stop")) for row in stops)
    return {
        "total_signals": len(rows),
        "triggered": sum(_is_triggered(row) for row in rows),
        "resolved": len(resolved),
        "target": len(targets),
        "stop": len(stops),
        "win_rate": round(len(targets) / len(resolved) * 100.0, 6) if resolved else None,
        "fast_stop_count": fast_stop_count,
        "fast_stop_rate_pct": round(fast_stop_count / len(stops) * 100.0, 6) if stops else None,
        "expectancy_pct": round(statistics.fmean(returns), 6) if returns else None,
        "profit_factor": round(positive / abs(negative), 6) if negative < 0 else None,
        "avg_mfe_pct": round(statistics.fmean(mfe_values), 6) if mfe_values else None,
        "median_mfe_pct": round(statistics.median(mfe_values), 6) if mfe_values else None,
        "avg_mae_pct": round(statistics.fmean(mae_values), 6) if mae_values else None,
        "median_mae_pct": round(statistics.median(mae_values), 6) if mae_values else None,
        "untriggered": sum(row.get("status") == "UNTRIGGERED" for row in rows),
        "ambiguous": sum(row.get("status") == "AMBIGUOUS_SAME_BAR" for row in rows),
    }


def _sessions_inclusive(start: str | None, end: date, calendar: TradingCalendar) -> int:
    if start is None:
        return 0
    try:
        current = parse_date(start)
    except (TypeError, ValueError):
        return 0
    if current > end:
        return 0
    count = 0
    while current <= end:
        if calendar.is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def build_volume_cohort_summary(
    canonical_watchlists: Any,
    performance: Any,
    as_of_date: date | datetime | str,
    *,
    epoch_start: date | datetime | str | None,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Split a prospective cohort without reading or changing formal outcomes."""

    cal = calendar or default_calendar()
    as_of = parse_date(as_of_date)
    epoch = _normalise_date(epoch_start)
    candidate_by_id = _candidate_by_id(canonical_watchlists)
    formal_by_id = {
        str(row.get("signal_id")): dict(row)
        for row in _performance_rows(performance)
        if row.get("signal_id")
    }
    prospective: list[dict[str, Any]] = []
    pre_epoch_count = 0
    for signal_id, candidate in sorted(candidate_by_id.items(), key=lambda item: (str(item[1].get("date")), item[0])):
        signal_date = _normalise_date(candidate.get("date"))
        if signal_date is None or parse_date(signal_date) > as_of:
            continue
        if epoch is None or parse_date(signal_date) < parse_date(epoch):
            pre_epoch_count += 1
            continue
        row = dict(candidate)
        row.update(formal_by_id.get(signal_id, {}))
        row.setdefault("signal_id", signal_id)
        row.setdefault("signal_date", signal_date)
        row.setdefault("date", signal_date)
        row["vol_ratio"] = candidate.get("vol_ratio")
        row["candidate_score"] = candidate.get("score")
        volume = _finite_number(candidate.get("vol_ratio"))
        row["cohort"] = "A" if volume is not None and volume >= VOLUME_CONFIRM_FOCUS_THRESHOLD else (
            "B" if volume is not None and volume < VOLUME_CONFIRM_FOCUS_THRESHOLD else None
        )
        if row["cohort"] is not None:
            prospective.append(row)

    cohorts: dict[str, dict[str, Any]] = {}
    for label, description in (
        ("A", "vol_ratio >= 1.20"),
        ("B", "vol_ratio < 1.20"),
    ):
        rows = [row for row in prospective if row.get("cohort") == label]
        for row in rows:
            if _is_stop(row):
                row["fast_stop"] = _sellable_session_index(
                    row.get("entry_date"), row.get("exit_date"), cal
                ) in (1, 2)
        metrics = _outcome_metrics(rows)
        metrics.update({"cohort": label, "definition": description})
        cohorts[label] = metrics

    epoch_sessions = _sessions_inclusive(epoch, as_of, cal)
    focus_triggered = cohorts["A"]["triggered"]
    gate_reached = bool(
        epoch is not None
        and epoch_sessions >= REVIEW_GATE_XSHG_SESSIONS
        and focus_triggered >= REVIEW_GATE_FOCUS_TRIGGERED
    )
    evidence_status = REVIEW_GATE_REACHED if gate_reached else EVIDENCE_ACCUMULATING
    return {
        "experiment_version": VOLUME_CONFIRM_FOCUS_VERSION,
        "classification": VOLUME_CONFIRM_FOCUS_CLASSIFICATION,
        "formal_boundary": VOLUME_CONFIRM_FOCUS_FORMAL_BOUNDARY,
        "threshold": VOLUME_CONFIRM_FOCUS_THRESHOLD,
        "epoch_boundary": PROSPECTIVE_EPOCH_BOUNDARY,
        "epoch_start": epoch,
        "as_of_date": as_of.isoformat(),
        "evidence_status": evidence_status,
        "review_gate": {
            "status": evidence_status,
            "xshg_sessions": epoch_sessions,
            "xshg_sessions_required": REVIEW_GATE_XSHG_SESSIONS,
            "focus_triggered": focus_triggered,
            "focus_triggered_required": REVIEW_GATE_FOCUS_TRIGGERED,
            "formal_strategy_change_allowed": False,
        },
        "pre_epoch_excluded_signals": pre_epoch_count,
        "unclassified_missing_or_invalid_vol_ratio": sum(
            1 for candidate in candidate_by_id.values()
            if _normalise_date(candidate.get("date")) is not None
            and parse_date(_normalise_date(candidate.get("date"))) <= as_of
            and epoch is not None
            and parse_date(_normalise_date(candidate.get("date"))) >= parse_date(epoch)
            and _finite_number(candidate.get("vol_ratio")) is None
        ),
        "cohorts": cohorts,
        "no_automatic_formal_change": True,
    }


def build_volume_focus_report(
    current_watchlist: Mapping[str, Any],
    canonical_watchlists: Any,
    performance: Any,
    tracker: Mapping[str, Any] | None,
    report_date: date | datetime | str,
    *,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Build the complete report context for the observational focus panel."""

    epoch = _epoch_record(tracker)
    epoch_start = epoch.get("epoch_start") if epoch and epoch.get("status") == "STARTED" else None
    current = build_current_focus_summary(current_watchlist, canonical_watchlists)
    cohorts = build_volume_cohort_summary(
        canonical_watchlists,
        performance,
        report_date,
        epoch_start=epoch_start,
        calendar=calendar,
    )
    if epoch and epoch.get("status") == "EPOCH_METADATA_INVALID":
        cohorts["evidence_status"] = "EPOCH_METADATA_INVALID"
        cohorts["review_gate"]["status"] = "EPOCH_METADATA_INVALID"
    return {
        **current,
        "prospective_epoch_start": epoch_start,
        "prospective_epoch_status": epoch.get("status", "NOT_STARTED") if epoch else "NOT_STARTED",
        "evidence_status": cohorts["evidence_status"],
        "review_gate": cohorts["review_gate"],
        "cohorts": cohorts["cohorts"],
        "pre_epoch_excluded_signals": cohorts["pre_epoch_excluded_signals"],
        "unclassified_missing_or_invalid_vol_ratio": cohorts["unclassified_missing_or_invalid_vol_ratio"],
        "no_automatic_formal_change": True,
    }


def _with_candidate_fields(
    canonical_watchlists: Any,
    performance: Any,
    as_of: date,
) -> list[dict[str, Any]]:
    candidates = _candidate_by_id(canonical_watchlists)
    rows_by_id = {
        str(row.get("signal_id")): dict(row)
        for row in _performance_rows(performance)
        if row.get("signal_id")
    }
    result: list[dict[str, Any]] = []
    for signal_id, candidate in candidates.items():
        if _normalise_date(candidate.get("date")) is None or parse_date(candidate["date"]) > as_of:
            continue
        row = dict(candidate)
        row.update(rows_by_id.get(signal_id, {}))
        row["vol_ratio"] = candidate.get("vol_ratio")
        row["candidate_score"] = candidate.get("score")
        result.append(row)
    return result


def build_retrospective_volume_summary(
    canonical_watchlists: Any,
    performance: Any,
    as_of_date: date | datetime | str,
    *,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Describe the pre-registered volume hypothesis retrospectively."""

    as_of = parse_date(as_of_date)
    rows = _with_candidate_fields(canonical_watchlists, performance, as_of)
    resolved = [row for row in rows if _is_resolved(row)]
    targets = [row for row in resolved if _is_target(row)]
    stops = [row for row in resolved if _is_stop(row)]
    cal = calendar or default_calendar()
    for row in stops:
        row["fast_stop"] = _sellable_session_index(row.get("entry_date"), row.get("exit_date"), cal) in (1, 2)

    def descriptive(group: list[Mapping[str, Any]]) -> dict[str, Any]:
        volumes = _number_list(group, "vol_ratio")
        scores = _number_list(group, "candidate_score")
        return {
            "sample_count": len(group),
            "vol_ratio": {
                **_distribution(volumes),
                "count_ge_1_20": sum(value >= VOLUME_CONFIRM_FOCUS_THRESHOLD for value in volumes),
                "proportion_ge_1_20_pct": round(
                    sum(value >= VOLUME_CONFIRM_FOCUS_THRESHOLD for value in volumes) / len(volumes) * 100.0,
                    6,
                ) if volumes else None,
            },
            "score": _distribution(scores),
        }

    fast_by_cohort: dict[str, dict[str, Any]] = {}
    for label, predicate in (
        ("A", lambda value: value is not None and value >= VOLUME_CONFIRM_FOCUS_THRESHOLD),
        ("B", lambda value: value is not None and value < VOLUME_CONFIRM_FOCUS_THRESHOLD),
    ):
        cohort_stops = [row for row in stops if predicate(_finite_number(row.get("vol_ratio")))]
        fast_count = sum(bool(row.get("fast_stop")) for row in cohort_stops)
        fast_by_cohort[label] = {
            "definition": "vol_ratio >= 1.20" if label == "A" else "vol_ratio < 1.20",
            "stop_count": len(cohort_stops),
            "fast_stop_count": fast_count,
            "fast_stop_rate_pct": round(fast_count / len(cohort_stops) * 100.0, 6) if cohort_stops else None,
        }

    return {
        "schema_version": "B_VOLUME_CONFIRM_FOCUS_RETROSPECTIVE_SUMMARY_V1",
        "status": "COMPLETE",
        "analysis_cutoff": as_of.isoformat(),
        "retrospective_only": True,
        "threshold": VOLUME_CONFIRM_FOCUS_THRESHOLD,
        "threshold_search": False,
        "not_prospective_proof": True,
        "resolved_total": len(resolved),
        "target": descriptive(targets),
        "stop": descriptive(stops),
        "fast_stop": {
            "definition": FAST_STOP_DEFINITION,
            "count": sum(bool(row.get("fast_stop")) for row in stops),
            "rate_pct": round(sum(bool(row.get("fast_stop")) for row in stops) / len(stops) * 100.0, 6) if stops else None,
            "by_volume_cohort": fast_by_cohort,
        },
        "score_separation": {
            "target_mean": descriptive(targets)["score"]["mean"],
            "target_median": descriptive(targets)["score"]["median"],
            "stop_mean": descriptive(stops)["score"]["mean"],
            "stop_median": descriptive(stops)["score"]["median"],
            "interpretation": "DESCRIPTIVE_ONLY_NO_CLEAR_SEPARATION_CLAIM",
        },
    }


def _entry_day_bar(
    row: Mapping[str, Any],
    historical_ohlc: Mapping[str, Any] | None,
    as_of: date,
) -> dict[str, float | None] | None:
    entry_date = _normalise_date(row.get("entry_date") or row.get("trigger_date"))
    if entry_date is None:
        return None
    raw_history = _rule_history_value(historical_ohlc, str(row.get("code", "")))
    if raw_history is None:
        return None
    bars, invalid_days, _errors = _rule_history_bars(raw_history, as_of)
    parsed = parse_date(entry_date)
    if parsed in invalid_days:
        return None
    return dict(bars.get(parsed, {})) or None


def build_t1_giveback_diagnostic(
    canonical_watchlists: Any,
    historical_ohlc: Mapping[str, Any] | None,
    as_of_date: date | datetime | str,
    *,
    performance: Any = None,
    historical_provenance: Mapping[str, Any] | None = None,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Classify entry-day target touches among formal resolved STOP trades.

    Formal rows are produced by ``build_strategy_rule_performance`` when the
    caller does not provide them.  This function only reads those rows and
    existing OHLC; it never changes their status or writes them back.
    """

    cal = calendar or default_calendar()
    as_of = parse_date(as_of_date)
    formal = performance
    if not isinstance(formal, Mapping) or not isinstance(formal.get("all_rows"), list):
        formal = build_strategy_rule_performance(
            canonical_watchlists,
            historical_ohlc,
            as_of,
            calendar=cal,
            historical_provenance=historical_provenance,
        )
    candidate_rows = _with_candidate_fields(canonical_watchlists, formal, as_of)
    diagnostics: list[dict[str, Any]] = []
    for raw_row in candidate_rows:
        if not _is_resolved(raw_row):
            continue
        entry_bar = _entry_day_bar(raw_row, historical_ohlc, as_of)
        trigger = _finite_number(raw_row.get("trigger"))
        target = _finite_number(raw_row.get("target"))
        high = _finite_number(entry_bar.get("high")) if entry_bar else None
        target_touched = high is not None and target is not None and high >= target
        entry_mfe = (high / trigger - 1.0) * 100.0 if high is not None and trigger else None
        session_index = _sellable_session_index(raw_row.get("entry_date"), raw_row.get("exit_date"), cal)
        is_stop = _is_stop(raw_row)
        diagnostics.append({
            "signal_date": raw_row.get("signal_date") or raw_row.get("date"),
            "code": raw_row.get("code"),
            "name": raw_row.get("name"),
            "status": raw_row.get("status"),
            "trigger_date": raw_row.get("trigger_date") or raw_row.get("entry_date"),
            "trigger": raw_row.get("trigger"),
            "target": raw_row.get("target"),
            "stop": raw_row.get("stop"),
            "entry_day_ohlc": entry_bar,
            "entry_day_high_return_pct": round(entry_mfe, 6) if entry_mfe is not None else None,
            "entry_day_mfe_pct": round(entry_mfe, 6) if entry_mfe is not None else None,
            "entry_day_target_touched": target_touched if entry_bar is not None else None,
            "entry_day_target_touch_status": "VERIFIED" if entry_bar is not None else "UNVERIFIED_MISSING_ENTRY_DAY_OHLC",
            "earliest_sellable_date": raw_row.get("sellable_from"),
            "formal_exit_date": raw_row.get("exit_date"),
            "formal_exit_type": raw_row.get("exit_reason"),
            "final_return_pct": raw_row.get("realized_return_pct"),
            "total_mfe_pct": raw_row.get("mfe_pct"),
            "total_mae_pct": raw_row.get("mae_pct"),
            "sellable_session_index": session_index,
            "fast_stop": bool(is_stop and session_index in (1, 2)),
            "classification": (
                "ENTRY_DAY_TARGET_TOUCHED_THEN_STOP"
                if is_stop and entry_bar is not None and target_touched
                else None
            ),
        })

    stop_rows = [row for row in diagnostics if row["formal_exit_type"] == EXIT_REASON_STOP]
    touched_rows = [
        row for row in stop_rows
        if row.get("entry_day_target_touched") is True
    ]
    fast_rows = [row for row in stop_rows if row.get("fast_stop")]
    intersection = [row for row in touched_rows if row.get("fast_stop")]
    special = next(
        (
            row for row in touched_rows
            if row.get("signal_date") == "2026-09-03" and row.get("code") == "300546"
        ),
        None,
    )
    return {
        "schema_version": "B_T1_GIVEBACK_RETROSPECTIVE_DIAGNOSTIC_V1",
        "status": "COMPLETE",
        "analysis_cutoff": as_of.isoformat(),
        "diagnostic_type": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
        "formal_performance_model_reused": True,
        "formal_outcomes_unchanged": True,
        "stop_count": len(stop_rows),
        "entry_day_target_touched_then_stop_count": len(touched_rows),
        "entry_day_target_touched_then_stop_rate_pct": round(len(touched_rows) / len(stop_rows) * 100.0, 6) if stop_rows else None,
        "fast_stop_count": len(fast_rows),
        "fast_stop_rate_pct": round(len(fast_rows) / len(stop_rows) * 100.0, 6) if stop_rows else None,
        "fast_stop_and_entry_day_target_touched_count": len(intersection),
        "categories_are_distinct": True,
        "entry_day_mfe_distribution_stop": _distribution(row.get("entry_day_mfe_pct") for row in stop_rows),
        "total_mfe_distribution_stop": _distribution(row.get("total_mfe_pct") for row in stop_rows),
        "total_mae_distribution_stop": _distribution(row.get("total_mae_pct") for row in stop_rows),
        "entry_day_target_touched_then_stop": touched_rows,
        "300546_verification": special or {
            "signal_date": "2026-09-03",
            "code": "300546",
            "status": "NOT_CONFIRMED_OR_UNAVAILABLE",
        },
        "rows": diagnostics,
    }


def build_repeat_exposure_summary(
    canonical_watchlists: Any,
    performance: Any = None,
    *,
    as_of_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Describe repeated ticker signal events without filtering them."""

    cutoff = parse_date(as_of_date) if as_of_date is not None else None
    events_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in _candidate_records(canonical_watchlists):
        signal_date = _normalise_date(candidate.get("date"))
        code = str(candidate.get("code", ""))
        if not signal_date or not code or (cutoff is not None and parse_date(signal_date) > cutoff):
            continue
        events_by_code[code].append({
            "signal_date": signal_date,
            "signal_id": candidate.get("signal_id"),
            "name": candidate.get("name"),
        })
    repeated = {
        code: sorted(events, key=lambda row: (row["signal_date"], str(row["signal_id"])))
        for code, events in events_by_code.items()
        if len(events) > 1
    }
    performance_by_id = {
        str(row.get("signal_id")): row
        for row in _performance_rows(performance)
        if row.get("signal_id")
    }
    repeated_ids = {
        str(event["signal_id"])
        for events in repeated.values()
        for event in events
    }
    repeated_rows = [
        row for signal_id, row in performance_by_id.items()
        if signal_id in repeated_ids and _is_resolved(row)
    ]
    return {
        "schema_version": "B_REPEAT_EXPOSURE_DESCRIPTIVE_DIAGNOSTIC_V1",
        "descriptive_only": True,
        "duplicate_signal_event_count": sum(len(events) - 1 for events in repeated.values()),
        "repeated_signal_event_count": sum(len(events) for events in repeated.values()),
        "unique_ticker_count": len(repeated),
        "repeated_stop_count": sum(_is_stop(row) for row in repeated_rows),
        "repeated_target_count": sum(_is_target(row) for row in repeated_rows),
        "repeated_events": repeated,
        "no_effect_on_canonical_selection": True,
    }


def build_research_diagnostics(
    canonical_watchlists: Any,
    historical_ohlc: Mapping[str, Any] | None,
    performance: Any,
    as_of_date: date | datetime | str,
    *,
    historical_provenance: Mapping[str, Any] | None = None,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Build the three bounded research summaries used by the research note."""

    return {
        "volume": build_retrospective_volume_summary(
            canonical_watchlists,
            performance,
            as_of_date,
            calendar=calendar,
        ),
        "t1": build_t1_giveback_diagnostic(
            canonical_watchlists,
            historical_ohlc,
            as_of_date,
            performance=performance,
            historical_provenance=historical_provenance,
            calendar=calendar,
        ),
        "repeat": build_repeat_exposure_summary(
            canonical_watchlists,
            performance,
            as_of_date=as_of_date,
        ),
    }
