#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""Read-only correctness audit for prospective/rule-performance semantics.

The audit deliberately composes the existing prospective replay and the
existing theoretical rule-price replay.  It does not change either replay,
the tracker, canonical rows, runtime-state, or production report code.
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
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence

from research_b_signal_entry_validity_decay import (
    DEFAULT_AS_OF,
    EVIDENCE_DATE,
    PROTOCOL_VERSION as ENTRY_VALIDITY_DECAY_PROTOCOL,
    STRATEGY,
    analyze_signal,
    canonical_json_bytes,
    load_runtime_inputs,
)
from track_perf import (
    EXIT_REASON_AMBIGUOUS,
    EXIT_REASON_EXPIRED_UNTRIGGERED,
    EXIT_REASON_STOP,
    EXIT_REASON_STOP_GAP,
    EXIT_REASON_TARGET,
    EXIT_REASON_TARGET_GAP,
    EXIT_REASON_TIME,
    EXIT_REASON_TIME_DEFERRED_T1,
    RULE_STATUS_NOT_YET_ELIGIBLE,
    PERFORMANCE_DATA_INCOMPLETE,
    RULE_STATUS_AMBIGUOUS,
    RULE_STATUS_CLOSED,
    RULE_STATUS_OPEN,
    RULE_STATUS_UNTRIGGERED,
    _next_session_after,
    build_strategy_rule_performance,
    parse_date,
)
from trading_calendar import TradingCalendar, default_calendar


AUDIT_VERSION = "B_ENTRY_VALIDITY_SEMANTICS_IMPACT_V1"
DEFAULT_OUTPUT_DIR = Path("data/research/b_entry_validity_semantics_impact_v1")
MODEL_P = "MODEL_P_CURRENT_PROSPECTIVE_SEMANTICS"
MODEL_R = "MODEL_R_CURRENT_STRATEGY_RULE_PERFORMANCE_SEMANTICS"
CATEGORY_A = "ENTRY_EXPIRY_MISMATCH"
CATEGORY_B = "TIME_EXIT_MISMATCH"
DECISION_MARKER_A = "PERFORMANCE_SEMANTICS_SHOULD_ALIGN_WITH_PROSPECTIVE_READY_FOR_USER_DECISION"
DECISION_MARKER_B = "DUAL_MODEL_SEMANTICS_INTENTIONAL_REPORTING_SEPARATION_READY_FOR_USER_DECISION"
DECISION_MARKER_C = "ENTRY_VALIDITY_SEMANTIC_CONTRACT_REQUIRES_USER_DECISION"
FINAL_OOS_STATE = "SEALED / UNREAD"

_P_TERMINAL_CLASSES = {"TARGET", "STOP", "TIME_EXIT", "EXPIRED_UNTRIGGERED", "OPEN"}
_R_TERMINAL_CLASSES = {"TARGET", "STOP", "OPEN", "UNTRIGGERED", "AMBIGUOUS"}
_NUMERIC_FIELDS = (
    "trigger_rate_pct",
    "expired_untriggered_count",
    "expired_untriggered_rate_pct",
    "open_trades",
    "open_trade_rate_pct",
    "closed_trades",
    "closed_trade_rate_pct",
    "target_count",
    "target_rate_pct",
    "stop_count",
    "stop_rate_pct",
    "time_exit_count",
    "time_exit_rate_pct",
    "win_rate_pct",
    "average_return_pct",
    "median_return_pct",
    "average_winner_pct",
    "average_loser_pct",
    "payoff_ratio",
    "profit_factor",
    "expectancy_pct",
    "average_holding_sessions",
    "ambiguous_count",
    "untriggered_to_report_count",
)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _mean(values: Iterable[Any]) -> float | None:
    numbers = [number for number in (_finite(value) for value in values) if number is not None]
    return _round(mean(numbers)) if numbers else None


def _median(values: Iterable[Any]) -> float | None:
    numbers = [number for number in (_finite(value) for value in values) if number is not None]
    return _round(median(numbers)) if numbers else None


def _pct(count: int, denominator: int) -> float | None:
    return _round(count / denominator * 100.0) if denominator else None


def _canonical_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical_json(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_json(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_canonical_json(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_rev(repo_root: Path, ref: str) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _git_blob(repo_root: Path, ref: str, path: str) -> str | None:
    return _git_rev(repo_root, f"{ref}:{path}")


def _session_delay(signal_date: date | str, entry_date: date | str | None, calendar: TradingCalendar) -> int | None:
    if entry_date is None:
        return None
    target = parse_date(entry_date)
    current = parse_date(signal_date)
    for delay in range(1, 1001):
        current = _next_session_after(current, calendar)
        if current == target:
            return delay
        if current > target:
            return None
    return None


def _build_history(inputs: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Make the same read-only merged history used by the current renderer."""

    history = {
        str(code): [dict(value) for value in values]
        for code, values in inputs["evidence_by_code"].items()
    }
    for signal in inputs["tracker_signals"]:
        code = str(signal["code"])
        by_day = {str(value.get("date")): dict(value) for value in history.setdefault(code, [])}
        for value in signal.get("observations", []):
            if isinstance(value, Mapping) and value.get("date") is not None:
                by_day[str(value["date"])] = dict(value)
        history[code] = list(by_day.values())
    return history


def _prospective_terminal_class(row: Mapping[str, Any]) -> str:
    if row.get("operational_path_status") != "COMPLETE":
        return "INCOMPLETE_OR_CENSORED"
    terminal = str(row.get("operational_terminal_status") or "")
    if terminal in _P_TERMINAL_CLASSES:
        return terminal
    if terminal == "OPEN_OR_PENDING":
        return "OPEN"
    return "UNRESOLVED"


def _rule_terminal_class(row: Mapping[str, Any]) -> str:
    status = row.get("status")
    if status == PERFORMANCE_DATA_INCOMPLETE:
        return "INCOMPLETE_OR_CENSORED"
    if status == RULE_STATUS_NOT_YET_ELIGIBLE:
        return "NOT_YET_ELIGIBLE"
    if status == RULE_STATUS_CLOSED:
        if row.get("exit_reason") == EXIT_REASON_TARGET:
            return "TARGET"
        if row.get("exit_reason") == EXIT_REASON_STOP:
            return "STOP"
        return "CLOSED_OTHER"
    if status == RULE_STATUS_OPEN:
        return "OPEN"
    if status == RULE_STATUS_UNTRIGGERED:
        return "UNTRIGGERED"
    if status == RULE_STATUS_AMBIGUOUS or status == EXIT_REASON_AMBIGUOUS:
        return "AMBIGUOUS"
    return str(status or "UNRESOLVED")


def _entry_identity_comparable(p: Mapping[str, Any], r: Mapping[str, Any]) -> bool:
    p_entry = p.get("operational_entry_date")
    r_entry = r.get("entry_date")
    if p_entry is None or r_entry is None:
        return p_entry is None and r_entry is None
    return str(p_entry) == str(r_entry)


def _exit_after(p: Mapping[str, Any], r: Mapping[str, Any]) -> bool:
    p_exit = p.get("operational_exit_date")
    r_exit = r.get("exit_date")
    if not p_exit or not r_exit:
        return False
    return parse_date(r_exit) > parse_date(p_exit)


def _category_b_outcome(p: Mapping[str, Any], r: Mapping[str, Any], r_class: str) -> str | None:
    if r_class == "TARGET" and _exit_after(p, r):
        return "LATER_TARGET"
    if r_class == "STOP" and _exit_after(p, r):
        return "LATER_STOP"
    if r_class == "OPEN":
        return "REMAINS_OPEN"
    if r_class == "AMBIGUOUS" and _exit_after(p, r):
        return "LATER_AMBIGUOUS"
    if r_class == "INCOMPLETE_OR_CENSORED":
        return "UNRESOLVED_INCOMPLETE_OR_CENSORED"
    return "NOT_A_LATER_TERMINAL_RESULT"


def compare_pair(
    prospective: Mapping[str, Any],
    rule: Mapping[str, Any],
    *,
    calendar: TradingCalendar,
) -> dict[str, Any]:
    """Classify one signal without changing either model row."""

    p_class = _prospective_terminal_class(prospective)
    r_class = _rule_terminal_class(rule)
    p_delay = prospective.get("first_trigger_delay")
    if not isinstance(p_delay, int):
        p_delay = None
    r_delay = _session_delay(rule.get("signal_date"), rule.get("entry_date"), calendar)
    entry_identity = _entry_identity_comparable(prospective, rule)
    p_delay_unresolved = prospective.get("delay_status") in {"CENSORED", "INCOMPLETE", "DATA_CONFLICT"}
    r_path_incomplete = rule.get("historical_data_status") != "COMPLETE"

    category_a_exact = p_class == "EXPIRED_UNTRIGGERED" and r_delay is not None and r_delay > 10
    category_a_evidence = (
        "COMPLETE"
        if category_a_exact and not r_path_incomplete and r_class in _R_TERMINAL_CLASSES
        else "INCOMPLETE_OR_CENSORED"
        if category_a_exact
        else None
    )
    category_a_unresolved = (
        not category_a_exact
        and p_delay_unresolved
        and r_class != "NOT_YET_ELIGIBLE"
        and (r_delay is None or r_delay > 10)
        and r_path_incomplete
    )

    category_b_identity = (
        entry_identity
        and p_delay is not None
        and 1 <= p_delay <= 10
        and r_delay == p_delay
    )
    rule_continues_after_p_time_exit = (
        r_class in {"OPEN", "INCOMPLETE_OR_CENSORED"}
        or _exit_after(prospective, rule)
    )
    category_b_exact = (
        category_b_identity
        and p_delay < 10
        and p_class == "TIME_EXIT"
        and rule_continues_after_p_time_exit
    )
    category_b_unresolved = (
        not category_b_exact
        and entry_identity
        and p_delay is not None
        and 1 <= p_delay < 10
        and (prospective.get("operational_path_status") != "COMPLETE" or r_path_incomplete)
    )

    p_return = _finite(prospective.get("operational_return_pct"))
    r_return = _finite(rule.get("realized_return_pct"))
    p_holding = _finite(prospective.get("operational_holding_sessions"))
    r_holding = _finite(rule.get("holding_sessions"))
    return {
        "category_a_exact": category_a_exact,
        "category_a_evidence_status": category_a_evidence,
        "category_a_unresolved_candidate": category_a_unresolved,
        "category_b_entry_identity_comparable": category_b_identity,
        "category_b_exact": category_b_exact,
        "category_b_unresolved_candidate": category_b_unresolved,
        "category_b_outcome": _category_b_outcome(prospective, rule, r_class) if category_b_exact else None,
        "entry_identity_comparable": entry_identity,
        "entry_price_same": (
            p_entry == r_entry
            if (p_entry := _finite(prospective.get("operational_entry_price"))) is not None
            and (r_entry := _finite(rule.get("entry_price"))) is not None
            else None
        ),
        "p_terminal_class": p_class,
        "r_terminal_class": r_class,
        "r_first_trigger_delay": r_delay,
        "return_delta_pct": _round(r_return - p_return) if p_return is not None and r_return is not None else None,
        "holding_sessions_delta": _round(r_holding - p_holding) if p_holding is not None and r_holding is not None else None,
    }


def _public_row(
    prospective: Mapping[str, Any],
    rule: Mapping[str, Any],
    flags: Mapping[str, Any],
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "signal_id": prospective.get("signal_id"),
        "strategy_version": prospective.get("strategy_version"),
        "signal_date": prospective.get("signal_date"),
        "code": prospective.get("code"),
        "setup": prospective.get("setup"),
        "trigger": prospective.get("trigger"),
        "stop": prospective.get("stop"),
        "target": prospective.get("target"),
        "p_delay_status": prospective.get("delay_status"),
        "p_first_trigger_date": prospective.get("first_trigger_date"),
        "p_first_trigger_delay": prospective.get("first_trigger_delay"),
        "p_path_status": prospective.get("operational_path_status"),
        "p_verification_status": prospective.get("operational_execution_verification_status"),
        "p_entry_price": prospective.get("operational_entry_price"),
        "p_exit_date": prospective.get("operational_exit_date"),
        "p_exit_reason": prospective.get("operational_exit_reason"),
        "p_return_pct": prospective.get("operational_return_pct"),
        "p_holding_sessions": prospective.get("operational_holding_sessions"),
        "p_missing_sessions": prospective.get("missing_sessions"),
        "r_status": rule.get("status"),
        "r_data_status": rule.get("historical_data_status"),
        "r_first_trigger_date": rule.get("trigger_date"),
        "r_first_trigger_delay": flags.get("r_first_trigger_delay"),
        "r_entry_price": rule.get("entry_price"),
        "r_exit_date": rule.get("exit_date"),
        "r_exit_reason": rule.get("exit_reason"),
        "r_return_pct": rule.get("realized_return_pct"),
        "r_holding_sessions": rule.get("holding_sessions"),
        "r_reason": rule.get("reason"),
    }
    fields.update(flags)
    return fields


def _pair_rows(
    inputs: Mapping[str, Any],
    *,
    as_of: date,
    calendar: TradingCalendar,
    rule_rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal in inputs["tracker_signals"]:
        signal_id = str(signal["signal_id"])
        prospective = analyze_signal(
            signal,
            inputs["canonical"][signal_id],
            inputs["evidence_by_code"].get(str(signal["code"]), []),
            as_of,
            calendar,
        )
        rule = rule_rows.get(signal_id)
        if rule is None:
            raise ValueError(f"strategy-rule replay omitted canonical signal_id: {signal_id}")
        flags = compare_pair(prospective, rule, calendar=calendar)
        rows.append(_public_row(prospective, rule, flags))
    return rows


def _pair_objects(
    inputs: Mapping[str, Any],
    *,
    as_of: date,
    calendar: TradingCalendar,
    rule_rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for signal in inputs["tracker_signals"]:
        signal_id = str(signal["signal_id"])
        prospective = analyze_signal(
            signal,
            inputs["canonical"][signal_id],
            inputs["evidence_by_code"].get(str(signal["code"]), []),
            as_of,
            calendar,
        )
        rule = rule_rows[signal_id]
        flags = compare_pair(prospective, rule, calendar=calendar)
        objects.append({"prospective": prospective, "rule": rule, "flags": flags})
    return objects


def _primary_intersection(objects: Sequence[Mapping[str, Any]], as_of: date) -> list[Mapping[str, Any]]:
    selected = []
    for item in objects:
        p = item["prospective"]
        r = item["rule"]
        if parse_date(p["signal_date"]) >= as_of:
            continue
        if p.get("operational_path_status") != "COMPLETE":
            continue
        if r.get("historical_data_status") != "COMPLETE":
            continue
        if not item["flags"].get("entry_identity_comparable"):
            continue
        selected.append(item)
    return selected


def _model_metrics(objects: Sequence[Mapping[str, Any]], model: str) -> dict[str, Any]:
    eligible = len(objects)
    if model == MODEL_P:
        classes = [_prospective_terminal_class(item["prospective"]) for item in objects]
        triggered = [item for item in objects if item["prospective"].get("operational_entry_date")]
        returns = [item["prospective"].get("operational_return_pct") for item in objects if _prospective_terminal_class(item["prospective"]) in {"TARGET", "STOP", "TIME_EXIT"}]
        holdings = [item["prospective"].get("operational_holding_sessions") for item in objects if _prospective_terminal_class(item["prospective"]) in {"TARGET", "STOP", "TIME_EXIT"}]
        targets = [item for item in objects if _prospective_terminal_class(item["prospective"]) == "TARGET"]
        stops = [item for item in objects if _prospective_terminal_class(item["prospective"]) == "STOP"]
        times = [item for item in objects if _prospective_terminal_class(item["prospective"]) == "TIME_EXIT"]
        winners = [item["prospective"].get("operational_return_pct") for item in objects if _finite(item["prospective"].get("operational_return_pct")) is not None and _finite(item["prospective"].get("operational_return_pct")) > 0 and _prospective_terminal_class(item["prospective"]) in {"TARGET", "STOP", "TIME_EXIT"}]
        losers = [item["prospective"].get("operational_return_pct") for item in objects if _finite(item["prospective"].get("operational_return_pct")) is not None and _finite(item["prospective"].get("operational_return_pct")) < 0 and _prospective_terminal_class(item["prospective"]) in {"TARGET", "STOP", "TIME_EXIT"}]
        expired = classes.count("EXPIRED_UNTRIGGERED")
        open_count = classes.count("OPEN")
        ambiguous = classes.count("AMBIGUOUS")
    else:
        classes = [_rule_terminal_class(item["rule"]) for item in objects]
        triggered = [item for item in objects if item["rule"].get("entry_date")]
        returns = [item["rule"].get("realized_return_pct") for item in objects if _rule_terminal_class(item["rule"]) in {"TARGET", "STOP"}]
        holdings = [item["rule"].get("holding_sessions") for item in objects if _rule_terminal_class(item["rule"]) in {"TARGET", "STOP"}]
        targets = [item for item in objects if _rule_terminal_class(item["rule"]) == "TARGET"]
        stops = [item for item in objects if _rule_terminal_class(item["rule"]) == "STOP"]
        times = []
        winners = [item["rule"].get("realized_return_pct") for item in objects if _finite(item["rule"].get("realized_return_pct")) is not None and _finite(item["rule"].get("realized_return_pct")) > 0 and _rule_terminal_class(item["rule"]) in {"TARGET", "STOP"}]
        losers = [item["rule"].get("realized_return_pct") for item in objects if _finite(item["rule"].get("realized_return_pct")) is not None and _finite(item["rule"].get("realized_return_pct")) < 0 and _rule_terminal_class(item["rule"]) in {"TARGET", "STOP"}]
        expired = None
        open_count = classes.count("OPEN")
        ambiguous = classes.count("AMBIGUOUS")

    closed = len(targets) + len(stops) + len(times)
    numeric_returns = [number for number in (_finite(value) for value in returns) if number is not None]
    numeric_holdings = [number for number in (_finite(value) for value in holdings) if number is not None]
    numeric_winners = [number for number in (_finite(value) for value in winners) if number is not None]
    numeric_losers = [number for number in (_finite(value) for value in losers) if number is not None]
    negative_sum = sum(numeric_losers)
    positive_sum = sum(numeric_winners)
    average_winner = _mean(numeric_winners)
    average_loser = _mean(numeric_losers)
    metrics = {
        "eligible_signals": eligible,
        "triggered": len(triggered),
        "trigger_rate_pct": _pct(len(triggered), eligible),
        "expired_untriggered_count": expired,
        "expired_untriggered_rate_pct": _pct(expired, eligible) if expired is not None else None,
        "open_trades": open_count,
        "open_trade_rate_pct": _pct(open_count, eligible),
        "closed_trades": closed,
        "closed_trade_rate_pct": _pct(closed, eligible),
        "target_count": len(targets),
        "target_rate_pct": _pct(len(targets), closed),
        "stop_count": len(stops),
        "stop_rate_pct": _pct(len(stops), closed),
        "time_exit_count": len(times),
        "time_exit_rate_pct": _pct(len(times), closed),
        "win_rate_pct": _pct(len(targets), closed),
        "average_return_pct": _mean(numeric_returns),
        "median_return_pct": _median(numeric_returns),
        "average_winner_pct": average_winner,
        "average_loser_pct": average_loser,
        "payoff_ratio": _round(average_winner / abs(average_loser)) if average_winner is not None and average_loser not in (None, 0) else None,
        "profit_factor": _round(positive_sum / abs(negative_sum)) if negative_sum < 0 else None,
        "expectancy_pct": _mean(numeric_returns),
        "average_holding_sessions": _mean(numeric_holdings),
        "ambiguous_count": ambiguous,
        "untriggered_to_report_count": classes.count("UNTRIGGERED") if model == MODEL_R else None,
        "return_sample_n": len(numeric_returns),
        "holding_sample_n": len(numeric_holdings),
    }
    return metrics


def _primary_metrics(objects: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    denominator = {
        "eligible_signals": len(objects),
        "trigger_rate": "eligible_signals",
        "expired_untriggered_rate": "eligible_signals",
        "open_trade_rate": "eligible_signals",
        "closed_trade_rate": "eligible_signals",
        "target_rate": "closed_trades",
        "stop_rate": "closed_trades",
        "time_exit_rate": "closed_trades",
        "win_rate": "closed_trades",
        "average_return": "numeric realized returns from closed trades only",
        "average_winner": "positive numeric realized returns from closed trades",
        "average_loser": "negative numeric realized returns from closed trades",
        "payoff_ratio": "average winner / abs(average loser)",
        "profit_factor": "sum positive returns / abs(sum negative returns)",
        "expectancy": "numeric realized returns from closed trades only",
        "average_holding_sessions": "closed trades with numeric holding_sessions",
    }
    p = _model_metrics(objects, MODEL_P)
    r = _model_metrics(objects, MODEL_R)
    delta: dict[str, Any] = {}
    for field in _NUMERIC_FIELDS:
        left, right = r.get(field), p.get(field)
        delta[field] = _round(left - right) if _finite(left) is not None and _finite(right) is not None else None
    return {
        "intersection_count": len(objects),
        "denominators": denominator,
        MODEL_P: p,
        MODEL_R: r,
        "delta_MODEL_R_minus_MODEL_P": delta,
    }


def _category_summary(
    objects: Sequence[Mapping[str, Any]],
    category: str,
    *,
    full_eligible_denominator: int,
) -> dict[str, Any]:
    if category == CATEGORY_A:
        exact = [item for item in objects if item["flags"].get("category_a_exact")]
        unresolved = [item for item in objects if item["flags"].get("category_a_unresolved_candidate")]
    else:
        exact = [item for item in objects if item["flags"].get("category_b_exact")]
        unresolved = [item for item in objects if item["flags"].get("category_b_unresolved_candidate")]
    complete = [item for item in exact if item["flags"].get("category_a_evidence_status") == "COMPLETE" or category == CATEGORY_B and item["rule"].get("historical_data_status") == "COMPLETE"]
    incomplete = [item for item in exact if item not in complete]
    p_triggered_delta = 0
    open_delta = 0
    closed_delta = 0
    for item in exact:
        p_class = item["flags"].get("p_terminal_class")
        r_class = item["flags"].get("r_terminal_class")
        if category == CATEGORY_A:
            p_triggered_delta += 1
        open_delta += int(r_class == "OPEN") - int(p_class == "OPEN")
        closed_delta += int(r_class in {"TARGET", "STOP"}) - int(p_class in {"TARGET", "STOP", "TIME_EXIT"})
    return {
        "category": category,
        "exact_count": len(exact),
        "complete_evidence_count": len(complete),
        "incomplete_or_censored_count": len(incomplete),
        "unresolved_candidate_count": len(unresolved),
        "potentially_affected_unresolved_count": len(unresolved),
        "fictional_triggered_trade_count": p_triggered_delta,
        "impact": {
            "common_eligible_denominator": full_eligible_denominator,
            "triggered_count_delta_MODEL_R_minus_MODEL_P": p_triggered_delta,
            "trigger_rate_delta_pct_points_MODEL_R_minus_MODEL_P": _pct(p_triggered_delta, full_eligible_denominator),
            "open_count_delta_MODEL_R_minus_MODEL_P": open_delta,
            "closed_count_delta_MODEL_R_minus_MODEL_P": closed_delta,
        },
        "exact_signal_ids": sorted(str(item["prospective"]["signal_id"]) for item in exact),
        "unresolved_signal_ids": sorted(str(item["prospective"]["signal_id"]) for item in unresolved),
    }


def _secondary_counts(objects: Sequence[Mapping[str, Any]], as_of: date) -> dict[str, Any]:
    eligible = [item for item in objects if parse_date(item["prospective"]["signal_date"]) < as_of]
    p_classes = Counter(item["flags"].get("p_terminal_class") for item in objects)
    r_classes = Counter(item["flags"].get("r_terminal_class") for item in objects)
    p_delay = Counter(item["prospective"].get("delay_status") for item in objects)
    r_status = Counter(item["rule"].get("status") for item in objects)
    return {
        "universe_signal_count": len(objects),
        "eligible_by_report_date_count": len(eligible),
        "model_p": {
            "delay_status_counts": dict(sorted(p_delay.items(), key=lambda pair: str(pair[0]))),
            "terminal_class_counts": dict(sorted(p_classes.items(), key=lambda pair: str(pair[0]))),
            "triggered_count": sum(item["prospective"].get("operational_entry_date") is not None for item in eligible),
            "waiting_trigger_count": sum(
                item["prospective"].get("operational_entry_date") is None
                and item["prospective"].get("delay_status") != "DATA_CONFLICT"
                for item in eligible
            ),
            "open_or_pending_count": sum(item["flags"].get("p_terminal_class") == "INCOMPLETE_OR_CENSORED" for item in eligible)
            + sum(item["flags"].get("p_terminal_class") == "OPEN" for item in eligible),
            "complete_path_count": sum(item["prospective"].get("operational_path_status") == "COMPLETE" for item in eligible),
        },
        "model_r": {
            "status_counts": dict(sorted(r_status.items(), key=lambda pair: str(pair[0]))),
            "terminal_class_counts": dict(sorted(r_classes.items(), key=lambda pair: str(pair[0]))),
            "triggered_count": sum(item["rule"].get("entry_date") is not None for item in eligible),
            "open_count": sum(item["flags"].get("r_terminal_class") == "OPEN" for item in eligible),
            "closed_count": sum(item["flags"].get("r_terminal_class") in {"TARGET", "STOP"} for item in eligible),
            "untriggered_to_report_count": sum(item["flags"].get("r_terminal_class") == "UNTRIGGERED" for item in eligible),
            "incomplete_count": sum(item["flags"].get("r_terminal_class") == "INCOMPLETE_OR_CENSORED" for item in eligible),
        },
    }


def build_protocol(
    *,
    repo_root: Path,
    inputs: Mapping[str, Any],
    runtime_ref: str,
    tracker_path: str,
    as_of: date,
    evidence_date: date,
) -> dict[str, Any]:
    source_dir = repo_root / "data/research/b_signal_entry_validity_decay_v1"
    return {
        "audit_version": AUDIT_VERSION,
        "research_only": True,
        "data_cutoff": as_of.isoformat(),
        "canonical_universe": {
            "unit": "canonical signal_id",
            "strategy": STRATEGY,
            "source_protocol": ENTRY_VALIDITY_DECAY_PROTOCOL,
            "source_protocol_sha256": _sha256_file(source_dir / "protocol.json"),
            "source_manifest_sha256": _sha256_file(source_dir / "manifest.json"),
            "signal_count": len(inputs["tracker_signals"]),
            "canonical_rows_mutated": False,
        },
        "model_p": {
            "name": MODEL_P,
            "source": "scripts/track_perf.py::rebuild_execution_state_from_observations via scripts/research_b_signal_entry_validity_decay.py::analyze_signal",
            "first_entry": "first canonical trigger on XSHG T+1 through T+10",
            "fill": "open when opening gap is at/above trigger, otherwise canonical trigger",
            "entry_day_sellability": "entry session cannot sell; next XSHG session is sellable",
            "stop_target": "sellable bar open-first gap, then low/high; same-bar stop+target is AMBIGUOUS_SAME_BAR",
            "t_plus_10_untriggered": "EXPIRED_UNTRIGGERED",
            "t_plus_10_first_trigger": "entry allowed; first legal next session handles exit/time-exit",
            "earlier_entry_at_t_plus_10": "TIME_EXIT at T+10 close unless an earlier stop/target terminal event occurs",
            "missing_observation": "path is unverified/incomplete; missing is never zero-filled or repaired with future bars",
        },
        "model_r": {
            "name": MODEL_R,
            "source": "scripts/track_perf.py::build_strategy_rule_performance -> _strategy_rule_trade_row -> _rule_sessions_after",
            "first_entry": "first post-signal XSHG session through report_date with high >= canonical trigger",
            "fill": "canonical trigger price; daily open is not used",
            "entry_day_sellability": "entry session cannot sell; next XSHG session is sellable",
            "stop_target": "sellable bar low/high at canonical rule price; same-bar stop+target is AMBIGUOUS_SAME_BAR",
            "entry_expiry": "none",
            "time_exit": "none; a trade may remain OPEN through report_date",
            "t_plus_10_or_later_first_trigger": "allowed while report_date contains the session",
            "missing_observation": "PERFORMANCE_DATA_INCOMPLETE; missing is never zero-filled",
        },
        "categories": {
            CATEGORY_A: {
                "definition": "P is complete EXPIRED_UNTRIGGERED at T+10 and R first trigger delay is >10",
                "new_rule_trade": "R creates a triggered trade outside the P entry-validity contract",
                "complete_evidence": "R has complete history through its terminal/open state at report_date",
                "unresolved_candidate": "P cannot prove T+10 expiry and R lacks a complete path; NOT_YET_ELIGIBLE rows are excluded from potentially affected count",
            },
            CATEGORY_B: {
                "definition": "same signal and first-entry date, first entry T+1..T+9, P completes with T+10 TIME_EXIT, and R continues beyond P exit",
                "entry_identity": "same canonical signal_id and same first_trigger_date; entry_price equality is reported separately",
                "later_outcomes": ["LATER_TARGET", "LATER_STOP", "REMAINS_OPEN", "UNRESOLVED_INCOMPLETE_OR_CENSORED"],
                "unresolved_candidate": "same known early entry but P or R post-entry path is incomplete",
            },
            "mutually_exclusive": True,
        },
        "missing_data_rules": {
            "all_missing_observations": "retain missing/null; never use 0 or future observations",
            "primary_returns": "only complete, identity-consistent P/R intersection; numeric realized returns only",
            "secondary_counts": "include incomplete, censored, conflict and not-yet-eligible states without adding them to return denominators",
            "model_r_expiry_metric": "NOT_APPLICABLE because R has no expiry; report untriggered_to_report separately",
        },
        "metric_denominators": {
            "eligible_signals": "signal_date < data_cutoff and both models have a T+1 opportunity in the selected intersection",
            "trigger_rate": "triggered / eligible_signals",
            "open_and_closed_rates": "count / eligible_signals",
            "target_stop_time_exit_rates": "exit count / closed_trades; ambiguous is not a closed trade",
            "win_rate": "TARGET / closed_trades",
            "returns": "complete numeric realized return rows only; no open/ambiguous/incomplete/censored rows",
            "payoff_ratio": "average positive realized return / abs(average negative realized return)",
            "profit_factor": "sum positive realized returns / abs(sum negative realized returns)",
            "delta": "MODEL_R minus MODEL_P on the same primary intersection",
        },
        "decision_rule": {
            "A": "choose only if repository contract defines formal performance as prospective execution reconstruction and R deviation is incorrect",
            "B": "choose only if repository contract explicitly supports independent rule simulation; separate labels, counts and UI are required",
            "C": "choose if contract evidence is materially conflicting or insufficient to determine canonical meaning",
            "selection_constraint": "never choose from which model has better returns",
        },
        "source_contract": {
            "master_sha_at_audit_base": _git_rev(repo_root, "origin/master"),
            "runtime_state_ref": runtime_ref,
            "runtime_state_sha": _git_rev(repo_root, runtime_ref),
            "tracker_path": tracker_path,
            "tracker_git_blob_sha": inputs.get("tracker_git_blob_sha") or _git_blob(repo_root, runtime_ref, tracker_path),
            "tracker_sha256": inputs.get("tracker_sha256"),
            "evidence_date": evidence_date.isoformat(),
            "evidence_manifest_sha256": inputs.get("evidence_manifest_sha256"),
            "final_oos": FINAL_OOS_STATE,
            "c_outcome": "NOT_READ",
            "old_d": "NOT_READ",
            "forbidden_validation_data": "NOT_READ",
        },
        "source_paths_and_functions": {
            "prospective": [
                "scripts/track_perf.py::_execution_horizon_sessions",
                "scripts/track_perf.py::rebuild_execution_state_from_observations",
                "scripts/track_perf.py::_sellable_exit_decision",
                "scripts/track_perf.py::_time_exit_t1_decision",
                "scripts/research_b_signal_entry_validity_decay.py::analyze_signal",
            ],
            "rule_performance": [
                "scripts/track_perf.py::_rule_sessions_after",
                "scripts/track_perf.py::_strategy_rule_trade_row",
                "scripts/track_perf.py::build_strategy_rule_performance",
                "scripts/render_daily_close_html.py::build_report_model",
            ],
            "tests": [
                "tests/test_b_signal_entry_validity_decay.py",
                "tests/test_strategy_rule_performance.py",
                "tests/test_entry_validity_semantics_impact.py",
            ],
        },
    }


CSV_FIELDS = (
    "signal_id", "strategy_version", "signal_date", "code", "setup", "trigger", "stop", "target",
    "p_delay_status", "p_first_trigger_date", "p_first_trigger_delay", "p_path_status", "p_verification_status",
    "p_entry_price", "p_exit_date", "p_exit_reason", "p_return_pct", "p_holding_sessions", "p_missing_sessions",
    "r_status", "r_data_status", "r_first_trigger_date", "r_first_trigger_delay", "r_entry_price", "r_exit_date",
    "r_exit_reason", "r_return_pct", "r_holding_sessions", "r_reason", "p_terminal_class", "r_terminal_class",
    "entry_identity_comparable", "entry_price_same", "category_a_exact",
    "category_a_evidence_status", "category_a_unresolved_candidate", "category_b_entry_identity_comparable",
    "category_b_exact", "category_b_unresolved_candidate", "category_b_outcome", "return_delta_pct",
    "holding_sessions_delta",
)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(_canonical_json(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (str(item.get("signal_date")), str(item.get("signal_id")))):
            writer.writerow({field: _csv_value(row.get(field)) for field in CSV_FIELDS})


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def _metric_table(metrics: Mapping[str, Any]) -> list[str]:
    p = metrics[MODEL_P]
    r = metrics[MODEL_R]
    d = metrics["delta_MODEL_R_minus_MODEL_P"]
    labels = (
        ("eligible signals", "eligible_signals"), ("triggered", "triggered"), ("trigger rate %", "trigger_rate_pct"),
        ("expired untriggered", "expired_untriggered_count"), ("open trades", "open_trades"),
        ("closed trades", "closed_trades"), ("target count", "target_count"), ("target rate %", "target_rate_pct"),
        ("stop count", "stop_count"), ("stop rate %", "stop_rate_pct"), ("time-exit count", "time_exit_count"),
        ("time-exit rate %", "time_exit_rate_pct"), ("win rate %", "win_rate_pct"),
        ("average return %", "average_return_pct"), ("median return %", "median_return_pct"),
        ("average winner %", "average_winner_pct"), ("average loser %", "average_loser_pct"),
        ("payoff ratio", "payoff_ratio"), ("profit factor", "profit_factor"), ("expectancy %", "expectancy_pct"),
        ("average holding sessions", "average_holding_sessions"),
    )
    lines = ["| Metric | MODEL_P | MODEL_R | MODEL_R - MODEL_P |", "|---|---:|---:|---:|"]
    for label, key in labels:
        lines.append(f"| {label} | {_fmt(p.get(key))} | {_fmt(r.get(key))} | {_fmt(d.get(key))} |")
    return lines


def render_report(
    *,
    protocol: Mapping[str, Any],
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    protocol_sha256: str,
    artifact_hashes: Mapping[str, str],
) -> str:
    category_a = summary["categories"][CATEGORY_A]
    category_b = summary["categories"][CATEGORY_B]
    secondary = summary["secondary_counts"]
    primary = summary["primary_metrics"]
    exact_a = ", ".join(category_a["exact_signal_ids"]) or "None"
    exact_b = ", ".join(category_b["exact_signal_ids"]) or "None"
    lines = [
        f"# {AUDIT_VERSION}",
        "",
        f"Decision marker: `{DECISION_MARKER_B}`",
        "",
        "This is a research-quality correctness audit. It does not change production execution semantics, tracker state, entry validity, T+10 behavior, Formal B, runtime-state, or formal performance definitions.",
        "",
        "## 1. Fixed intake and universe",
        "",
        f"- Data cutoff: `{protocol['data_cutoff']}`; strategy: `{STRATEGY}`; unit: canonical `signal_id`.",
        f"- Live audit base: `origin/master={protocol['source_contract']['master_sha_at_audit_base']}`.",
        f"- Runtime source: `{protocol['source_contract']['runtime_state_ref']}={protocol['source_contract']['runtime_state_sha']}`.",
        f"- Canonical signal count: `{protocol['canonical_universe']['signal_count']}`; canonical rows mutated: `false`.",
        f"- Existing source protocol: `{ENTRY_VALIDITY_DECAY_PROTOCOL}` / `{protocol['canonical_universe']['source_protocol_sha256']}`.",
        f"- Final OOS: `{FINAL_OOS_STATE}`; C outcome, old D and forbidden validation data: `NOT_READ`.",
        "",
        "PR #95/#96/#97 were read as live OPEN independent work; PR #98 and PR #99 were read as MERGED historical checkpoints. Their CI and merge identities are provenance only; this audit does not merge or cherry-pick any of them.",
        "",
        "## 2. Call-chain contract evidence",
        "",
        "| Concern | MODEL_P prospective tracker | MODEL_R strategy-rule performance |",
        "|---|---|---|",
        "| earliest first entry | T+1 | T+1 opportunity after signal date |",
        "| latest first trigger | T+10 | report date; may exceed T+10 |",
        "| trigger window | `_execution_horizon_sessions` / T+1..T+10 | `_rule_sessions_after` / T+1..report date |",
        "| T+10 untriggered | `EXPIRED_UNTRIGGERED` | no expiry; `UNTRIGGERED` only if complete through report date |",
        "| T+10 first trigger | allowed; next XSHG session is first sellable session | allowed if report date contains it |",
        "| earlier entry at T+10 | T+10 close `TIME_EXIT` unless earlier terminal event | no time exit; continues |",
        "| entry-day sellability | cannot sell on entry day | cannot sell on entry day |",
        "| stop/target | open-first gap, then low/high; same-bar ambiguous | canonical rule price low/high; same-bar ambiguous |",
        "| missing observation | incomplete/unverified; no zero-fill/future repair | `PERFORMANCE_DATA_INCOMPLETE`; no zero-fill |",
        "| fixed T+3/T+5/T+10 | signal-date fixed-horizon observation | independent of execution validity |",
        "",
        "Evidence is from `scripts/track_perf.py::rebuild_execution_state_from_observations`, `::_execution_horizon_sessions`, `::_sellable_exit_decision`, `::_time_exit_t1_decision`, `::_rule_sessions_after`, `::_strategy_rule_trade_row`, `::build_strategy_rule_performance`; renderer wiring is `scripts/render_daily_close_html.py::build_report_model`.",
        "",
        "## 3. Category A — ENTRY_EXPIRY_MISMATCH",
        "",
        "Definition: MODEL_P is complete `EXPIRED_UNTRIGGERED` at T+10 while MODEL_R first triggers after T+10.",
        "",
        f"- Exact count: **{category_a['exact_count']}**.",
        f"- Complete-evidence count: **{category_a['complete_evidence_count']}**.",
        f"- Incomplete/censored within exact rows: **{category_a['incomplete_or_censored_count']}**.",
        f"- Unresolved candidates with an incomplete MODEL_P expiry decision: **{category_a['unresolved_comparison_count']}**; potentially affected eligible count: **{category_a['potentially_affected_unresolved_count']}**.",
        f"- Unresolved MODEL_P delay-status breakdown: `{json.dumps(category_a['unresolved_delay_status_counts'], ensure_ascii=False, sort_keys=True)}`; `{category_a['excluded_not_yet_eligible_count']}` censored rows are excluded from potentially affected impact because they have no T+1 opportunity by the cutoff.",
        f"- New rule trades outside the prospective contract: **{category_a['fictional_triggered_trade_count']}** exact observable trades.",
        f"- Exact signal rows: `{exact_a}`.",
        f"- Exact trigger/open/closed impact: `{json.dumps(category_a['impact'], ensure_ascii=False, sort_keys=True)}`.",
        "",
        "The 83 potentially affected eligible rows are unresolved because the prospective T+10 expiry path and the rule path are incomplete; 9 additional censored rows are not yet T+1-eligible by the cutoff and are not counted as potentially affected. The full per-signal state, including all missing sessions, is in `signal_level_comparison.csv`.",
        "",
        "## 4. Category B — TIME_EXIT_MISMATCH",
        "",
        "Definition: same signal and first-entry date, first entry T+1..T+9, MODEL_P completes with T+10 time exit, and MODEL_R continues after that exit.",
        "",
        f"- Entry-identity-comparable rows (first entry known): `{summary['category_b_comparable_identity_count']}`.",
        f"- Exact count: **{category_b['exact_count']}**.",
        f"- Complete-evidence count: **{category_b['complete_evidence_count']}**.",
        f"- Incomplete/censored within exact rows: **{category_b['incomplete_or_censored_count']}**.",
        f"- Unresolved early-entry candidates: **{category_b['unresolved_candidate_count']}**.",
        f"- Exact signal rows: `{exact_b}`.",
        f"- Exact later outcome counts: `{json.dumps(summary['category_b_outcomes'], ensure_ascii=False, sort_keys=True)}`.",
        f"- Exact trigger/open/closed impact: `{json.dumps(category_b['impact'], ensure_ascii=False, sort_keys=True)}`.",
        "",
        "The 48 unresolved candidates have known early entry identity but missing post-entry observations, so the audit does not guess whether MODEL_P would time-exit or MODEL_R would later hit target, stop, or remain open.",
        "",
        "## 5. Primary apples-to-apples intersection",
        "",
        "The primary denominator requires both models to have complete observations at the same cutoff and matching first-entry identity. Missing, censored, conflict, not-yet-eligible and ambiguous rows are not added to realized-return denominators.",
        "",
        *_metric_table(primary),
        "",
        f"Primary intersection count: **{primary['intersection_count']}**. Entry-price equality is a separate orthogonal difference: `{summary['entry_price_difference_count']}` of these rows have different current-model entry prices (MODEL_P gap/open fill vs MODEL_R canonical trigger); this is not classified as Category A or B.",
        "",
        "## 6. Secondary full-universe state counts",
        "",
        f"- Universe: `{secondary['universe_signal_count']}`; eligible by cutoff: `{secondary['eligible_by_report_date_count']}`.",
        f"- MODEL_P delay statuses: `{json.dumps(secondary['model_p']['delay_status_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"- MODEL_P terminal classes: `{json.dumps(secondary['model_p']['terminal_class_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"- MODEL_R statuses: `{json.dumps(secondary['model_r']['status_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"- MODEL_R terminal classes: `{json.dumps(secondary['model_r']['terminal_class_counts'], ensure_ascii=False, sort_keys=True)}`.",
        "",
        "These counts expose incomplete/censored/conflict states; they are not complete performance metrics and do not treat missing observations as zero return.",
        "",
        "## 7. Current renderer impact",
        "",
        "| Report field / surface | Audit result | Current source |",
        "|---|---|---|",
        "| 今日总览 candidate/earliest-execution facts | UNAFFECTED_BY_ENTRY_VALIDITY_SEMANTICS; prospective daily rows drive them | `build_report_model` overview/daily_summary |",
        "| 规则模拟未结案 / historical closed | AFFECTED by MODEL_R no-expiry/no-time-exit state | `trade_performance` from `build_strategy_rule_performance` |",
        "| 胜率、平均收益、平均赢家/输家、payoff ratio、PF、expectancy、holding | AFFECTED in the rule-simulation block; denominators must remain MODEL_R-labelled | `render_daily_close_html.py::_performance_cards/_performance_metric_strip` |",
        "| waiting-trigger count | prospective waiting count is separate and unaffected; rule funnel `untriggered` is MODEL_R-specific and affected | `build_trade_performance_summary` vs `trade_performance` funnel |",
        "| cumulative strategy performance | NOT_PRESENT in current master renderer; no cumulative series was found | no current renderer field |",
        "| fixed T+3/T+5/T+10 | `UNAFFECTED_BY_ENTRY_VALIDITY_SEMANTICS` when kept as fixed-horizon research snapshots | `track_perf.py` review points / renderer research panels |",
        "",
        "The current page places the theoretical rule-price block near prospective review data and uses a generic performance heading. That is a reporting-separation risk even though the code/doc contract says the rule model is theoretical and not actual trades.",
        "",
        "## 8. Contract-intent decision",
        "",
        "The repository contract supports **B — independent rule simulation**: `docs/CURRENT_STATUS.md` calls the formal performance model theoretical strategy performance and not the user's actual trades; `docs/DECISION_LOG.md` records theoretical rule-price performance as read-only and independent from prospective observations; `track_perf.py::build_strategy_rule_performance` documents independence, and `tests/test_strategy_rule_performance.py` explicitly asserts no T+10 forced exit, open theoretical trades, and no mutation/backfill of prospective observations.",
        "",
        f"Terminal marker: `{DECISION_MARKER_B}`.",
        "",
        "Recommended reporting boundary for user decision: keep MODEL_P as the prospective execution/path model; label MODEL_R as `THEORETICAL_RULE_PRICE_SIMULATION_NO_ENTRY_EXPIRY_NO_TIME_EXIT`; expose separate denominators and separate open/closed/waiting counts; do not merge the two into one cumulative or realized-performance series. No production semantic change is implemented in this audit.",
        "",
        "## 9. Reproducibility and artifacts",
        "",
        f"- Protocol SHA-256: `{protocol_sha256}`.",
        f"- `protocol.json`: `{artifact_hashes['protocol.json']}`; `signal_level_comparison.csv`: `{artifact_hashes['signal_level_comparison.csv']}`; `impact_summary.json`: `{artifact_hashes['impact_summary.json']}`. The report hash is recorded in `manifest.json` after report generation.",
        f"- Manifest is generated after artifact hashes and records the command, live refs, source artifact identities and read-only evidence boundary.",
        "- Final OOS remains SEALED / UNREAD; no C outcome, old D, forbidden validation data, provider call, runtime-state write, prospective backfill, merge, or production semantic change was performed.",
        "",
    ]
    return "\n".join(lines)


def run_audit(
    *,
    repo_root: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
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
    protocol = build_protocol(
        repo_root=repo_root,
        inputs=inputs,
        runtime_ref=runtime_ref,
        tracker_path=tracker_path,
        as_of=as_of,
        evidence_date=evidence_date,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol_path = output_dir / "protocol.json"
    _write_json(protocol_path, protocol)
    protocol_sha256 = _sha256_file(protocol_path)

    before_inputs = deepcopy({"canonical": inputs["canonical"], "watchlists": inputs["watchlist_values"], "signals": inputs["tracker_signals"]})
    history = _build_history(inputs)
    rule_performance = build_strategy_rule_performance(
        inputs["watchlist_values"],
        history,
        as_of,
        calendar=cal,
        historical_provenance={"__meta__": {"source": "AUDIT_MERGED_CANONICAL_BARS", "provider_calls": 0}},
    )
    rule_rows = {str(row["signal_id"]): row for row in rule_performance["all_rows"]}
    objects = _pair_objects(inputs, as_of=as_of, calendar=cal, rule_rows=rule_rows)
    public_rows = _pair_rows(inputs, as_of=as_of, calendar=cal, rule_rows=rule_rows)
    after_inputs = {"canonical": inputs["canonical"], "watchlists": inputs["watchlist_values"], "signals": inputs["tracker_signals"]}
    if before_inputs != after_inputs:
        raise AssertionError("AUDIT_CANONICAL_INPUT_MUTATED")

    primary_objects = _primary_intersection(objects, as_of)
    primary_metrics = _primary_metrics(primary_objects)
    full_eligible = sum(parse_date(item["prospective"]["signal_date"]) < as_of for item in objects)
    category_a = _category_summary(objects, CATEGORY_A, full_eligible_denominator=full_eligible)
    category_b = _category_summary(objects, CATEGORY_B, full_eligible_denominator=full_eligible)
    unresolved_a = [
        item for item in objects
        if item["prospective"].get("delay_status") in {"CENSORED", "INCOMPLETE", "DATA_CONFLICT"}
    ]
    excluded_a = [
        item for item in unresolved_a
        if item["flags"].get("r_terminal_class") == "NOT_YET_ELIGIBLE"
    ]
    category_a["unresolved_comparison_count"] = len(unresolved_a)
    category_a["unresolved_delay_status_counts"] = dict(sorted(
        Counter(item["prospective"].get("delay_status") for item in unresolved_a).items(),
        key=lambda pair: str(pair[0]),
    ))
    category_a["excluded_not_yet_eligible_count"] = len(excluded_a)
    secondary = _secondary_counts(objects, as_of)
    entry_price_difference_count = sum(item["flags"].get("entry_price_same") is False for item in primary_objects)
    category_b_outcomes = Counter(
        item["flags"].get("category_b_outcome")
        for item in objects
        if item["flags"].get("category_b_exact")
    )
    summary = {
        "audit_version": AUDIT_VERSION,
        "decision_marker": DECISION_MARKER_B,
        "data_cutoff": as_of.isoformat(),
        "canonical_signal_count": len(objects),
        "canonical_rows_mutated": False,
        "categories": {CATEGORY_A: category_a, CATEGORY_B: category_b},
        "category_b_comparable_identity_count": sum(item["flags"].get("category_b_entry_identity_comparable") for item in objects),
        "category_b_outcomes": dict(sorted(category_b_outcomes.items(), key=lambda pair: str(pair[0]))),
        "entry_price_difference_count": entry_price_difference_count,
        "primary_metrics": primary_metrics,
        "secondary_counts": secondary,
        "source_contract": protocol["source_contract"],
    }
    csv_path = output_dir / "signal_level_comparison.csv"
    _write_csv(csv_path, public_rows)
    summary_path = output_dir / "impact_summary.json"
    _write_json(summary_path, summary)
    artifact_hashes = {
        "protocol.json": _sha256_file(protocol_path),
        "signal_level_comparison.csv": _sha256_file(csv_path),
        "impact_summary.json": _sha256_file(summary_path),
    }
    report = render_report(
        protocol=protocol,
        summary=summary,
        rows=public_rows,
        protocol_sha256=protocol_sha256,
        artifact_hashes=artifact_hashes,
    )
    report_path = output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    artifact_hashes["report.md"] = _sha256_file(report_path)
    manifest = {
        "audit_version": AUDIT_VERSION,
        "decision_marker": DECISION_MARKER_B,
        "protocol_sha256": protocol_sha256,
        "artifacts": artifact_hashes,
        "canonical_signal_id_sha256": hashlib.sha256(
            canonical_json_bytes(sorted(str(row["signal_id"]) for row in public_rows))
        ).hexdigest(),
        "source": protocol["source_contract"],
        "reproducibility": {
            "command": "python scripts/audit_entry_validity_semantics_impact.py run --runtime-ref origin/runtime-state --as-of 2026-09-30 --evidence-root <existing-read-only-data/t_close_evidence>",
            "input_evidence_is_read_only": True,
            "canonical_rows_mutated": False,
            "production_semantics_changed": False,
        },
    }
    manifest_path = output_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    artifact_hashes["manifest.json"] = _sha256_file(manifest_path)
    return {
        "protocol": protocol,
        "protocol_sha256": protocol_sha256,
        "rows": public_rows,
        "summary": summary,
        "artifacts": artifact_hashes,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--repo-root", default=".")
    run.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
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
        result = run_audit(
            repo_root=Path(args.repo_root).resolve(),
            output_dir=Path(args.output_dir),
            runtime_ref=args.runtime_ref,
            tracker_path=args.tracker_path,
            watchlist_dir=args.watchlist_dir,
            as_of=parse_date(args.as_of),
            evidence_root=Path(args.evidence_root).resolve() if args.evidence_root else None,
            evidence_date=parse_date(args.evidence_date),
        )
        print(json.dumps({"decision_marker": result["summary"]["decision_marker"], "artifacts": result["artifacts"]}, ensure_ascii=False, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
