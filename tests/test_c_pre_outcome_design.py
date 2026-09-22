from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from trading_calendar import default_calendar

from c_pre_outcome_design import (
    C_ENTRY_SCHEMA,
    C_EXIT_SCHEMA,
    RULE_CANDIDATES,
    build_data_dependency_check,
    build_entry_observation,
    classify_c_universe_row,
    classify_exit_observation,
    high_volume_low_progress,
    limit_up_failure_status,
    relative_volume_features,
    find_pullback_structure,
    validate_ohlcv_bars,
    volume_path_features,
)


def _xshg_sessions(count: int) -> list[date]:
    calendar = default_calendar()
    sessions: list[date] = []
    current = date(2026, 1, 5)
    while len(sessions) < count:
        if calendar.is_trading_day(current):
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


_SESSION_DATES = _xshg_sessions(100)


def _bar(day: int | date | str, close: float, *, opening: float | None = None, high: float | None = None, low: float | None = None, volume: float = 100.0, **extra):
    if isinstance(day, int):
        day_value = _SESSION_DATES[day - 1].isoformat()
    else:
        day_value = day.isoformat() if isinstance(day, date) else day
    opening = close if opening is None else opening
    high = max(opening, close) + 0.8 if high is None else high
    low = min(opening, close) - 0.8 if low is None else low
    return {"date": day_value, "open": opening, "high": high, "low": low, "close": close, "volume": volume, **extra}


def _synthetic_entry_bars() -> list[dict[str, float | str]]:
    bars: list[dict[str, float | str]] = []
    for index in range(60):
        close = 100.0 + index * 0.50
        bars.append(_bar(index + 1, close, high=close + 1.0, low=close - 1.0, volume=100.0))
    # A prior stage high, a shallow two-test pullback, a small rebound high,
    # then T close confirmation below the stage high.  No 60-session high
    # breakout is required for the candidate.
    bars.extend([
        _bar(61, 129.0, high=135.0, low=127.0, volume=90.0),
        _bar(62, 125.0, high=127.0, low=123.0, volume=75.0),
        _bar(63, 127.0, high=128.0, low=125.0, volume=70.0),
        _bar(64, 126.0, high=127.0, low=125.0, volume=68.0),
        _bar(65, 128.0, high=129.0, low=127.0, volume=72.0),
        _bar(66, 125.5, high=127.0, low=124.0, volume=70.0),
        _bar(67, 129.0, high=130.0, low=126.0, volume=80.0),
        _bar(68, 132.0, high=133.0, low=129.0, volume=90.0),
        _bar(69, 130.0, high=131.0, low=128.0, volume=95.0),
        _bar(70, 129.5, high=131.0, low=128.0, volume=92.0),
        _bar(71, 130.0, high=131.0, low=128.0, volume=95.0),
        _bar(72, 134.0, opening=131.0, high=135.0, low=131.0, volume=130.0),
    ])
    return bars


def test_relative_volume_is_prefix_only_and_future_bar_cannot_change_t_value():
    bars = [_bar(day, 100.0, volume=100.0) for day in range(1, 23)]
    bars[-1]["volume"] = 250.0
    before = relative_volume_features(bars, len(bars) - 1)
    extended = bars + [_bar(23, 100.0, volume=100000.0)]
    after = relative_volume_features(extended, len(bars) - 1)
    assert before == after
    assert before["relative_volume_ratio"] == pytest.approx(2.5)
    assert before["anomaly_ratio_candidate"] is True


def test_volume_path_keeps_directional_counts_and_does_not_claim_mechanism():
    bars = [_bar(day, 100.0 + (day % 2), volume=100.0 + day) for day in range(1, 11)]
    result = volume_path_features(
        bars,
        pullback_start=4,
        pullback_end_exclusive=9,
        reference_start=0,
        reference_end_exclusive=4,
    )
    assert result["path_label"] in {"CONTRACTED_OBSERVABLE", "MIXED_OBSERVABLE", "EXPANDED_OBSERVABLE"}
    assert result["mechanism_claim"].startswith("UNKNOWN")
    assert result["up_day_count"] + result["down_day_count"] <= 5


def test_volume_path_requires_two_effective_days_per_direction():
    bars = [
        _bar(1, 100.0, volume=100.0),
        _bar(2, 101.0, volume=110.0),
        _bar(3, 100.0, volume=90.0),
        _bar(4, 100.0, volume=95.0),
    ]
    result = volume_path_features(
        bars,
        pullback_start=1,
        pullback_end_exclusive=4,
        reference_start=0,
        reference_end_exclusive=1,
    )
    assert result["up_day_count"] == 1
    assert result["down_day_count"] == 1
    assert result["up_down_ratio_status"] == "INSUFFICIENT_DIRECTIONAL_DAYS"
    assert result["up_to_down_volume_median_ratio"] is None
    assert result["up_day_volume_median"] is None
    assert result["down_day_volume_median"] is None


def test_c_entry_uses_two_distinct_higher_lows_and_no_breakout_gate():
    result = build_entry_observation(_synthetic_entry_bars(), rule_id="BALANCED_A")
    assert result["schema_version"] == C_ENTRY_SCHEMA
    assert result["entry_candidate"] is True
    assert result["trend"]["trend_qualified"] is True
    structure = result["structure"]
    assert structure["low_one_index"] != structure["low_two_index"]
    assert structure["low_two"] > structure["low_one"]
    assert result["confirmation"]["no_stage_breakout_required"] is True
    assert result["stage_resistance"]["stage_prior_high"] > result["confirmation"]["close_t"]
    assert result["support"]["support_tolerance_role"] == "DISPLAY_ONLY"
    assert result["support"]["pivot_uses_t_bar"] is False
    assert result["future_data_used"] is False
    assert "outcome" not in result


def test_entry_rejects_structure_when_trend_conditions_fail():
    bars = _synthetic_entry_bars()
    for index in range(60):
        close = 160.0 - index * 0.5
        bars[index].update(open=close, high=close + 1.0, low=close - 1.0, close=close)
    result = build_entry_observation(bars, rule_id="BALANCED_A")
    assert result["structure"]["status"] == "OK"
    assert result["trend"]["status"] == "OK"
    assert result["trend"]["positive_slope"] is False
    assert result["trend"]["trend_qualified"] is False
    assert result["entry_candidate"] is False


def test_support_events_are_separate_and_tolerance_is_not_a_gate():
    puncture_bars = _synthetic_entry_bars()
    puncture_bars[-1].update(low=122.0)
    puncture = build_entry_observation(puncture_bars, rule_id="BALANCED_A")
    assert puncture["support"]["status"] == "T_INTRADAY_PUNCTURE_RECOVERED"
    assert puncture["support"]["t_intraday_puncture_recovered"] is True
    assert puncture["support"]["t_close_break"] is False
    assert puncture["entry_candidate"] is True

    close_break_bars = _synthetic_entry_bars()
    close_break_bars[-1] = _bar(72, 122.0, opening=123.0, high=124.0, low=121.0)
    close_break = build_entry_observation(close_break_bars, rule_id="BALANCED_A")
    assert close_break["support"]["status"] == "T_CLOSE_BREAK"
    assert close_break["support"]["t_close_break"] is True
    assert close_break["entry_candidate"] is False

    destroyed_bars = _synthetic_entry_bars()
    destroyed_bars[-3] = _bar(70, 122.0, opening=124.0, high=131.0, low=121.0)
    destroyed_bars[-2] = _bar(71, 120.0, opening=123.0, high=131.0, low=119.0)
    destroyed = build_entry_observation(destroyed_bars, rule_id="BALANCED_A")
    assert destroyed["support"]["status"] == "PULLBACK_SUPPORT_DESTROYED"
    assert destroyed["support"]["pullback_support_destroyed"] is True
    assert destroyed["support"]["entry_support_ok"] is False
    assert destroyed["entry_candidate"] is False


def test_pivots_are_confirmed_from_strict_pre_t_prefix():
    bars = _synthetic_entry_bars()
    altered_t = list(bars)
    altered_t[-1] = _bar(72, 129.0, opening=128.0, high=130.0, low=127.0)
    baseline = find_pullback_structure(bars, RULE_CANDIDATES["BALANCED_A"])
    altered = find_pullback_structure(altered_t, RULE_CANDIDATES["BALANCED_A"])
    assert baseline["status"] == altered["status"] == "OK"
    for field in ("peak_index", "low_one_index", "low_two_index", "rebound_high_index", "stage_prior_high"):
        assert baseline[field] == altered[field]
    assert baseline["pivot_confirmation_timing"] == "T_MINUS_ONE_CLOSE"
    assert baseline["pivot_uses_t_bar"] is False


def test_universe_gate_is_main_board_non_st_and_fail_closed_without_pit_status():
    assert classify_c_universe_row({"symbol": "600001.SH", "name": "平安银行", "st_status_known_at_t": True})["status"] == "ELIGIBLE"
    assert classify_c_universe_row({"symbol": "600001.SH", "name": "*ST样本", "st_status_known_at_t": True})["status"] == "EXCLUDED_ST_OR_STAR_ST"
    assert classify_c_universe_row({"symbol": "300001.SZ", "name": "主板外", "st_status_known_at_t": True})["status"] == "EXCLUDED_BOARD"
    assert classify_c_universe_row({"symbol": "600001.SH", "name": "平安银行"})["status"] == "UNRESOLVED_ST_STATUS"


def test_limit_up_blast_is_unknown_without_valid_limit_price_and_tick():
    unavailable = limit_up_failure_status(_bar(1, 109.0, high=110.0, low=99.0))
    assert unavailable["status"] == "UNAVAILABLE"
    available = limit_up_failure_status(_bar(1, 109.0, high=110.0, low=99.0, limit_up_price=110.0, tick_size=0.01))
    assert available["status"] == "AVAILABLE_DAILY_PROXY"
    assert available["limit_up_touched"] is True
    assert available["limit_up_failed_to_hold"] is True


def test_high_volume_stall_is_observable_only():
    bars = [_bar(day, 100.0, volume=100.0) for day in range(1, 22)]
    bars.append(_bar(22, 100.1, opening=100.0, high=102.0, low=99.8, volume=250.0))
    result = high_volume_low_progress(bars, 21)
    assert result["high_volume_low_price_progress"] is True
    assert "distribution" in result["mechanism_claim"]


def test_exit_blocks_same_day_sell_and_separates_profit_from_risk():
    bars = _synthetic_entry_bars()
    same_day = classify_exit_observation(
        bars,
        entry_index=len(bars) - 1,
        entry_price=133.0,
        stage_prior_high=135.0,
        support_floor=123.0,
        rule_id="BALANCED_A",
    )
    assert same_day["schema_version"] == C_EXIT_SCHEMA
    assert same_day["exit_state"] == "ENTRY_SESSION_NOT_SELLABLE"
    bars.append(_bar(73, 122.0, opening=124.0, high=125.0, low=121.0, volume=150.0))
    support_break = classify_exit_observation(
        bars,
        entry_index=len(bars) - 2,
        entry_price=133.0,
        stage_prior_high=135.0,
        support_floor=123.0,
        rule_id="BALANCED_A",
    )
    assert support_break["exit_state"] == "KEY_SUPPORT_BREAK"
    assert support_break["exit_class"] == "ENTRY_RISK"
    assert support_break["support_break"] is True
    assert support_break["support_intraday_puncture_recovered"] is False
    assert support_break["reference_execution_semantics"] == "REFERENCE_EXECUTION_NOT_ACTUAL_FILL"


def test_exit_events_use_only_post_entry_near_resistance_observations():
    bars = _synthetic_entry_bars()
    # Two failures before the position exists must not count toward early exit.
    bars[-3] = _bar(70, 130.0, opening=134.0, high=135.0, low=126.0, volume=110.0)
    bars[-2] = _bar(71, 130.0, opening=134.0, high=135.0, low=126.0, volume=115.0)
    entry_index = len(bars) - 1
    bars.append(_bar(73, 130.0, opening=130.0, high=131.0, low=129.0, volume=250.0))
    far_from_resistance = classify_exit_observation(
        bars,
        entry_index=entry_index,
        entry_price=120.0,
        stage_prior_high=135.0,
        support_floor=123.0,
        rule_id="BALANCED_A",
    )
    assert far_from_resistance["failed_push_features"]["failed_push_count"] == 0
    assert far_from_resistance["current_resistance_rejection"] is False
    assert far_from_resistance["high_volume_low_progress"]["high_volume_low_price_progress"] is True
    assert far_from_resistance["high_volume_low_progress_near_resistance"] is False
    assert far_from_resistance["early_profit_taking_candidate"] is False
    assert far_from_resistance["exit_state"] == "HOLD_OR_REOBSERVE"

    first_warning_bars = _synthetic_entry_bars() + [
        _bar(73, 130.0, opening=131.0, high=135.0, low=126.0, volume=110.0),
    ]
    first_warning = classify_exit_observation(
        first_warning_bars,
        entry_index=len(_synthetic_entry_bars()) - 1,
        entry_price=120.0,
        stage_prior_high=135.0,
        support_floor=123.0,
        rule_id="BALANCED_A",
    )
    assert first_warning["current_resistance_rejection"] is True
    assert first_warning["first_resistance_rejection_warning"] is True
    assert first_warning["early_profit_taking_confirmed"] is False
    assert first_warning["exit_state"] == "FIRST_RESISTANCE_REJECTION_WARNING"

    repeated_bars = _synthetic_entry_bars() + [
        _bar(73, 130.0, opening=131.0, high=135.0, low=126.0, volume=110.0),
        _bar(74, 130.0, opening=130.0, high=135.0, low=126.0, volume=250.0),
    ]
    repeated = classify_exit_observation(
        repeated_bars,
        entry_index=len(_synthetic_entry_bars()) - 1,
        entry_price=120.0,
        stage_prior_high=135.0,
        support_floor=123.0,
        rule_id="BALANCED_A",
    )
    assert repeated["current_resistance_rejection"] is True
    assert repeated["repeated_resistance_rejection"] is True
    assert repeated["failed_push_features"]["failed_push_count"] == 2
    assert repeated["high_volume_low_progress_near_resistance"] is True
    assert repeated["early_profit_taking_confirmed"] is True
    assert repeated["exit_state"] == "EARLY_PROFIT_TAKING_CANDIDATE"


def test_ohlcv_date_validation_rejects_illegal_and_duplicate_dates():
    invalid = _bar(1, 100.0)
    invalid["date"] = "2026-02-30"
    with pytest.raises(ValueError, match="invalid bar date"):
        validate_ohlcv_bars([invalid])

    duplicate = [_bar(1, 100.0), _bar(1, 101.0)]
    with pytest.raises(ValueError, match="strictly chronological"):
        validate_ohlcv_bars(duplicate)


def test_t_close_t_plus_one_boundary_is_not_same_day_sell():
    bars = _synthetic_entry_bars()
    t_date = bars[-1]["date"]
    same_day = classify_exit_observation(
        bars,
        entry_index=len(bars) - 1,
        entry_price=133.0,
        stage_prior_high=135.0,
        support_floor=123.0,
        rule_id="BALANCED_A",
    )
    assert same_day["exit_state"] == "ENTRY_SESSION_NOT_SELLABLE"
    bars.append(_bar(73, 122.0, opening=124.0, high=125.0, low=121.0, volume=150.0))
    assert bars[-1]["date"] > t_date
    next_session = classify_exit_observation(
        bars,
        entry_index=len(bars) - 2,
        entry_price=133.0,
        stage_prior_high=135.0,
        support_floor=123.0,
        rule_id="BALANCED_A",
    )
    assert next_session["as_of_date"] == bars[-1]["date"]
    assert next_session["exit_state"] == "KEY_SUPPORT_BREAK"


def test_candidate_matrix_is_small_and_explicit():
    assert set(RULE_CANDIDATES) == {"BALANCED_A", "CONSERVATIVE_B"}
    assert RULE_CANDIDATES["BALANCED_A"].shallow_depth_max < 0.22
    assert RULE_CANDIDATES["CONSERVATIVE_B"].trend_window > RULE_CANDIDATES["BALANCED_A"].trend_window


def test_data_check_is_metadata_only_and_marks_missing_pit_evidence():
    result = build_data_dependency_check(
        Path("data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"),
        project_root=Path("."),
    )
    assert result["c_outcome_accessed"] is False
    assert result["formal_historical_return_research_run"] is False
    assert result["checks"]["known_at"]["status"] == "PARTIAL_UNVERIFIED"
    assert result["checks"]["local_replay"]["daily_k_local_present"] is False
    assert result["checks"]["local_replay"]["scope"] == "THIS_WORKTREE_ONLY"
    assert result["checks"]["local_replay"]["daily_k_local_sha256_status"] == "NOT_VERIFIABLE_MISSING"
    assert result["checks"]["universe"]["st_status"] == "UNRESOLVED_FOR_HISTORICAL_PIT_UNIVERSE"
