from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from c_pre_outcome_design import RULE_CANDIDATES, build_entry_observation, trend_features
from c_raw_t_anchor_exploration import (
    BJT,
    COST_DECISION,
    EXPECTED_INPUTS,
    RULES,
    aggregate,
    anchor_arrays_for_range,
    apply_event_values,
    canonical_text_sha256,
    count_events_in_window,
    date_to_ms,
    horizon_record,
    ms_to_date,
    series_summary,
    strong_up_close_mask,
    symbol_bounds,
    trend_prefilter,
    verify_inputs,
)


def _store_from_bars(bars: list[dict[str, float]]) -> dict:
    return {
        "codes": ["600000.SH"],
        "code_index": np.zeros(len(bars), dtype=np.int64),
        "date_ms": np.asarray([int(item["date_ms"]) for item in bars], dtype=np.int64),
        "open": np.asarray([item["open"] for item in bars], dtype=np.float64),
        "high": np.asarray([item["high"] for item in bars], dtype=np.float64),
        "low": np.asarray([item["low"] for item in bars], dtype=np.float64),
        "close": np.asarray([item["close"] for item in bars], dtype=np.float64),
        "volume": np.asarray([item["volume"] for item in bars], dtype=np.float64),
    }


def test_ms_to_date_uses_beijing_not_utc():
    """Frozen daily-K timestamps are Beijing midnight; UTC conversion is off by one day."""

    value = date_to_ms("2024-06-13")
    assert ms_to_date(value) == "2024-06-13"
    utc_date = datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
    assert utc_date == "2024-06-12"
    assert datetime.fromtimestamp(value / 1000, tz=BJT).hour == 0


def test_apply_event_values_matches_declared_formula():
    values = np.asarray([10.0, 20.0])
    result = apply_event_values(values, dividend=0.5, bonus=0.3, ratio=0.2, allotment_price=8.0)
    expected = (values - 0.5 + 8.0 * 0.2) / (1.0 + 0.3 + 0.2)
    assert np.allclose(result, expected)


def test_apply_event_values_rejects_invalid_denominator():
    with pytest.raises(Exception):
        apply_event_values(np.asarray([10.0]), 0.0, -1.0, 0.0, 0.0)


def test_anchor_arrays_apply_only_events_at_or_before_anchor_and_keep_anchor_bar_raw():
    """``bar_date < ex_date <= T``: the anchor bar and later events must stay raw."""

    dates = [date_to_ms("2024-06-11"), date_to_ms("2024-06-12"), date_to_ms("2024-06-13")]
    bars = [{"date_ms": value, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100.0}
            for value in dates]
    store = _store_from_bars(bars)
    events = [(float(date_to_ms("2024-06-13")), 0.5, 0.0, 0.0, 0.0)]
    before = anchor_arrays_for_range(store, events, 0, 3, date_to_ms("2024-06-12"))
    assert list(before["close"]) == [10.0, 10.0, 10.0]
    after = anchor_arrays_for_range(store, events, 0, 3, date_to_ms("2024-06-13"))
    assert list(after["close"]) == [9.5, 9.5, 10.0]
    later = [*events, (float(date_to_ms("2024-06-14")), 1.0, 0.0, 0.0, 0.0)]
    assert list(anchor_arrays_for_range(store, later, 0, 3, date_to_ms("2024-06-13"))["close"]) == [
        9.5, 9.5, 10.0]


def test_anchor_arrays_agree_with_existing_project_vectorised_rule():
    """Cross-check against the rule already used by the B volume-path diagnostic."""

    dates = [date_to_ms(f"2024-06-{day:02d}") for day in (10, 11, 12, 13, 14, 17)]
    closes = [20.0, 19.5, 19.0, 18.0, 18.5, 19.2]
    bars = [{"date_ms": dates[index], "open": value, "high": value + 1.0, "low": value - 1.0,
             "close": value, "volume": 100.0} for index, value in enumerate(closes)]
    store = _store_from_bars(bars)
    events = [
        (float(date_to_ms("2024-06-12")), 0.4, 0.2, 0.0, 0.0),
        (float(date_to_ms("2024-06-14")), 0.3, 0.0, 0.0, 0.0),
    ]
    anchor = date_to_ms("2024-06-14")
    observed = anchor_arrays_for_range(store, events, 0, len(dates), anchor)["close"]
    reference = np.asarray(closes, dtype=float)
    event_array = np.asarray(dates, dtype=np.int64)
    for ex_date_ms, dividend, bonus, ratio, allotment_price in events:
        mask = event_array < ex_date_ms
        denominator = 1.0 + bonus + ratio
        reference[mask] = (reference[mask] - dividend + allotment_price * ratio) / denominator
    assert np.allclose(observed, reference)


def _trend_series(length: int = 140, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.0015, scale=0.012, size=length)
    return 10.0 * np.exp(np.cumsum(steps))


@pytest.mark.parametrize("rule_id", RULES)
def test_trend_prefilter_matches_frozen_trend_features(rule_id: str):
    """The prefilter must never disagree with the frozen trend qualification."""

    config = RULE_CANDIDATES[rule_id]
    close = _trend_series()
    flags = trend_prefilter(close, config)
    positions = list(range(len(close) - 6, len(close)))
    for position in positions:
        bars = [{"date": (datetime(2023, 1, 1) + timedelta(days=index)).date().isoformat(),
                 "open": float(close[index]), "high": float(close[index]),
                 "low": float(close[index]), "close": float(close[index]), "volume": 1.0}
                for index in range(position + 1)]
        expected = trend_features(bars, config)["trend_qualified"]
        assert bool(flags[position]) is bool(expected), (rule_id, position)


def test_trend_prefilter_is_false_before_minimum_history():
    close = _trend_series(length=90)
    flags = trend_prefilter(close, RULE_CANDIDATES["CONSERVATIVE_B"])
    assert not flags[:119].any()


def test_strong_up_close_mask_matches_confirmation_conditions():
    open_ = np.asarray([10.0, 10.0, 10.0, 10.0])
    high = np.asarray([11.0, 11.0, 11.0, 11.0])
    low = np.asarray([9.0, 9.0, 9.5, 9.0])
    close = np.asarray([10.0, 10.5, 10.2, 11.0])
    mask = strong_up_close_mask(open_, high, low, close)
    # index 0 has no predecessor; index 2 fails the higher-close test; index 3 qualifies
    assert list(mask) == [False, True, False, True]


def test_count_events_in_window_is_half_open():
    events = [(100.0, 0.0, 0.0, 0.0, 0.0), (200.0, 0.0, 0.0, 0.0, 0.0),
              (300.0, 0.0, 0.0, 0.0, 0.0)]
    assert count_events_in_window(events, 100.0, 300.0) == 2
    assert count_events_in_window(events, 300.0, 400.0) == 0


def test_series_summary_reports_denominator_and_skips_missing():
    summary = series_summary([0.05, None, -0.02, float("nan"), 0.10])
    assert summary["valid_n"] == 3
    assert summary["positive_n"] == 2
    assert summary["positive_rate"] == pytest.approx(2 / 3)
    assert summary["median"] == pytest.approx(0.05)
    assert series_summary([])["status"] == "INSUFFICIENT_DATA"


def test_aggregate_reports_cost_and_actual_trade_boundaries():
    records = [{
        "symbol": "600000.SH", "rule_id": "BALANCED_A", "signal_date": "2024-01-02",
        "signal_index": 5, "stage_prior_high_date": "2023-12-01", "low_one_date": "2023-12-05",
        "low_two_date": "2023-12-11",
    }]
    observations = {5: {"T+3": {"status": "OK", "observation_return": 0.02,
                                "t_plus_one_reference_return": 0.01, "mfe": 0.03, "mae": -0.01,
                                "intervening_corporate_actions": 0},
                        "T+5": {"status": "MISSING_SESSION_AT_HORIZON"},
                        "T+10": {"status": "HORIZON_OUTSIDE_FROZEN_CALENDAR"}}}
    result = aggregate(records, observations, {})
    window = result["BALANCED_A"]["windows"]["T+3"]
    assert result["BALANCED_A"]["raw_event_count"] == 1
    assert result["BALANCED_A"]["deduplicated_episode_count"] == 1
    assert window["observation_return"]["denominator"] == "valid computed window observation returns"
    assert window["observation_return"]["positive_n"] == 1
    assert result["BALANCED_A"]["windows"]["T+5"]["missing_session_at_horizon"] == 1
    assert result["BALANCED_A"]["windows"]["T+10"]["horizon_outside_frozen_calendar"] == 1
    assert window["cost_after_return"]["status"] == COST_DECISION
    assert window["actual_trade_win_rate"]["status"] == "NOT_AVAILABLE_NO_ACTUAL_FILL_EVIDENCE"
    assert result["CONSERVATIVE_B"]["raw_event_count"] == 0


def test_verify_inputs_fails_closed_when_files_are_missing(tmp_path: Path):
    verification = verify_inputs(tmp_path, tmp_path / "manifest.json")
    assert verification["status"] == "BLOCKED_BY_INPUT_IDENTITY_GAP"
    assert verification["blocking_reasons"]


def test_verify_inputs_detects_hash_mismatch(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "daily_k.parquet").write_bytes(b"not the frozen bytes")
    (raw_dir / "adjustment_factors.parquet").write_bytes(b"not the frozen bytes")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"adjustment_semantics": {}}), encoding="utf-8")
    verification = verify_inputs(raw_dir, manifest)
    assert verification["status"] == "BLOCKED_BY_INPUT_IDENTITY_GAP"
    assert "daily_k:HASH_MISMATCH" in verification["blocking_reasons"]


def test_canonical_text_sha256_normalises_crlf(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_bytes(b'{"a": 1}\r\n')
    digest, size = canonical_text_sha256(path)
    assert digest == hashlib.sha256(b'{"a": 1}\n').hexdigest()
    assert size == len(b'{"a": 1}\n')


def _two_symbol_store() -> dict:
    """Symbol 0 has six bars, symbol 1 only four: horizons must stay in-slab."""

    first = ["2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13", "2024-06-14", "2024-06-17"]
    second = ["2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13"]
    rows: list[tuple[int, str, float]] = []
    for day in first:
        rows.append((0, day, 10.0))
    for day in second:
        rows.append((1, day, 50.0))
    return {
        "codes": ["600000.SH", "600001.SH"],
        "code_index": np.asarray([row[0] for row in rows], dtype=np.int64),
        "date_ms": np.asarray([date_to_ms(row[1]) for row in rows], dtype=np.int64),
        "open": np.asarray([row[2] for row in rows], dtype=np.float64),
        "high": np.asarray([row[2] + 1.0 for row in rows], dtype=np.float64),
        "low": np.asarray([row[2] - 1.0 for row in rows], dtype=np.float64),
        "close": np.asarray([row[2] for row in rows], dtype=np.float64),
        "volume": np.asarray([1000.0 for _ in rows], dtype=np.float64),
    }


def test_horizon_record_searches_only_inside_the_symbol_slab():
    store = _two_symbol_store()
    calendar = [date_to_ms(day) for day in
                ["2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13", "2024-06-14", "2024-06-17"]]
    calendar_index = {value: index for index, value in enumerate(calendar)}
    first_bounds = symbol_bounds(store, 0)
    second_bounds = symbol_bounds(store, 1)
    assert first_bounds == (0, 6) and second_bounds == (6, 10)
    # symbol 1 lacks a bar at T+5 (calendar "2024-06-17") -> explicit missing, never a foreign bar
    missing = horizon_record(store, [], calendar_index, calendar, 6, "2024-06-10", 5, second_bounds)
    assert missing["status"] == "MISSING_SESSION_AT_HORIZON"
    assert missing["missing_date"] == "2024-06-17"
    # symbol 0 has all six sessions; its own slab must be used
    present = horizon_record(store, [], calendar_index, calendar, 0, "2024-06-10", 3, first_bounds)
    assert present["status"] == "OK"
    assert present["horizon_date"] == "2024-06-13"
    assert present["observation_return"] == pytest.approx(0.0)
    assert present["t_plus_one_reference_return"] == pytest.approx(0.0)


def test_horizon_record_rejects_horizon_beyond_the_frozen_calendar():
    store = _two_symbol_store()
    calendar = [date_to_ms(day) for day in
                ["2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13", "2024-06-14", "2024-06-17"]]
    calendar_index = {value: index for index, value in enumerate(calendar)}
    record = horizon_record(store, [], calendar_index, calendar, 3, "2024-06-13", 3,
                            symbol_bounds(store, 0))
    assert record["status"] == "HORIZON_OUTSIDE_FROZEN_CALENDAR"


def test_declared_input_identity_constants_are_frozen():
    assert EXPECTED_INPUTS["daily_k"]["sha256"] == (
        "61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426")
    assert EXPECTED_INPUTS["adjustment_factors"]["sha256"] == (
        "a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716")
    assert EXPECTED_INPUTS["manifest"]["text_identity"] is True


def test_exploration_entry_uses_frozen_candidate_matrix_only():
    """The exploration must not introduce rule variants or tuned parameters."""

    assert set(RULE_CANDIDATES) == {"BALANCED_A", "CONSERVATIVE_B"}
    assert RULE_CANDIDATES["BALANCED_A"].trend_window == 60
    assert RULE_CANDIDATES["CONSERVATIVE_B"].trend_window == 90
    payload = [{"date": "2024-01-02", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.4,
                "volume": 1000.0}]
    observation = build_entry_observation(payload, rule_id="BALANCED_A")
    assert observation["entry_candidate"] is False
    assert observation["namespace"] == "C_PRE_OUTCOME_DESIGN_V1"
