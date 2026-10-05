from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

from research_b_signal_entry_validity_decay import (
    CUTOFFS,
    FIXED_ENTRY_HORIZONS,
    analyze_signal,
    classify_first_trigger,
    cutoff_sensitivity,
    evaluate_fixed_horizons,
    merge_bars,
    normalize_bar,
    rebuild_execution_state_from_observations,
    sessions_after,
    summarize_rows,
)
from trading_calendar import TradingCalendar


CALENDAR = TradingCalendar(holidays={"2026-09-08"})


def bar(day: str, *, opening: float = 10.0, high: float = 10.5, low: float = 9.5, close: float = 10.0) -> dict[str, object]:
    return {"date": day, "open": opening, "high": high, "low": low, "close": close}


def signal(*, signal_date: str = "2026-09-04", trigger: float = 10.0) -> dict[str, object]:
    return {
        "signal_id": f"B_BREAKOUT_RETEST_LEGACY_V1_1:{signal_date}:600519:B_BREAKOUT_RETEST",
        "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
        "date": signal_date,
        "code": "600519",
        "setup": "B_BREAKOUT_RETEST",
        "score": 60,
        "trigger": trigger,
        "stop": 9.0,
        "target": 12.0,
        "rr": 2.0,
        "status": "pending",
        "observations": [],
    }


def normalized_bars(values: list[dict[str, object]]) -> dict[date, dict[str, object]]:
    return {date.fromisoformat(item["date"]): normalize_bar(item) for item in values}


def test_sessions_after_uses_xshg_sessions_and_holiday_boundary() -> None:
    assert [day.isoformat() for day in sessions_after("2026-09-04", 3, CALENDAR)] == [
        "2026-09-07",
        "2026-09-09",
        "2026-09-10",
    ]


def test_first_trigger_delay_t_plus_one_and_t_plus_ten_boundaries() -> None:
    item = signal()
    sessions = sessions_after(item["date"], 10, CALENDAR)
    values = [bar(day.isoformat(), opening=9.0, high=9.5, low=8.5, close=9.0) for day in sessions]
    values[0]["high"] = 10.0
    result = classify_first_trigger(item, normalized_bars(values), sessions[-1], CALENDAR)
    assert result["first_trigger_delay"] == 1
    assert result["cohort"] == "T+1"

    late = signal()
    late_values = [bar(day.isoformat(), opening=9.0, high=9.5, low=8.5, close=9.0) for day in sessions]
    late_values[-1]["high"] = 10.0
    late_result = classify_first_trigger(late, normalized_bars(late_values), sessions[-1], CALENDAR)
    assert late_result["first_trigger_delay"] == 10
    assert late_result["cohort"] == "T+6-T+10"


def test_untriggered_and_censored_classification_are_distinct() -> None:
    item = signal()
    sessions = sessions_after(item["date"], 10, CALENDAR)
    values = normalized_bars([bar(day.isoformat(), opening=9.0, high=9.5, low=8.5, close=9.0) for day in sessions])
    mature = classify_first_trigger(item, values, sessions[-1], CALENDAR)
    assert mature["delay_status"] == "UNTRIGGERED"
    assert mature["cohort"] == "UNTRIGGERED"

    censored = classify_first_trigger(item, values, sessions[4], CALENDAR)
    assert censored["delay_status"] == "CENSORED"
    assert censored["cohort"] == "CENSORED_OR_INCOMPLETE"


def test_tracker_t_plus_ten_untriggered_expires_and_triggered_entry_waits_for_t1() -> None:
    item = signal()
    sessions = sessions_after(item["date"], 10, CALENDAR)
    no_trigger = [bar(day.isoformat(), opening=9.0, high=9.5, low=8.5, close=9.0) for day in sessions]
    expired = rebuild_execution_state_from_observations(
        {**item, "observations": no_trigger}, calendar=CALENDAR, as_of=sessions[-1]
    )
    assert expired["status"] == "expired"
    assert expired["exit_reason"] == "EXPIRED_UNTRIGGERED"

    trigger_on_t10 = [bar(day.isoformat(), opening=9.0, high=9.5, low=8.5, close=9.0) for day in sessions]
    trigger_on_t10[-1] = bar(sessions[-1].isoformat(), opening=10.0, high=10.5, low=9.5, close=10.2)
    t1 = sessions_after(sessions[-1], 1, CALENDAR)[0]
    trigger_on_t10.append(bar(t1.isoformat(), opening=10.5, high=11.0, low=10.2, close=10.6))
    entered = rebuild_execution_state_from_observations(
        {**item, "observations": trigger_on_t10}, calendar=CALENDAR, as_of=t1
    )
    assert entered["entry_date"] == sessions[-1].isoformat()
    assert entered["exit_date"] == t1.isoformat()
    assert entered["exit_reason"] == "TIME_EXIT_T1_DEFERRED"


def test_missing_prior_session_does_not_create_false_delay() -> None:
    item = signal()
    sessions = sessions_after(item["date"], 10, CALENDAR)
    values = normalized_bars([bar(sessions[1].isoformat(), high=10.0)])
    result = classify_first_trigger(item, values, sessions[1], CALENDAR)
    assert result["raw_trigger_delay"] == 2
    assert result["first_trigger_delay"] is None
    assert result["delay_status"] == "INCOMPLETE"


def test_fixed_horizon_obeys_t_plus_one_and_terminal_carry_forward() -> None:
    item = signal(signal_date="2026-09-03")
    entry = date(2026, 9, 4)
    values = normalized_bars([
        bar("2026-09-04", opening=10.0, high=12.0, low=9.0, close=10.0),
        bar("2026-09-07", opening=10.0, high=12.0, low=9.5, close=11.0),
    ])
    result = evaluate_fixed_horizons(item, values, entry, "2026-09-07", CALENDAR)
    assert result["E+1"]["status"] == "TERMINAL"
    assert result["E+1"]["return_pct"] == 20.0
    assert result["E+3"]["status"] == "TERMINAL"
    assert result["E+5"]["status"] == "TERMINAL"


def test_fixed_horizon_same_bar_is_ambiguous_and_missing_is_not_zero() -> None:
    item = signal(signal_date="2026-09-03")
    entry = date(2026, 9, 4)
    ambiguous = normalized_bars([
        bar("2026-09-04", high=10.5, low=9.5),
        bar("2026-09-07", high=12.0, low=8.5),
    ])
    result = evaluate_fixed_horizons(item, ambiguous, entry, "2026-09-07", CALENDAR)
    assert result["E+1"]["status"] == "AMBIGUOUS_SAME_BAR"
    assert result["E+1"]["return_pct"] is None

    missing = normalized_bars([bar("2026-09-04", high=10.5, low=9.5)])
    missing_result = evaluate_fixed_horizons(item, missing, entry, "2026-09-07", CALENDAR)
    assert missing_result["E+1"]["status"] == "MISSING_OBSERVATION"
    assert missing_result["E+1"]["return_pct"] is None


def test_merge_conflict_is_fail_closed() -> None:
    left = [bar("2026-09-07", close=10.0)]
    right = [bar("2026-09-07", close=10.1)]
    merged, conflicts = merge_bars(left, right)
    assert date(2026, 9, 7) in merged
    assert conflicts == ["2026-09-07"]


def test_cutoff_sensitivity_is_counterfactual_and_does_not_mutate_rows() -> None:
    rows = [
        {
            "cohort": "T+1",
            "delay_status": "KNOWN",
            "first_trigger_delay": 1,
            "raw_trigger_delay": 1,
            "operational_return_pct": 1.0,
            "operational_terminal_status": "TARGET",
        },
        {
            "cohort": "T+4-T+5",
            "delay_status": "KNOWN",
            "first_trigger_delay": 5,
            "raw_trigger_delay": 5,
            "operational_return_pct": -2.0,
            "operational_terminal_status": "STOP",
        },
    ]
    before = [dict(row) for row in rows]
    result = cutoff_sensitivity(rows)
    assert [item["entry_validity_cutoff_sessions"] for item in result] == list(CUTOFFS)
    assert result[0]["retained_triggered_signals"] == 1
    assert result[-1]["retained_triggered_signals"] == 2
    assert rows == before


def test_delay_status_aggregation_keeps_conflict_exclusive() -> None:
    rows = [
        {"delay_status": "KNOWN", "cohort": "T+1", "operational_path_status": "INCOMPLETE"},
        {"delay_status": "INCOMPLETE", "cohort": "CENSORED_OR_INCOMPLETE", "operational_path_status": "INCOMPLETE"},
        {"delay_status": "CENSORED", "cohort": "CENSORED_OR_INCOMPLETE", "operational_path_status": "INCOMPLETE"},
        {"delay_status": "DATA_CONFLICT", "cohort": "CENSORED_OR_INCOMPLETE", "operational_path_status": "INCOMPLETE"},
    ]
    summary = summarize_rows(rows)
    assert summary["delay_known_count"] == 1
    assert summary["delay_incomplete_count"] == 1
    assert summary["delay_censored_count"] == 1
    assert summary["delay_data_conflict_count"] == 1
    assert (
        summary["delay_known_count"]
        + summary["delay_incomplete_count"]
        + summary["delay_censored_count"]
        + summary["delay_data_conflict_count"]
        == summary["total_signals"]
    )


def test_generated_fixture_delay_status_partition_and_cohort_invariants() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "research" / "b_signal_entry_validity_decay_v1"
    with (root / "signal_level_results.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((root / "cohort_summary.json").read_text(encoding="utf-8"))
    counts = Counter(row["delay_status"] for row in rows)
    assert counts == Counter({"KNOWN": 118, "INCOMPLETE": 82, "CENSORED": 9, "DATA_CONFLICT": 1})
    assert sum(counts.values()) == len(rows) == 210

    unresolved = summary["cohorts"]["CENSORED_OR_INCOMPLETE"]
    assert unresolved["total_signals"] == 92
    assert (
        unresolved["delay_incomplete_count"]
        + unresolved["delay_censored_count"]
        + unresolved["delay_data_conflict_count"]
        == unresolved["total_signals"]
        == 92
    )
    assert unresolved["delay_incomplete_count"] == 82
    assert unresolved["delay_censored_count"] == 9
    assert unresolved["delay_data_conflict_count"] == 1
    assert summary["early_vs_late"]["early_sample_size"] == 117
    assert summary["early_vs_late"]["late_sample_size"] == 1


def test_analyze_signal_uses_canonical_signal_id_and_fixed_horizon_fields() -> None:
    item = signal(signal_date="2026-09-03")
    item["observations"] = [bar("2026-09-04", high=10.5, low=9.5), bar("2026-09-07", high=10.6, low=9.5)]
    canonical = {"price": 9.8}
    row = analyze_signal(item, canonical, [], "2026-09-07", TradingCalendar(holidays=set()))
    assert row["signal_id"] == item["signal_id"]
    assert row["first_trigger_delay"] == 1
    assert row["e1_status"] == "MARK_TO_MARKET"
    assert row["e3_status"] == "CENSORED"
    assert row["e5_status"] == "CENSORED"
