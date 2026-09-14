from __future__ import annotations

import copy
import json
from pathlib import Path

from b_volume_confirm_focus import (
    EVIDENCE_ACCUMULATING,
    VOLUME_CONFIRM_FOCUS_THRESHOLD,
    build_current_focus_summary,
    build_repeat_exposure_summary,
    build_volume_cohort_summary,
    ensure_volume_focus_epoch,
    is_volume_focus_candidate,
)
from trading_calendar import TradingCalendar
from watchlist_schema import stable_signal_id, validate_watchlist


CALENDAR = TradingCalendar(holidays=set())
FIXTURE = Path(__file__).parent / "fixtures" / "b_volume_focus_20260914.json"
STRATEGY = "B_BREAKOUT_RETEST_LEGACY_V1_1"
SETUP = "B_BREAKOUT_RETEST"
# The fixture is a compact canonical-watchlist copy of the live runtime-state
# 2026-09-14 output; it contains no raw provider response or K-line data.


def candidate(code: str, *, vol_ratio: object, score: int = 60) -> dict[str, object]:
    return {
        "code": code,
        "name": f"测试{code}",
        "buy_type": "B 突破回踩",
        "score": score,
        "price": 10.0,
        "trigger": 10.2,
        "stop": 9.5,
        "target": 12.0,
        "rr": 2.57,
        "vol_ratio": vol_ratio,
        "setup": SETUP,
    }


def watchlist(signal_date: str, candidates: list[dict[str, object]]) -> dict[str, object]:
    return {
        "date": signal_date,
        "mode": "close",
        "market_env": {},
        "sectors": [],
        "strategy_version": STRATEGY,
        "candidates": candidates,
    }


def formal_row(signal_id: str, *, status: str, exit_reason: str | None = None) -> dict[str, object]:
    return {
        "signal_id": signal_id,
        "status": status,
        "exit_reason": exit_reason,
        "entry_date": "2026-09-08",
        "trigger_date": "2026-09-08",
        "exit_date": "2026-09-09" if exit_reason else None,
        "realized_return_pct": 10.0 if exit_reason == "TARGET" else -5.0 if exit_reason == "STOP" else None,
        "realized_r": 2.0 if exit_reason == "TARGET" else -1.0 if exit_reason == "STOP" else None,
        "mfe_pct": 11.0,
        "mae_pct": -2.0,
    }


def test_volume_focus_threshold_is_fail_soft_and_exact():
    assert VOLUME_CONFIRM_FOCUS_THRESHOLD == 1.20
    assert not is_volume_focus_candidate({"vol_ratio": 1.1999})
    assert is_volume_focus_candidate({"vol_ratio": 1.20})
    assert is_volume_focus_candidate({"vol_ratio": 1.200001})
    for value in (None, "", "not-a-number", float("nan"), float("inf"), True):
        assert not is_volume_focus_candidate({"vol_ratio": value})


def test_20260914_canonical_fixture_has_one_focus_candidate_and_preserves_input():
    source = validate_watchlist(json.loads(FIXTURE.read_text(encoding="utf-8")))
    before = copy.deepcopy(source)

    summary = build_current_focus_summary(source, [source])

    assert summary["canonical_candidate_count"] == 16
    assert summary["focus_candidate_count"] == 1
    assert summary["focus_ratio_pct"] == 6.25
    assert [(row["code"], row["name"]) for row in summary["focus_candidates"]] == [("002394", "联发股份")]
    assert summary["focus_candidates"][0]["vol_ratio"] == 1.5762907292169963
    assert source == before


def test_focus_membership_does_not_apply_other_candidate_fields():
    current = watchlist("2026-09-14", [
        candidate("600001", vol_ratio=1.20, score=1),
        candidate("600002", vol_ratio=1.19, score=99),
    ])
    summary = build_current_focus_summary(current, [current])

    assert [row["code"] for row in summary["focus_candidates"]] == ["600001"]
    assert summary["focus_candidates"][0]["score"] == 1
    assert len(current["candidates"]) == 2


def test_prospective_cohorts_exclude_pre_epoch_and_reuse_formal_rows():
    old = watchlist("2026-09-03", [candidate("600001", vol_ratio=1.50)])
    current = watchlist("2026-09-08", [
        candidate("600002", vol_ratio=1.20),
        candidate("600003", vol_ratio=0.90),
    ])
    a_id = stable_signal_id(STRATEGY, "2026-09-08", "600002", SETUP)
    b_id = stable_signal_id(STRATEGY, "2026-09-08", "600003", SETUP)
    performance = {"all_rows": [
        formal_row(a_id, status="CLOSED", exit_reason="TARGET"),
        formal_row(b_id, status="CLOSED", exit_reason="STOP"),
    ]}

    result = build_volume_cohort_summary(
        [old, current],
        performance,
        "2026-09-11",
        epoch_start="2026-09-08",
        calendar=CALENDAR,
    )

    assert result["pre_epoch_excluded_signals"] == 1
    assert result["cohorts"]["A"]["total_signals"] == 1
    assert result["cohorts"]["A"]["target"] == 1
    assert result["cohorts"]["A"]["win_rate"] == 100.0
    assert result["cohorts"]["B"]["total_signals"] == 1
    assert result["cohorts"]["B"]["stop"] == 1
    assert result["evidence_status"] == EVIDENCE_ACCUMULATING
    assert result["review_gate"]["formal_strategy_change_allowed"] is False


def test_missing_volume_is_not_cohort_b_and_epoch_marker_is_fixed():
    current = watchlist("2026-09-14", [candidate("600001", vol_ratio=None)])
    tracker: dict[str, object] = {}

    record, changed = ensure_volume_focus_epoch(tracker, "2026-09-14", source_commit="abc")
    second, changed_again = ensure_volume_focus_epoch(tracker, "2026-09-13", source_commit="def")

    assert changed is True
    assert changed_again is False
    assert record["epoch_start"] == "2026-09-14"
    assert second["epoch_start"] == "2026-09-14"
    summary = build_volume_cohort_summary(
        [current],
        {"all_rows": []},
        "2026-09-14",
        epoch_start=record["epoch_start"],
        calendar=CALENDAR,
    )
    assert summary["unclassified_missing_or_invalid_vol_ratio"] == 1
    assert summary["cohorts"]["A"]["total_signals"] == 0
    assert summary["cohorts"]["B"]["total_signals"] == 0


def test_repeat_summary_is_descriptive_and_does_not_select_or_filter():
    first = watchlist("2026-09-03", [candidate("600001", vol_ratio=0.8)])
    second = watchlist("2026-09-08", [candidate("600001", vol_ratio=1.3), candidate("600002", vol_ratio=0.8)])
    repeated_id = stable_signal_id(STRATEGY, "2026-09-08", "600001", SETUP)
    result = build_repeat_exposure_summary(
        [first, second],
        {"all_rows": [formal_row(repeated_id, status="CLOSED", exit_reason="STOP")]},
        as_of_date="2026-09-11",
    )

    assert result["duplicate_signal_event_count"] == 1
    assert result["unique_ticker_count"] == 1
    assert result["repeated_stop_count"] == 1
    assert result["repeated_target_count"] == 0
    assert result["no_effect_on_canonical_selection"] is True
