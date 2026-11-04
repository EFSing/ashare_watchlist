"""Recording-only diagnostics from the exact, already-consumed same-day C input.

Runs after C publication in a separate, optional fail-soft workflow step. This
module neither supplies inputs to C nor changes its rule results. Undefined
downstream features stay null. Candidate-pair diagnostics are not stock-level
qualification, a score, sensitivity analysis, or evidence about outcomes.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

import c_pre_outcome_design as frozen
from c_b_input_adapter import _b_kline_sha
from c_prospective_capture import _safe_output_root
from c_state_store import _copy_missing
from cloud_runtime_state import validate_state_tree
from trading_calendar import default_calendar
from universe_policy import classify_board


VERSION = "C_PROSPECTIVE_RULE_FUNNEL_CAPTURE_V1"
RELATIVE_ROOT = Path("data/research/c_rule_funnel_capture_v1")
RULES = ("BALANCED_A", "CONSERVATIVE_B")
TREND_CONDITIONS = ("close_above_fast_average", "ma_order_ok", "positive_slope", "up_close_fraction_ok")
CONFIRMATION_CONDITIONS = ("close_above_rebound_high", "close_above_previous_close", "positive_body", "close_location_ok")
MAX_DETAIL_BYTES = 64_000_000  # compressed; at most 20 dates, never on master
MAX_SUMMARY_BYTES = 100_000
_BJT = timezone(timedelta(hours=8))


def canonical(value: Any) -> bytes:
    return (frozen.canonical_json(value) + "\n").encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _all_known(values: Sequence[Any]) -> bool:
    return all(isinstance(value, bool) for value in values)


def _confirmation(bars: Sequence[Mapping[str, Any]], structure: Mapping[str, Any], config: Any) -> dict[str, Any]:
    result = frozen._rebound_confirmation(bars, structure, config)
    failed = [key for key in CONFIRMATION_CONDITIONS if result.get(key) is False]
    result.update({"threshold": config.confirmation_close_location,
                   "close_location_margin": result["close_location"] - config.confirmation_close_location,
                   "confirmation_fail_count": len(failed), "failed_subconditions": failed})
    return result


def _pair_contexts(bars: Sequence[Mapping[str, Any]], config: Any) -> tuple[list[int], list[int], list[dict[str, Any]]]:
    """Frozen enumeration order; retain ALL tried pairs, stopping at its selection.

    Age/depth/rebound are decomposed even when an earlier predicate fails. No
    threshold is changed and no alternative stock list is calculated. Pivots
    are confirmed using T-1, exactly as in the frozen implementation.
    """
    t = len(bars) - 1
    lows, highs = [row["low"] for row in bars], [row["high"] for row in bars]
    low_pivots = frozen._pivot_indices(lows[:t], config.pivot_radius, low=True)
    high_pivots = frozen._pivot_indices(highs[:t], config.pivot_radius, low=False)
    contexts = []
    support_cache, confirmation_cache, peak_cache, rebound_cache = {}, {}, {}, {}
    for position in range(len(low_pivots) - 1, -1, -1):
        low2 = low_pivots[position]
        for low1 in reversed(low_pivots[:position]):
            if low2 - low1 < config.minimum_pivot_separation or lows[low2] <= lows[low1]:
                continue
            if low1 not in peak_cache:
                peaks = [index for index in high_pivots if index < low1]
                peak = peaks[-1] if peaks else None
                peak_cache[low1] = (peak, t - peak if peak is not None else None,
                                   (highs[peak] - min(lows[peak + 1:t])) / highs[peak] if peak is not None else None)
            peak, age, depth = peak_cache[low1]
            age_limit = config.maximum_pullback_sessions + config.pivot_radius * 2
            if low2 not in rebound_cache:
                rebound = frozen._latest_rebound_high(highs, high_pivots, low2, t)
                rebound_cache[low2] = (rebound, (highs[rebound] - lows[low2]) / lows[low2] if rebound is not None else None)
            rebound, size = rebound_cache[low2]
            gates = {
                "pre_pullback_peak_available": peak is not None,
                "peak_age_ok": age <= age_limit if age is not None else None,
                "depth_ok": config.shallow_depth_min <= depth <= config.shallow_depth_max if depth is not None else None,
                "rebound_high_available": rebound is not None,
                "rebound_size_ok": config.rebound_size_min <= size <= config.rebound_size_max if size is not None else None,
            }
            structure = {"support_floor": lows[low1], "support_ceiling": lows[low2],
                         "pullback_start_index": peak + 1 if peak is not None else None,
                         "pullback_end_exclusive": t, "rebound_high": highs[rebound] if rebound is not None else None}
            if rebound is not None and rebound not in confirmation_cache:
                confirmation_cache[rebound] = _confirmation(bars, structure, config)
            if peak is not None and low1 not in support_cache:
                support_cache[low1] = frozen._support_observation(bars, structure, config)
            confirmation = confirmation_cache.get(rebound)
            support = {**support_cache[low1], "support_ceiling": lows[low2]} if low1 in support_cache else None
            selected = all(value is True for value in gates.values())
            context = {
                "low1_index": low1, "low2_index": low2, "low1": lows[low1], "low2": lows[low2],
                "separation": low2 - low1, "minimum_separation": config.minimum_pivot_separation,
                "peak_index": peak, "peak_high": highs[peak] if peak is not None else None,
                "peak_age": age, "peak_age_limit": age_limit,
                "peak_age_failed": not gates["peak_age_ok"] if age is not None else None,
                "depth": depth, "depth_min": config.shallow_depth_min, "depth_max": config.shallow_depth_max,
                "depth_lower_margin": depth - config.shallow_depth_min if depth is not None else None,
                "depth_upper_margin": config.shallow_depth_max - depth if depth is not None else None,
                "depth_failed": not gates["depth_ok"] if depth is not None else None,
                "pullback_sessions": t - peak - 1 if peak is not None else None,
                "rebound_high_index": rebound, "rebound_high": highs[rebound] if rebound is not None else None,
                "rebound_size": size, "rebound_size_min": config.rebound_size_min,
                "rebound_size_max": config.rebound_size_max,
                "rebound_lower_margin": size - config.rebound_size_min if size is not None else None,
                "rebound_upper_margin": config.rebound_size_max - size if size is not None else None,
                "rebound_status": ("NO_CONFIRMED_REBOUND_HIGH" if rebound is None else
                                   "OK" if gates["rebound_size_ok"] else "REBOUND_SIZE_OUTSIDE_CANDIDATE"),
                "gates": gates, "confirmation": confirmation, "support": support,
                "selected_by_current_structure_rule": selected,
            }
            contexts.append(context)
            if selected:
                return low_pivots, high_pivots, contexts
    return low_pivots, high_pivots, contexts


def iter_pair_diagnostics(row: Mapping[str, Any]):
    """Lossless expansion of compact pair references; no OHLCV is required."""
    for low1, low2 in row["candidate_pairs"]:
        first, second = row["first_low_contexts"][str(low1)], row["second_low_contexts"][str(low2)]
        gates = {**first["gates"], **second["gates"]}
        support = {**first["support"], "support_ceiling": second["low2"]} if first["support"] else None
        conditions = {**{k: row["F2"].get(k) for k in TREND_CONDITIONS}, **gates,
                      **{k: (second["confirmation"] or {}).get(k) for k in CONFIRMATION_CONDITIONS},
                      "entry_support_ok": (support or {}).get("entry_support_ok")}
        failed = [k for k, value in conditions.items() if value is False]
        yield {**first, **second, "support": support, "gates": gates, "separation": low2 - low1,
               "minimum_separation": row["F3"]["minimum_separation"],
               "selected_by_current_structure_rule": all(value is True for value in gates.values()),
               "failed_conditions": failed, "missing_conditions": [k for k, value in conditions.items() if value is None],
               "failed_condition_count": len(failed) if _all_known(list(conditions.values())) else None}


def diagnose(bars: Sequence[Mapping[str, Any]], original: Mapping[str, Any], rule_id: str) -> dict[str, Any]:
    """Preserve canonical observations; supplement their diagnostic omissions."""
    config = frozen.RULE_CANDIDATES[rule_id]
    observed = original.get("price_structure_observation") or {}
    trend = dict(observed.get("trend") or {})
    structure = observed.get("structure") or {}
    trend.update({"minimum_up_close_fraction": config.minimum_up_close_fraction,
                  "up_close_fraction_margin": (trend["up_close_fraction"] - config.minimum_up_close_fraction
                                               if trend.get("up_close_fraction") is not None else None)})
    for key in TREND_CONDITIONS + ("trend_qualified", "up_close_fraction", "log_close_slope_per_session"):
        trend.setdefault(key, None)
    low_pivots, high_pivots, contexts = _pair_contexts(bars, config)
    selected = next((row for row in contexts if row["selected_by_current_structure_rule"]), None)
    # A drift/missing canonical result is a missing diagnostic, never a repaired C result.
    if structure.get("status") != "INSUFFICIENT_HISTORY":
        derived = ("OK" if selected else "NO_DISTINCT_HIGHER_LOW_PAIR" if not contexts else
                   "NO_PRE_PULLBACK_PEAK" if not any(c["gates"]["pre_pullback_peak_available"] for c in contexts) else
                   "PULLBACK_DEPTH_OUTSIDE_CANDIDATE" if not any(
                       c["gates"]["peak_age_ok"] is True and c["gates"]["depth_ok"] is True for c in contexts) else
                   "NO_CONFIRMED_REBOUND_HIGH")
        if derived != structure.get("status"):
            raise ValueError("DIAGNOSTIC_STRUCTURE_PARITY_MISMATCH")
        if selected and (selected["low1_index"], selected["low2_index"], selected["peak_index"], selected["rebound_high_index"]) != (
                structure.get("low_one_index"), structure.get("low_two_index"),
                structure.get("peak_index"), structure.get("rebound_high_index")):
            raise ValueError("DIAGNOSTIC_SELECTED_PAIR_PARITY_MISMATCH")
    confirmation = selected["confirmation"] if selected else None
    support = selected["support"] if selected else None
    if observed.get("confirmation") and any(observed["confirmation"].get(key) != confirmation.get(key)
                                            for key in CONFIRMATION_CONDITIONS + ("confirmation_qualified",)):
        raise ValueError("DIAGNOSTIC_CONFIRMATION_PARITY_MISMATCH")
    if observed.get("support") and observed["support"].get("entry_support_ok") != support.get("entry_support_ok"):
        raise ValueError("DIAGNOSTIC_SUPPORT_PARITY_MISMATCH")
    final = original.get("price_structure_match")
    expected = (trend.get("trend_qualified") is True and selected is not None
                and confirmation["confirmation_qualified"] and support["entry_support_ok"])
    if isinstance(final, bool) and final != expected:
        raise ValueError("DIAGNOSTIC_FINAL_PARITY_MISMATCH")
    if confirmation is None:
        current, previous = bars[-1], bars[-2]
        location = frozen._bar_geometry(current, previous["close"])["close_location"]
        confirmation = {"close_above_rebound_high": None,
                        "close_above_previous_close": current["close"] > previous["close"],
                        "positive_body": current["close"] > current["open"],
                        "close_location": location, "close_location_ok": location >= config.confirmation_close_location,
                        "threshold": config.confirmation_close_location,
                        "close_location_margin": location - config.confirmation_close_location,
                        "confirmation_qualified": None, "confirmation_fail_count": None}
        confirmation["failed_subconditions"] = [k for k in CONFIRMATION_CONDITIONS if confirmation.get(k) is False]
        confirmation["known_confirmation_fail_count"] = len(confirmation["failed_subconditions"])
    near_contexts = [selected] if selected else contexts
    for context in contexts:
        conditions = {**{key: trend.get(key) for key in TREND_CONDITIONS}, **context["gates"],
                      **{key: (context["confirmation"] or {}).get(key) for key in CONFIRMATION_CONDITIONS},
                      "entry_support_ok": (context["support"] or {}).get("entry_support_ok")}
        context["failed_conditions"] = [key for key, value in conditions.items() if value is False]
        context["missing_conditions"] = [key for key, value in conditions.items() if value is None]
        context["failed_condition_count"] = len(context["failed_conditions"]) if _all_known(list(conditions.values())) else None
    counts = [row["failed_condition_count"] for row in near_contexts if row["failed_condition_count"] is not None]
    near_classes = set()
    if final is False:
        for context in near_contexts:
            if context["failed_condition_count"] == 1:
                failed = context["failed_conditions"][0]
                label = ("ONE_TREND_SUBCONDITION" if failed in TREND_CONDITIONS else
                         "ONE_CONFIRMATION_SUBCONDITION" if failed in CONFIRMATION_CONDITIONS else
                         {"depth_ok": "DEPTH_ONLY", "peak_age_ok": "PEAK_AGE_ONLY",
                          "rebound_size_ok": "REBOUND_SIZE_ONLY", "entry_support_ok": "SUPPORT_ONLY"}.get(failed))
                if label:
                    near_classes.add(label)
    # First-low features (peak/depth/support) and second-low features (rebound/
    # confirmation) do not depend on the other low. Store each once and retain
    # every tried pair in its frozen order, avoiding hundreds of repeated dicts.
    first_fields = ("low1_index", "low1", "peak_index", "peak_high", "peak_age", "peak_age_limit", "peak_age_failed",
                    "depth", "depth_min", "depth_max", "depth_lower_margin", "depth_upper_margin", "depth_failed",
                    "pullback_sessions", "support")
    second_fields = ("low2_index", "low2", "rebound_high_index", "rebound_high", "rebound_size", "rebound_size_min",
                     "rebound_size_max", "rebound_lower_margin", "rebound_upper_margin", "rebound_status", "confirmation")
    first_contexts, second_contexts = {}, {}
    pair_failures, patterns = Counter(), Counter()
    for context in contexts:
        first_contexts[str(context["low1_index"])] = {**{key: context[key] for key in first_fields},
            "gates": {key: context["gates"][key] for key in ("pre_pullback_peak_available", "peak_age_ok", "depth_ok")}}
        if context["support"]:
            first_contexts[str(context["low1_index"])]["support"] = {key: value for key, value in context["support"].items() if key != "support_ceiling"}
        second_contexts[str(context["low2_index"])] = {**{key: context[key] for key in second_fields},
            "gates": {key: context["gates"][key] for key in ("rebound_high_available", "rebound_size_ok")}}
        pair_failures.update(key for key, value in context["gates"].items() if value is False)
        patterns[" + ".join(key for key, value in context["gates"].items() if value is False) or "ALL_STRUCTURE_GATES_PASS"] += 1
    return {
        "F2": trend,
        "F3": {"low_pivot_count": len(low_pivots), "high_pivot_count": len(high_pivots),
               "distinct_higher_low_pair_available": bool(contexts),
               "minimum_separation": config.minimum_pivot_separation,
               "pre_pullback_peak_available": any(c["gates"]["pre_pullback_peak_available"] for c in contexts),
               "selected_low1": selected["low1"] if selected else None,
               "selected_low2": selected["low2"] if selected else None,
               "separation": selected["separation"] if selected else None,
               "selected_peak_age": selected["peak_age"] if selected else None,
               "allowed_peak_age_limit": config.maximum_pullback_sessions + config.pivot_radius * 2,
               "selected_pair": structure if selected else None, "exact_failure_status": structure.get("status")},
        "F4": {"structure_status": structure.get("status"), "depth_min": config.shallow_depth_min,
               "depth_max": config.shallow_depth_max, "peak_age_limit": config.maximum_pullback_sessions + config.pivot_radius * 2,
               **{key: selected[key] if selected else None for key in
                  ("depth", "depth_lower_margin", "depth_upper_margin", "pullback_sessions", "peak_age_failed", "depth_failed")}},
        "F5": {"rebound_high_available": any(c["gates"]["rebound_high_available"] for c in contexts) if contexts else None,
               "rebound_status": "OK" if selected else "SEE_PAIR_CONTEXTS" if contexts else "UNAVAILABLE",
               "rebound_size_min": config.rebound_size_min, "rebound_size_max": config.rebound_size_max,
               **{key: selected[key] if selected else None for key in
                  ("rebound_size", "rebound_lower_margin", "rebound_upper_margin")}},
        "F6": confirmation,
        "F7": support or {"support_floor": None, "pullback_support_destroyed": None,
                          "t_close_break": None, "t_intraday_puncture_recovered": None, "entry_support_ok": None},
        "F8": {"price_structure_match": final, "research_match_status": original.get("research_match_status"),
               "rule_id": rule_id},
        "candidate_pairs": [[c["low1_index"], c["low2_index"]] for c in contexts],
        "first_low_contexts": first_contexts, "second_low_contexts": second_contexts,
        "pair_statistics": {"candidate_pair_failure_counts": dict(pair_failures),
                            "candidate_pair_failure_combinations": dict(patterns),
                            "all_pair_contexts_failed_counts": {key: bool(contexts) and all(c["gates"].get(key) is False for c in contexts)
                                                               for key in ("pre_pullback_peak_available", "peak_age_ok", "depth_ok", "rebound_high_available", "rebound_size_ok")},
                            "age_and_depth_pass_available": any(c["gates"]["peak_age_ok"] is True and c["gates"]["depth_ok"] is True for c in contexts),
                            "canonical_structure_selected": selected is not None},
        "near_miss_failed_condition_count": min(counts) if counts else None,
        "near_miss_classes": sorted(near_classes),
        "near_miss_semantics": "LOCAL_CONDITION_DIAGNOSTIC; NOT_A_RELAXED_RULE_OR_PROVEN_COUNTERFACTUAL_MATCH",
    }


def _identity_row(symbol: str, day: str, rule: str, history: Mapping[str, Any], item: Mapping[str, Any] | None) -> dict[str, Any]:
    bars = history.get("bars") or []
    minimum = max(90, frozen.RULE_CANDIDATES[rule].slow_average_window)
    return {"symbol": symbol, "signal_date": day, "rule_id": rule,
            "F0": {"board": classify_board(symbol), "st_status": item.get("st_status") if item else "UNRESOLVED",
                   "universe_eligible": True if item else None,
                   "input_quality": "T_BOUND_PRICE_INPUT; VOLUME_BASIS_UNVERIFIED" if item else "PARTIAL_UNVERIFIED",
                   "history_available": bool(bars), "b_kline_sha256": history.get("normalized_data_sha256")},
            "F1": {"enough_history": len(bars) >= minimum, "history_bars": len(bars),
                   "applicable_minimum": minimum, "adapter_minimum": 90,
                   "rule_minimum": frozen.RULE_CANDIDATES[rule].slow_average_window},
            "diagnostic_status": "PARTIAL_UNVERIFIED", "missing_reason": "NO_CANONICAL_C_RULE_OBSERVATION",
            "F2": None, "F3": None, "F4": None, "F5": None, "F6": None, "F7": None, "F8": None,
            "candidate_pairs": [], "first_low_contexts": {}, "second_low_contexts": {}, "pair_statistics": {},
            "near_miss_failed_condition_count": None, "near_miss_classes": []}


def build_rows(package: Mapping[str, Any], observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    day = observation["source"]["target_date"]
    histories = {row["symbol"]: row for row in package["generation_input_manifest"]["stock_klines"]}
    observed = {row["symbol"]: row for row in observation["observations"]}
    if len(observed) != len(observation["observations"]):
        raise ValueError("DUPLICATE_C_SYMBOL")
    rows = []
    for symbol in sorted(package["generation_input_manifest"]["universe"]["symbols"]):
        history, item = histories[symbol], observed.get(symbol)
        excluded = (observation.get("source", {}).get("coverage_groups") or {}).get("c_rule_or_st_excluded") or []
        st_known = bool(item) or any(entry == symbol or (
            isinstance(entry, dict) and entry.get("symbol") == symbol and "UNVERIFIED" not in entry.get("reason", ""))
            for entry in excluded)
        identity = frozen.classify_c_universe_row({"symbol": symbol,
                    "name": package.get("display_names", {}).get(symbol), "st_status_known_at_t": st_known})
        for rule in RULES:
            row = _identity_row(symbol, day, rule, history, item)
            row["F0"].update({"st_known_at_t": st_known,
                              "st_status": "NOT_ST" if identity["status"] == "ELIGIBLE" else identity["status"],
                              "universe_status": identity["status"],
                              "universe_eligible": identity["status"] == "ELIGIBLE" if st_known else None,
                              "rule_evaluated": bool(item),
                              "history_end_date": (history.get("bars") or [{}])[-1].get("date"),
                              "input_gaps": [g for g in observation.get("gaps", []) if str(g).endswith(":" + symbol)]})
            if item:
                original = item["rules"][rule]
                row["F8"] = {"price_structure_match": original.get("price_structure_match"),
                             "research_match_status": original.get("research_match_status"), "rule_id": rule}
            try:
                if item:
                    bars = frozen.validate_ohlcv_bars(history["bars"])
                    if (not bars or bars[-1]["date"] != day or any(b["date"] > day for b in bars)
                            or _b_kline_sha({"symbol": symbol, "bars": history["bars"]}) != item.get("b_kline_sha256")
                            or history.get("normalized_data_sha256") != item.get("b_kline_sha256")):
                        raise ValueError("T_BOUND_PREFIX_IDENTITY_MISMATCH")
                    row.update(diagnose(bars, original, rule))
                    complete = (row["F1"]["enough_history"] and
                                _all_known([row["F2"].get(key) for key in TREND_CONDITIONS]))
                    row.update({"diagnostic_status": "COMPLETE" if complete else "PARTIAL_UNVERIFIED",
                                "missing_reason": None if complete else "INSUFFICIENT_DATA",
                                "rule_observation_sha256": sha(canonical(original)),
                                "input_prefix_sha256": sha(canonical(bars))})
            except Exception as exc:
                row["missing_reason"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            rows.append(row)
    return rows


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for rule in RULES:
        cohort = [row for row in rows if row["rule_id"] == rule]
        funnel = Counter({f"F{i}": 0 for i in range(9)})
        attrition = Counter({f"F{i}": 0 for i in range(9)})
        unavailable = Counter({f"F{i}": 0 for i in range(9)})
        failures, missing, near, pair_failures, stock_all_pair_failures, pair_patterns, statuses, diagnostic_gaps = (Counter() for _ in range(8))
        joint = Counter({"both_failed": 0, "slope_only_failed": 0, "up_close_fraction_only_failed": 0, "missing": 0})
        complete = 0
        for row in cohort:
            complete += row["diagnostic_status"] == "COMPLETE"
            if row.get("missing_reason"):
                diagnostic_gaps[row["missing_reason"]] += 1
            statuses[(row.get("F3") or {}).get("exact_failure_status") or "UNAVAILABLE"] += 1
            for stage in ("F2", "F6", "F7"):
                conditions = (TREND_CONDITIONS if stage == "F2" else CONFIRMATION_CONDITIONS if stage == "F6" else ("entry_support_ok",))
                for key in conditions:
                    value = (row.get(stage) or {}).get(key)
                    failures[key] += value is False
                    missing[key] += value is None
            trend = row.get("F2") or {}
            slope, fraction = trend.get("positive_slope"), trend.get("up_close_fraction_ok")
            if not _all_known([slope, fraction]):
                joint["missing"] += 1
            else:
                joint["both_failed"] += slope is False and fraction is False
                joint["slope_only_failed"] += slope is False and fraction is True
                joint["up_close_fraction_only_failed"] += slope is True and fraction is False
            statistics = row["pair_statistics"]
            pair_failures.update(statistics.get("candidate_pair_failure_counts") or {})
            pair_patterns.update(statistics.get("candidate_pair_failure_combinations") or {})
            stock_all_pair_failures.update(statistics.get("all_pair_contexts_failed_counts") or {})
            for key in ("distinct_higher_low_pair_available", "pre_pullback_peak_available"):
                value = (row.get("F3") or {}).get(key)
                failures[key] += value is False
                missing[key] += value is None
            near.update(row["near_miss_classes"])
            passes = [row["F0"]["universe_eligible"], row["F1"]["enough_history"],
                      trend.get("trend_qualified"), (row.get("F3") or {}).get("pre_pullback_peak_available"),
                      statistics.get("age_and_depth_pass_available"), statistics.get("canonical_structure_selected"),
                      (row.get("F6") or {}).get("confirmation_qualified"),
                      (row.get("F7") or {}).get("entry_support_ok"),
                      (row.get("F8") or {}).get("price_structure_match")]
            alive = True
            for index, passed in enumerate(passes):
                attrition[f"F{index}"] += alive and passed is False
                unavailable[f"F{index}"] += alive and passed is None
                alive = alive and passed is True
                funnel[f"F{index}"] += alive
        result[rule] = {"input_stock_count": len(cohort),
                        "evaluated_count": sum(row["F0"]["rule_evaluated"] for row in cohort), "complete_diagnostic_count": complete,
                        "missing_diagnostic_count": len(cohort) - complete, "funnel_counts": dict(funnel),
                        "condition_failure_counts": dict(failures), "condition_missing_counts": dict(missing),
                        "all_pair_contexts_failed_counts": dict(stock_all_pair_failures),
                        "candidate_pair_failure_counts": dict(pair_failures),
                        "candidate_pair_failure_combinations": dict(pair_patterns),
                        "exact_structure_status_counts": dict(statuses), "diagnostic_gap_counts": dict(diagnostic_gaps),
                        "sequential_attrition_counts": dict(attrition),
                        "sequential_unavailable_counts": dict(unavailable),
                        "funnel_count_semantics": "KNOWN_SEQUENTIAL_PASSES; MISSING_IS_NOT_A_RULE_FAILURE",
                        "near_miss_counts": dict(near), "near_miss_count": sum(bool(r["near_miss_classes"]) for r in cohort),
                        "slope_up_close_fraction_joint": dict(joint),
                        "final_matches": sum((r.get("F8") or {}).get("price_structure_match") is True for r in cohort),
                        "top_failure_reasons": [{"condition": k, "count": v} for k, v in sorted(failures.items(), key=lambda x: (-x[1], x[0])) if v]}
    return result


def checkpoint(days: int, complete: int) -> dict[str, Any]:
    ready = (days >= 15 and complete >= 20_000) or days >= 20
    return {"real_c_run_days": days, "complete_stock_day_rule_observations": complete,
            "minimum_days": 15, "minimum_observations": 20_000, "hard_maximum_days": 20,
            "review_identity": "C_PROSPECTIVE_RULE_FUNNEL_REVIEW_V1" if ready else None,
            "status": "REVIEW_REQUIRED" if ready else "COLLECTING",
            "evidence_status": "SUFFICIENT_FOR_FUNNEL_REVIEW" if complete >= 20_000 else "INSUFFICIENT_DATA"}


def _read_verified(path: Path, expected: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError("INPUT_SHA_MISMATCH")
    return json.loads(raw)


def capture(b_result: Mapping[str, Any], prepared: Mapping[str, Any], published: Mapping[str, Any], *,
            state_root: Path, output_root: Path, start_date: str, now: datetime | None = None) -> dict[str, Any]:
    """Prepare immutable artifacts; only same-day, published, genuine C runs."""
    day = b_result["as_of_date"]
    current = (now or datetime.now(_BJT)).astimezone(_BJT)
    calendar = default_calendar()
    if (date.fromisoformat(start_date).isoformat() != start_date or day < start_date
            or current.date().isoformat() != day or current < calendar.session_close(day)):
        raise ValueError("NO_HISTORICAL_BACKFILL_OR_PRE_CLOSE_CAPTURE")
    if (published.get("status") != "C_DAILY_REPORT_PUBLISHED" or published.get("signal_date") != day
            or b_result.get("acquisition_timing") == "AUTHORIZED_WEEKEND_BACKFILL"):
        raise ValueError("GENUINE_PUBLISHED_C_RUN_REQUIRED")
    consumed = prepared["c_result"]["observation"]
    root = _safe_output_root()
    record = (root / consumed["record"]).resolve()
    if root not in record.parents:
        raise ValueError("C_RECORD_PATH_ESCAPES_ROOT")
    observation = _read_verified(record, consumed["record_sha256"])
    source = observation["source"]
    package_info = b_result["input_package"]
    package = _read_verified(Path(package_info["path"]), package_info["file_sha256"])
    acquired = datetime.fromisoformat(source["b_acquired_at_bjt"])
    read_at = datetime.fromisoformat(source["c_read_at_bjt"])
    if (source.get("target_date") != day or source.get("b_package_actual_sha256") != package_info["file_sha256"]
            or published.get("package_sha256") != package_info["file_sha256"]
            or source.get("handoff", {}).get("mode") != "SAME_RUNNER_READ_ONLY"
            or acquired.tzinfo is None or read_at.tzinfo is None
            or acquired.astimezone(_BJT).date().isoformat() != day or read_at.astimezone(_BJT).date().isoformat() != day
            or not calendar.session_close(day) <= acquired <= read_at <= current
            or observation.get("status") == "CAPTURE_FAILED" or not observation.get("observations")):
        raise ValueError("SAME_DAY_C_INPUT_PROVENANCE_REQUIRED")
    dated = state_root / "data/reports/c_daily" / day.replace("-", "") / "manifest.json"
    manifest_raw = dated.read_bytes()
    if sha(manifest_raw) != published["manifest_sha256"]:
        raise ValueError("PUBLISHED_C_MANIFEST_MISMATCH")
    manifest = json.loads(manifest_raw)
    if manifest.get("package_sha256") != package_info["file_sha256"] or manifest.get("signal_date") != day:
        raise ValueError("C_REPORT_INPUT_IDENTITY_MISMATCH")
    state = state_root / RELATIVE_ROOT
    previous = [json.loads(p.read_bytes()) for p in sorted((state / "daily").glob("????????.json")) if p.stem < day.replace("-", "")]
    if any(p["start_date"] != start_date or p["rule_source_sha256"] != sha(Path(frozen.__file__).read_bytes()) for p in previous):
        raise ValueError("CAPTURE_START_OR_FROZEN_RULE_IDENTITY_CHANGED")
    if any(p.get("checkpoint", {}).get("status") == "REVIEW_REQUIRED" for p in previous):
        return {"status": "C_FUNNEL_CHECKPOINT_REACHED_NO_FURTHER_CAPTURE"}
    # Count real published C dates, including recorder gaps, not repeated versions.
    real_days = set()
    for path in (state_root / "data/reports/c_daily").glob("????????/manifest.json"):
        token = path.parent.name
        if start_date.replace("-", "") <= token <= day.replace("-", ""):
            report_day = f"{token[:4]}-{token[4:6]}-{token[6:]}"
            report = json.loads(path.read_bytes())
            if (calendar.is_trading_day(report_day) and report.get("signal_date") == report_day
                    and report.get("schema_version") == "C_DAILY_RESEARCH_WATCHLIST_V1"
                    and report.get("c_status") in {"C_SUCCESS_WITH_MATCHES", "C_SUCCESS_NO_MATCH", "C_DATA_PENDING"}):
                real_days.add(token)
    if len(real_days) > 20:
        return {"status": "C_FUNNEL_HARD_MAXIMUM_REACHED_NO_FURTHER_CAPTURE", "real_c_run_days": len(real_days),
                "checkpoint": checkpoint(20, sum(p["complete_diagnostic_count"] for p in previous))}
    rows = build_rows(package, observation)
    by_rule = aggregate(rows)
    if {rule: by_rule[rule]["final_matches"] for rule in RULES} != manifest["matched_by_rule"]:
        raise ValueError("CANONICAL_C_MATCH_COUNT_MISMATCH")
    detail = b"".join(canonical(row) for row in rows)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", compresslevel=6, mtime=0) as archive:
        archive.write(detail)
    compressed = buffer.getvalue()
    if len(compressed) > MAX_DETAIL_BYTES:
        raise ValueError("C_FUNNEL_DETAIL_SIZE_LIMIT")
    day_token = day.replace("-", "")
    detail_relative = RELATIVE_ROOT / "details" / f"{day_token}.jsonl.gz"
    complete = sum(value["complete_diagnostic_count"] for value in by_rule.values())
    summary = {"schema_version": VERSION, "signal_date": day, "start_date": start_date,
               "mode": "RECORDING_ONLY / FAIL_SOFT", "rules": {k: asdict(frozen.RULE_CANDIDATES[k]) for k in RULES},
               "rule_version": frozen.C_STRATEGY_VERSION, "rule_source_sha256": sha(Path(frozen.__file__).read_bytes()),
               "recorder_source_sha256": sha(Path(__file__).read_bytes()),
               "package_sha256": package_info["file_sha256"], "c_observation_sha256": consumed["record_sha256"],
               "c_report_manifest_sha256": published["manifest_sha256"],
               "c_status": manifest["c_status"], "coverage_status": source.get("coverage_status"),
               "c_generation_fingerprint": source.get("b_generation_fingerprint"),
               "c_read_at_bjt": source["c_read_at_bjt"],
               "input_stock_count": len(rows) // len(RULES), "evaluated_stock_count": len(observation["observations"]),
               "evaluated_rule_observation_count": sum(value["evaluated_count"] for value in by_rule.values()),
               "retained_rule_row_count": len(rows),
               "complete_diagnostic_count": complete, "missing_diagnostic_count": len(rows) - complete,
               "by_rule": by_rule, "b_input_coverage": source.get("b_input_coverage"),
               "detail": {"path": detail_relative.as_posix(), "sha256": sha(compressed), "bytes": len(compressed),
                          "row_count": len(rows), "uncompressed_sha256": sha(detail), "uncompressed_bytes": len(detail)},
               "checkpoint": checkpoint(len(real_days), complete + sum(p["complete_diagnostic_count"] for p in previous)),
               "production_semantics_change": False, "outcome_accessed": False, "final_oos": "SEALED / UNREAD"}
    summary_raw = canonical(summary)
    if len(summary_raw) > MAX_SUMMARY_BYTES:
        raise ValueError("C_FUNNEL_SUMMARY_SIZE_LIMIT")
    summary_relative = RELATIVE_ROOT / "daily" / f"{day_token}.json"
    # Preflight both immutable destinations before adding either one.
    for relative, raw in ((detail_relative, compressed), (summary_relative, summary_raw)):
        target = state_root / relative
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise ValueError("C_FUNNEL_SYMLINK_REFUSED")
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("C_FUNNEL_SAME_DATE_IMMUTABILITY_CONFLICT")
    for relative, raw in ((detail_relative, compressed), (summary_relative, summary_raw)):
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        # Existing immutable writer gives same-date conflict rejection + atomic link.
        _copy_missing(path, state_root / relative)
    verify_artifacts(state_root, summary_relative)
    return {"status": "C_FUNNEL_STAGED_READBACK_VERIFIED", "paths": [detail_relative.as_posix(), summary_relative.as_posix()],
            "summary_sha256": sha(summary_raw), "checkpoint": summary["checkpoint"], "detail": summary["detail"]}


def verify_artifacts(root: Path, summary_relative: Path) -> None:
    summary = json.loads((root / summary_relative).read_bytes())
    info = summary["detail"]
    expected = RELATIVE_ROOT / "details" / f"{summary['signal_date'].replace('-', '')}.jsonl.gz"
    if info["path"] != expected.as_posix():
        raise ValueError("C_FUNNEL_DETAIL_PATH_MISMATCH")
    raw = (root / expected).read_bytes()
    plain = gzip.decompress(raw)
    if (len(raw) != info["bytes"] or sha(raw) != info["sha256"] or sha(plain) != info["uncompressed_sha256"]
            or len(plain) != info["uncompressed_bytes"] or len(plain.splitlines()) != info["row_count"]):
        raise ValueError("C_FUNNEL_DETAIL_READBACK_MISMATCH")


def publish(state_root: Path, staged: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse C's narrow commit/push/readback pattern; no B path is staged."""
    if not staged.get("paths"):
        return dict(staged)
    from run_c_daily_watchlist import _git

    validate_state_tree(state_root)
    if _git(state_root, "diff", "--cached", "--name-only").strip():
        raise ValueError("RUNTIME_STATE_ALREADY_HAS_STAGED_PATHS")
    paths = staged["paths"]
    # Existing date payloads may be re-read, but never replaced, deleted, or staged as edits.
    changed = _git(state_root, "diff", "--name-only", "--", *paths).strip()
    if changed:
        raise ValueError("APPEND_ONLY_EXISTING_CAPTURE_CHANGED")
    _git(state_root, "add", "--", *paths)
    staged_paths = set(_git(state_root, "diff", "--cached", "--name-only").decode().splitlines())
    if not staged_paths.issubset(set(paths)):
        raise ValueError("NON_FUNNEL_RUNTIME_PATH_STAGED")
    _git(state_root, "diff", "--cached", "--check")
    if staged_paths:
        _git(state_root, "config", "user.name", "github-actions[bot]")
        _git(state_root, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        _git(state_root, "commit", "-m", "runtime: append recording-only C rule funnel")
        _git(state_root, "push", "origin", "HEAD:runtime-state", timeout=60)
    _git(state_root, "fetch", "origin", "runtime-state", timeout=60)
    for path in paths:
        if _git(state_root, "show", f"FETCH_HEAD:{path}") != (state_root / path).read_bytes():
            raise ValueError("C_FUNNEL_REMOTE_READBACK_MISMATCH")
    return {**staged, "status": "C_FUNNEL_REMOTE_READBACK_VERIFIED",
            "runtime_state_sha": _git(state_root, "rev-parse", "FETCH_HEAD").decode().strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-result", type=Path, required=True)
    parser.add_argument("--prepared-result", type=Path, required=True)
    parser.add_argument("--published-result", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    args = parser.parse_args()
    result: dict[str, Any] = {"status": "C_FUNNEL_DISABLED"}
    if os.environ.get("ENABLE_C_RULE_FUNNEL_CAPTURE_V1", "").lower() == "true":
        try:
            # A separate bounded child/step is used only AFTER B delivery and C publication.
            load = lambda path: json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
            with tempfile.TemporaryDirectory(prefix="c-funnel-", dir=os.environ.get("RUNNER_TEMP")) as temp:
                result = capture(load(args.b_result), load(args.prepared_result), load(args.published_result),
                                 state_root=args.state_root, output_root=Path(temp),
                                 start_date=os.environ.get("C_RULE_FUNNEL_CAPTURE_START_DATE", ""))
                result = publish(args.state_root, result)
        except Exception as exc:
            result = {"status": "C_FUNNEL_RECORDING_FAILED_C_UNCHANGED", "reason": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0  # Research recording never changes B/C completion semantics.


if __name__ == "__main__":
    raise SystemExit(main())
