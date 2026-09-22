from __future__ import annotations

from pathlib import Path

import pytest

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
    volume_path_features,
)


def _bar(day: int, close: float, *, opening: float | None = None, high: float | None = None, low: float | None = None, volume: float = 100.0, **extra):
    opening = close if opening is None else opening
    high = max(opening, close) + 0.8 if high is None else high
    low = min(opening, close) - 0.8 if low is None else low
    return {"date": f"2026-01-{day:02d}", "open": opening, "high": high, "low": low, "close": close, "volume": volume, **extra}


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


def test_c_entry_uses_two_distinct_higher_lows_and_no_breakout_gate():
    result = build_entry_observation(_synthetic_entry_bars(), rule_id="BALANCED_A")
    assert result["schema_version"] == C_ENTRY_SCHEMA
    assert result["entry_candidate"] is True
    structure = result["structure"]
    assert structure["low_one_index"] != structure["low_two_index"]
    assert structure["low_two"] > structure["low_one"]
    assert result["confirmation"]["no_stage_breakout_required"] is True
    assert result["stage_resistance"]["stage_prior_high"] > result["confirmation"]["close_t"]
    assert result["future_data_used"] is False
    assert "outcome" not in result


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
    assert support_break["reference_execution_semantics"] == "REFERENCE_EXECUTION_NOT_ACTUAL_FILL"


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
    assert result["checks"]["universe"]["st_status"] == "UNRESOLVED_FOR_HISTORICAL_PIT_UNIVERSE"
