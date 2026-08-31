from __future__ import annotations

from copy import deepcopy
from datetime import date, time, timedelta

import numpy as np
import pytest

import generation_contract
from b_breakout_retest import (
    LEGACY_SPEC,
    SETUP_ID,
    STRATEGY_SPEC_SHA256,
    evaluate_candidate,
    evaluate_numeric_projection,
    semantic_spec_sha256,
)
from test_a_platform_breakout import AS_OF, SYMBOL, _base_bars, _bar, _manifest
from trading_calendar import TradingCalendar


EXPECTED_SPEC_SHA256 = "5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112"


@pytest.fixture(autouse=True)
def _explicit_test_calendar(monkeypatch):
    monkeypatch.setattr(
        generation_contract,
        "default_calendar",
        lambda: TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
    )


def _b_bars() -> list[dict[str, object]]:
    bars = _base_bars()
    first_day = date.fromisoformat(AS_OF) - timedelta(days=259)
    bars[252] = _bar(first_day + timedelta(days=252), close=11.0, high=11.1, low=10.5, volume=200)
    for index in range(253, 259):
        bars[index] = _bar(first_day + timedelta(days=index), close=10.1, high=10.2, low=9.9, volume=100)
    bars[259] = _bar(date.fromisoformat(AS_OF), close=10.1, high=10.3, low=9.9, volume=150)
    return bars


def test_semantic_spec_hash_is_pinned_and_mutation_sensitive():
    assert STRATEGY_SPEC_SHA256 == EXPECTED_SPEC_SHA256
    assert semantic_spec_sha256(LEGACY_SPEC) == EXPECTED_SPEC_SHA256
    mutated = deepcopy(LEGACY_SPEC)
    mutated["b_match"]["pullback"]["volume_contraction"] = "pull_volume<volume[i]*0.71"
    assert semantic_spec_sha256(mutated) != EXPECTED_SPEC_SHA256


def test_exact_v0_b_breakout_retest_reconstructs_and_uses_base_hi_as_trigger():
    result = evaluate_candidate(_manifest(_b_bars()), SYMBOL)
    assert result.setup_id == SETUP_ID
    assert result.status == "QUALIFIED_LEGACY_BASELINE"
    assert result.features is not None
    assert "BREAKOUT_CLOSE_ABOVE_60D_HIGH" in result.matched_conditions
    assert "PULLBACK_VOLUME_LT_70_PCT_BREAKOUT" in result.matched_conditions
    assert result.trigger == pytest.approx(10.1)
    assert result.target_type == "PRESSURE"
    assert result.rr is not None and result.rr >= 2.0


def test_first_qualifying_breakout_stops_scan_even_if_pullback_fails():
    bars = _b_bars()
    first_day = date.fromisoformat(AS_OF) - timedelta(days=259)
    bars[246] = _bar(first_day + timedelta(days=246), close=11.0, high=11.1, low=10.5, volume=200)
    for index in range(247, 252):
        bars[index] = _bar(first_day + timedelta(days=index), close=9.0, high=9.2, low=8.8, volume=100)
    bars[259] = _bar(date.fromisoformat(AS_OF), close=9.5, high=9.6, low=9.2, volume=150)
    result = evaluate_candidate(_manifest(bars), SYMBOL)
    assert result.status == "NOT_MATCHED"
    assert "PULLBACK_CLOSE_GE_97_PCT_BASE" in result.failed_conditions


def test_fast_projection_matches_manifest_evaluator_core_fields():
    bars = _b_bars()
    manifest = _manifest(bars)
    evaluated = evaluate_candidate(manifest, SYMBOL)
    arrays = tuple(
        np.asarray([float(item[field]) for item in bars], dtype=float)
        for field in ("close", "volume", "high", "low")
    )
    projected = evaluate_numeric_projection(
        symbol=SYMBOL,
        signal_date=AS_OF,
        earliest_execution_date=manifest.earliest_execution_date or "",
        bars=arrays,
        index_bars=manifest.index.bars,
    )
    assert projected["setup_id"] == evaluated.setup_id
    assert projected["status"] == evaluated.status
    for field in (
        "matched_conditions",
        "failed_conditions",
        "reject_reasons",
        "support",
        "trigger",
        "stop",
        "target",
        "target_type",
        "risk",
        "rr",
    ):
        expected = getattr(evaluated, field)
        if isinstance(expected, tuple):
            expected = list(expected)
        assert projected[field] == pytest.approx(expected) if isinstance(expected, (int, float)) else projected[field] == expected
