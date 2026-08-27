from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

import pytest

from a_platform_breakout import (
    ACCELERATION_OVEREXTENDED,
    GAIN_EXHAUSTED,
    INSUFFICIENT_DATA,
    MATCHED_REJECTED,
    MISSING_SECTOR_EVIDENCE,
    NOT_MATCHED,
    QUALIFIED_LEGACY_BASELINE,
    REJECTED_CLOSE_TOO_LOW,
    REJECTED_OVERHANG_RR,
    REJECTED_RR,
    REJECTED_STOP_DISTANCE,
    evaluate_candidate,
    evaluate_universe,
    strategy_spec_sha256,
)
from generation_contract import (
    IndexManifest,
    KlineManifest,
    QuoteSnapshotManifest,
    RunContext,
    SectorManifest,
    UniverseManifest,
    freeze_generation_inputs,
)


AS_OF = "2026-08-27"
RETRIEVED_AT = "2026-08-27T15:05:00+08:00"
SYMBOL = "600000"


def _bar(day: date, *, close: float, high: float, low: float, volume: float) -> dict[str, object]:
    return {
        "date": day.isoformat(),
        "open": close,
        "close": close,
        "high": high,
        "low": low,
        "volume": volume,
    }


def _base_bars() -> list[dict[str, object]]:
    first_day = date.fromisoformat(AS_OF) - timedelta(days=259)
    bars = [
        _bar(first_day + timedelta(days=index), close=10.0, high=10.2, low=9.5, volume=100)
        for index in range(260)
    ]
    bars[-1] = _bar(date.fromisoformat(AS_OF), close=10.4, high=10.5, low=10.0, volume=200)
    return bars


def _manifest(
    bars: list[dict[str, object]],
    *,
    sector_evidence: dict[str, object] | None = None,
    symbols: tuple[str, ...] = (SYMBOL,),
    quote_updates: dict[str, object] | None = None,
    bar_count_override: int | None = None,
):
    sector_evidence = (
        {SYMBOL: {"sector_name": "银行", "sector_rank": 5, "sector_chg": 1.5}}
        if sector_evidence is None
        else sector_evidence
    )
    universe = UniverseManifest(
        as_of_date=AS_OF,
        retrieved_at_bjt=RETRIEVED_AT,
        source="frozen-test-universe",
        symbols=symbols,
    )
    quotes: dict[str, dict[str, object]] = {}
    for symbol in symbols:
        quote: dict[str, object] = {
            "code": symbol,
            "quote_date": AS_OF,
            "price": 10.4,
            "turnover": 11.0,
        }
        if quote_updates and symbol == SYMBOL:
            quote.update(quote_updates)
        quotes[symbol] = quote
    quote_snapshot = QuoteSnapshotManifest(
        as_of_date=AS_OF,
        retrieved_at_bjt=RETRIEVED_AT,
        source="frozen-test-quotes",
        quotes=quotes,
    )
    stock_klines = []
    for symbol in symbols:
        stock_bars = bars if symbol == SYMBOL else deepcopy(bars)
        if bar_count_override is not None and symbol == SYMBOL:
            stock_bars = stock_bars[-bar_count_override:]
        stock_klines.append(
            KlineManifest(
                symbol=symbol,
                as_of_date=AS_OF,
                retrieved_at_bjt=RETRIEVED_AT,
                bars=stock_bars,
            )
        )
    index_day = date.fromisoformat(AS_OF) - timedelta(days=59)
    index = IndexManifest(
        symbol="sh000001",
        as_of_date=AS_OF,
        retrieved_at_bjt=RETRIEVED_AT,
        bars=[
            _bar(index_day + timedelta(days=index), close=3000, high=3010, low=2990, volume=1000)
            for index in range(60)
        ],
    )
    sector = SectorManifest(
        as_of_date=AS_OF,
        retrieved_at_bjt=RETRIEVED_AT,
        source="frozen-test-sector",
        definitions={"银行": {"name": "银行"}},
        members={},
        rank_input=sector_evidence,
    )
    return freeze_generation_inputs(
        RunContext(as_of_date=AS_OF),
        universe,
        quote_snapshot,
        stock_klines,
        index,
        sector,
    )


def _evaluate(bars: list[dict[str, object]] | None = None, **kwargs):
    return evaluate_candidate(_manifest(_base_bars() if bars is None else bars, **kwargs), SYMBOL)


def test_platform_range_exactly_30_percent_passes_that_condition():
    bars = _base_bars()
    for item in bars[-61:-1]:
        item["high"] = 9.5 * 1.30
    result = _evaluate(bars)
    assert result.features is not None
    assert result.features.plat_range == pytest.approx(0.30)
    assert "PLATFORM_RANGE_LE_30_PCT" in result.matched_conditions


def test_platform_range_over_30_percent_does_not_match():
    bars = _base_bars()
    for item in bars[-61:-1]:
        item["high"] = 12.36
    result = _evaluate(bars)
    assert result.status == NOT_MATCHED
    assert "PLATFORM_RANGE_LE_30_PCT" in result.failed_conditions


def test_volume_ratio_exactly_1_8_passes():
    bars = _base_bars()
    bars[-1]["volume"] = 180
    result = _evaluate(bars)
    assert result.features is not None
    assert result.features.vol_ratio_k == pytest.approx(1.8)
    assert result.status == QUALIFIED_LEGACY_BASELINE


def test_one_day_change_exactly_3_percent_passes():
    bars = _base_bars()
    bars[-1] = _bar(date.fromisoformat(AS_OF), close=10.3, high=10.4, low=10.0, volume=180)
    result = _evaluate(bars)
    assert result.features is not None
    assert result.features.chg1 == pytest.approx(3.0)
    assert "CHG1_GE_3_PCT" in result.matched_conditions


def test_close_not_above_previous_60_close_high_is_not_matched():
    bars = _base_bars()
    bars[-1] = _bar(date.fromisoformat(AS_OF), close=10.0, high=10.2, low=9.8, volume=200)
    result = _evaluate(bars)
    assert result.status == NOT_MATCHED
    assert "CLOSE_ABOVE_PREV_60_CLOSE_HIGH" in result.failed_conditions


def test_close_at_or_below_two_is_a_legacy_hard_reject():
    bars = _base_bars()
    for item in bars:
        item["close"] = float(item["close"]) * 0.15
        item["high"] = float(item["high"]) * 0.15
        item["low"] = float(item["low"]) * 0.15
    result = _evaluate(bars)
    assert result.status == MATCHED_REJECTED
    assert result.reject_reasons == (REJECTED_CLOSE_TOO_LOW,)


def test_fewer_than_120_bars_is_insufficient_data():
    result = _evaluate(bar_count_override=119)
    assert result.status == INSUFFICIENT_DATA
    assert result.reject_reasons == (INSUFFICIENT_DATA,)


def test_acceleration_reject():
    bars = _base_bars()
    bars[-11]["close"] = 10.0
    bars[-1] = _bar(date.fromisoformat(AS_OF), close=14.0, high=14.2, low=13.8, volume=200)
    result = _evaluate(bars)
    assert result.status == MATCHED_REJECTED
    assert result.reject_reasons == (ACCELERATION_OVEREXTENDED,)


def test_gain_exhausted_reject():
    bars = _base_bars()
    bars[-11]["close"] = 11.2
    bars[-1] = _bar(date.fromisoformat(AS_OF), close=15.0, high=15.2, low=14.8, volume=200)
    result = _evaluate(bars)
    assert result.status == MATCHED_REJECTED
    assert result.reject_reasons == (GAIN_EXHAUSTED,)


def test_support_uses_the_nearest_valid_candidate_and_stop_is_two_percent_below_it():
    bars = _base_bars()
    for item in bars[-20:-1]:
        item["close"] = 10.1
        item["high"] = 10.2
    bars[-1] = _bar(date.fromisoformat(AS_OF), close=10.5, high=10.6, low=10.0, volume=200)
    result = _evaluate(bars)
    assert result.features is not None
    assert result.support == pytest.approx(result.features.ma20)
    assert result.support > result.features.prev60_hi_c
    assert result.stop == pytest.approx(round(result.support * 0.98, 2))


def test_risk_above_nine_percent_is_rejected():
    bars = _base_bars()
    for item in bars[:-1]:
        item["close"] = 8.2
        item["high"] = 8.4
        item["low"] = 7.8
    bars[-1]["low"] = 8.0
    result = _evaluate(bars)
    assert result.status == MATCHED_REJECTED
    assert result.reject_reasons == (REJECTED_STOP_DISTANCE,)


def test_pressure_target_is_selected():
    bars = _base_bars()
    for item in bars[-120:-61]:
        item["close"] = 12.5
        item["high"] = 13.0
        item["low"] = 12.0
        item["volume"] = 1000
    result = _evaluate(bars)
    assert result.status == QUALIFIED_LEGACY_BASELINE
    assert result.target_type == "PRESSURE"
    assert result.target is not None and result.target > result.features.close * 1.03


def test_without_pressure_target_uses_2_5r():
    result = _evaluate()
    assert result.status == QUALIFIED_LEGACY_BASELINE
    assert result.target_type == "TREND_2_5R"
    assert result.rr == pytest.approx(2.5)


def test_rr_below_two_is_rejected():
    bars = _base_bars()
    for item in bars[-120:-61]:
        item["high"] = 10.72
    result = _evaluate(bars)
    assert result.status == MATCHED_REJECTED
    assert result.reject_reasons == (REJECTED_RR,)


def test_overhang_above_50_percent_with_rr_below_2_5_is_rejected():
    bars = _base_bars()
    for item in bars[-120:-61]:
        item["close"] = 11.7
        item["high"] = 11.8
        item["low"] = 11.6
        item["volume"] = 1000
    result = _evaluate(bars)
    assert result.features is not None
    assert result.features.overhang > 0.5
    assert result.rr is not None and 2 <= result.rr < 2.5
    assert result.reject_reasons == (REJECTED_OVERHANG_RR,)


def test_score_breakdown_golden_case_is_complete():
    result = _evaluate()
    assert result.score_total == 55
    assert result.score_breakdown is not None
    assert result.score_breakdown.to_dict() == {
        "strong_sector": 10,
        "relative_low": 0,
        "volume_price_health": 9,
        "clear_support": 6,
        "five_day_strength": 5,
        "sector_linkage": 10,
        "relative_strength": 10,
        "risk_reward": 5,
        "total": 55,
    }
    assert result.risk_flags == ("HIGH_TURNOVER",)


def test_missing_sector_evidence_is_insufficient_data_without_silent_fallback():
    result = _evaluate(sector_evidence={})
    assert result.status == INSUFFICIENT_DATA
    assert result.reject_reasons == (MISSING_SECTOR_EVIDENCE,)
    assert result.features is None


def test_t_plus_one_execution_metadata_is_preserved():
    manifest = _manifest(_base_bars())
    result = evaluate_candidate(manifest, SYMBOL)
    assert result.signal_date == AS_OF
    assert result.earliest_execution_date == manifest.earliest_execution_date
    assert result.provenance["earliest_execution_date"] == manifest.earliest_execution_date
    assert "retrieved_at_bjt" not in result.provenance


def test_same_input_has_same_evaluation_hash_and_spec_hash_is_stable():
    first = evaluate_candidate(_manifest(_base_bars()), SYMBOL)
    second = evaluate_candidate(_manifest(_base_bars()), SYMBOL)
    assert first.to_dict() == second.to_dict()
    assert first.evaluation_hash == second.evaluation_hash
    assert len(strategy_spec_sha256()) == 64


def test_input_fingerprint_change_changes_evaluation_provenance_and_hash():
    first = evaluate_candidate(_manifest(_base_bars()), SYMBOL)
    changed = evaluate_candidate(
        _manifest(_base_bars(), quote_updates={"price": 999.0}), SYMBOL
    )
    assert first.input_fingerprint != changed.input_fingerprint
    assert first.provenance["input_fingerprint"] != changed.provenance["input_fingerprint"]
    assert first.evaluation_hash != changed.evaluation_hash


def test_batch_returns_stable_per_symbol_audits_without_selection():
    manifest = _manifest(_base_bars(), symbols=("600001", "600000"))
    results = evaluate_universe(manifest)
    assert [result.symbol for result in results] == ["600000", "600001"]
    assert all(result.setup_id == "A_PLATFORM_BREAKOUT" for result in results)
    assert not hasattr(results, "watchlist")
