from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

import numpy as np
import pytest

from a_platform_breakout import (
    LEGACY_SPEC,
    LEGACY_SECTOR_PROVENANCE,
    MATCHED_REJECTED,
    QUALIFIED_LEGACY_BASELINE,
    REJECTED_OVERHANG_RR,
    REJECTED_RR,
    REJECTED_STOP_DISTANCE,
    STRATEGY_SPEC_SHA256,
    evaluate_candidate,
    semantic_spec_sha256,
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
SYMBOL = "600000"
DEFAULT_RETRIEVED_AT = "2026-08-27T15:05:00+08:00"
EXPECTED_SPEC_SHA256 = "7ce0bf660e3ae685405e01fb9d1ef8e27e7dec44a201ab290da5d8fa8079068d"
A_CONDITIONS = (
    "PLATFORM_RANGE_LE_30_PCT",
    "CLOSE_ABOVE_PREV_60_CLOSE_HIGH",
    "VOLUME_RATIO_K_GE_1_8",
    "CHG1_GE_3_PCT",
    "CLOSE_ABOVE_MA20",
)


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
    retrieved_at: str = DEFAULT_RETRIEVED_AT,
    sector_evidence: dict[str, object] | None = None,
):
    universe = UniverseManifest(
        as_of_date=AS_OF,
        retrieved_at_bjt=retrieved_at,
        source="frozen-test-universe",
        symbols=(SYMBOL,),
    )
    quote_snapshot = QuoteSnapshotManifest(
        as_of_date=AS_OF,
        retrieved_at_bjt=retrieved_at,
        source="frozen-test-quotes",
        quotes={
            SYMBOL: {
                "code": SYMBOL,
                "quote_date": AS_OF,
                "price": float(bars[-1]["close"]),
                "turnover": 11.0,
            }
        },
    )
    stock_klines = [
        KlineManifest(
            symbol=SYMBOL,
            as_of_date=AS_OF,
            retrieved_at_bjt=retrieved_at,
            bars=bars,
        )
    ]
    index_day = date.fromisoformat(AS_OF) - timedelta(days=59)
    index = IndexManifest(
        symbol="sh000001",
        as_of_date=AS_OF,
        retrieved_at_bjt=retrieved_at,
        bars=[
            _bar(index_day + timedelta(days=index), close=3000, high=3010, low=2990, volume=1000)
            for index in range(60)
        ],
    )
    sector = SectorManifest(
        as_of_date=AS_OF,
        retrieved_at_bjt=retrieved_at,
        source="frozen-test-sector",
        definitions={"银行": {"name": "银行"}},
        members={},
        rank_input=(
            {SYMBOL: {"sector_name": "银行", "sector_rank": 5, "sector_chg": 1.5}}
            if sector_evidence is None
            else sector_evidence
        ),
    )
    return freeze_generation_inputs(
        RunContext(as_of_date=AS_OF),
        universe,
        quote_snapshot,
        stock_klines,
        index,
        sector,
    )


def _reference_v0(bars: list[dict[str, object]]) -> dict[str, object]:
    """Independent frozen-V0 formula witness; no evaluator helper is called."""

    c = np.asarray([float(item["close"]) for item in bars], dtype=float)
    v = np.asarray([float(item["volume"]) for item in bars], dtype=float)
    hi = np.asarray([float(item["high"]) for item in bars], dtype=float)
    lo = np.asarray([float(item["low"]) for item in bars], dtype=float)

    close = float(c[-1])
    ma5 = float(np.mean(c[-5:]))
    ma20 = float(np.mean(c[-20:]))
    vma20_prev = float(np.mean(v[-21:-1]))
    vol_ratio_k = float(v[-1] / vma20_prev) if vma20_prev > 0 else 0.0
    chg1 = float((c[-1] / c[-2] - 1) * 100)
    chg5 = float((c[-1] / c[-6] - 1) * 100)
    chg10 = float((c[-1] / c[-11] - 1) * 100)
    chg20 = float((c[-1] / c[-21] - 1) * 100)
    bias20 = float((close / ma20 - 1) * 100)
    llv250 = float(np.min(lo[-250:]))
    hhv250 = float(np.max(hi[-250:]))
    pos250 = float((close - llv250) / (hhv250 - llv250)) if hhv250 > llv250 else 0.5
    prev60_hi_c = float(np.max(c[-61:-1]))
    prev60_lo = float(np.min(lo[-61:-1]))
    plat_range = float((np.max(hi[-61:-1]) - prev60_lo) / prev60_lo)
    matched = all(
        (
            plat_range <= 0.30,
            close > prev60_hi_c,
            vol_ratio_k >= 1.8,
            chg1 >= 3,
            close > ma20,
        )
    )
    if not matched:
        return {"matched": False, "support": None, "stop": None, "target": None, "rr": None, "score": None}

    diff = np.diff(c[-21:])
    up_v = v[-20:][diff > 0]
    dn_v = v[-20:][diff < 0]
    ud_ratio = (
        float(np.mean(up_v) / np.mean(dn_v))
        if len(up_v) and len(dn_v) and np.mean(dn_v) > 0
        else 1.0
    )
    bp_price = prev60_hi_c
    vol_bar_lo = float(lo[-10:][int(np.argmax(v[-10:]))])
    valid_supports = [
        value
        for value in (ma20, bp_price, vol_bar_lo, float(np.min(lo[-20:])))
        if value < close
    ]
    support = float(max(valid_supports))
    stop = round(support * 0.98, 2)
    risk = float((close - stop) / close)

    bins = np.linspace(float(np.min(lo[-120:])), float(np.max(hi[-120:])), 21)
    indices = np.clip(np.digitize(c[-120:], bins) - 1, 0, 19)
    vol_by_price = np.zeros(20, dtype=float)
    for index, volume in zip(indices, v[-120:]):
        vol_by_price[int(index)] += float(volume)

    target_candidates: list[float] = []
    h60 = float(np.max(hi[-60:]))
    hhv120 = float(np.max(hi[-120:]))
    if h60 > close * 1.03:
        target_candidates.append(h60)
    above_bins = [index for index in range(20) if bins[index] > close * 1.03]
    if above_bins:
        peak_index = max(above_bins, key=lambda index: vol_by_price[index])
        target_candidates.append(float(bins[peak_index]))
    if hhv120 > close * 1.03:
        target_candidates.append(hhv120)
    target = (
        float(min(target_candidates))
        if target_candidates
        else float(close * (1 + 2.5 * risk))
    )
    rr = float((target - close) / (close - stop))

    total_vol = float(np.sum(vol_by_price))
    overhang = (
        float(np.sum(vol_by_price[bins[:-1] > close * 1.02]) / total_vol)
        if total_vol > 0
        else 0.0
    )
    rejected = (
        close <= 2
        or (chg10 > 35 and bias20 > 15)
        or (pos250 > 0.9 and chg20 > 40)
        or risk <= 0
        or risk > 0.09
        or rr < 2
        or (overhang > 0.5 and rr < 2.5)
    )
    score = None
    if not rejected:
        strong_sector = 10
        relative_low = 15 if pos250 < 0.35 and chg10 <= 30 else (10 if pos250 < 0.5 else (5 if pos250 < 0.65 else 0))
        volume_price_health = 8 if ud_ratio >= 1.3 else (5 if ud_ratio >= 1.1 else 2)
        volume_price_health += 4 if 1.5 <= vol_ratio_k <= 4 else (2 if vol_ratio_k > 4 else 1)
        volume_price_health = min(volume_price_health + 3, 15)
        clear_support = 10 if risk <= 0.04 else (6 if risk <= 0.06 else 3)
        prior_five_mean = float(np.mean(c[-6:-1]))
        five_day_strength = 5 if close > ma5 and ma5 >= prior_five_mean else (3 if close > ma5 else 0)
        sector_linkage = 10
        rs = chg5
        relative_strength = 10 if rs > 3 else (6 if rs > 0 else 2)
        risk_reward = 10 if rr >= 3 else (8 if rr >= 2.5 else 5)
        values = {
            "strong_sector": strong_sector,
            "relative_low": relative_low,
            "volume_price_health": volume_price_health,
            "clear_support": clear_support,
            "five_day_strength": five_day_strength,
            "sector_linkage": sector_linkage,
            "relative_strength": relative_strength,
            "risk_reward": risk_reward,
        }
        score = {**values, "total": sum(values.values())}
    return {"matched": True, "support": support, "stop": stop, "target": target, "rr": rr, "score": score}


def _pressure_bars() -> list[dict[str, object]]:
    bars = _base_bars()
    for item in bars[-120:-61]:
        item["close"] = 12.5
        item["high"] = 13.0
        item["low"] = 12.0
        item["volume"] = 1000
    return bars


def _rr_reject_bars() -> list[dict[str, object]]:
    bars = _base_bars()
    for item in bars[-120:-61]:
        item["high"] = 10.72
    return bars


def test_complete_semantic_spec_hash_is_pinned_and_mutation_sensitive():
    assert STRATEGY_SPEC_SHA256 == EXPECTED_SPEC_SHA256
    assert semantic_spec_sha256(LEGACY_SPEC) == EXPECTED_SPEC_SHA256
    mutated = deepcopy(LEGACY_SPEC)
    mutated["a_match"]["conditions_in_order"][2]["rhs"] = 1.81
    assert semantic_spec_sha256(mutated) != EXPECTED_SPEC_SHA256


def test_retrieved_at_only_does_not_change_semantic_evaluation_hash():
    bars = _base_bars()
    first = evaluate_candidate(_manifest(deepcopy(bars)), SYMBOL)
    second = evaluate_candidate(
        _manifest(deepcopy(bars), retrieved_at="2026-08-27T15:55:00+08:00"), SYMBOL
    )
    assert first.input_fingerprint == second.input_fingerprint
    assert first.evaluation_hash == second.evaluation_hash


@pytest.mark.parametrize("bars_factory", [_base_bars, _pressure_bars, _rr_reject_bars])
def test_independent_v0_reference_matches_evaluator_key_outputs(bars_factory):
    bars = bars_factory()
    reference = _reference_v0(deepcopy(bars))
    result = evaluate_candidate(_manifest(deepcopy(bars)), SYMBOL)
    evaluator_matched = all(name in result.matched_conditions for name in A_CONDITIONS)
    assert evaluator_matched is reference["matched"]
    if reference["support"] is None:
        assert result.support is None
    else:
        assert result.support == pytest.approx(reference["support"])
        assert result.stop == pytest.approx(reference["stop"])
        assert result.target == pytest.approx(reference["target"])
        assert result.rr == pytest.approx(reference["rr"])
    if reference["score"] is None:
        assert result.score_breakdown is None
    else:
        assert result.score_breakdown is not None
        assert result.score_breakdown.to_dict() == reference["score"]


def test_differential_witness_covers_qualified_pressure_and_rr_reject_cases():
    qualified = evaluate_candidate(_manifest(_base_bars()), SYMBOL)
    pressure = evaluate_candidate(_manifest(_pressure_bars()), SYMBOL)
    rr_reject = evaluate_candidate(_manifest(_rr_reject_bars()), SYMBOL)
    assert qualified.status == QUALIFIED_LEGACY_BASELINE
    assert pressure.status == QUALIFIED_LEGACY_BASELINE
    assert pressure.target_type == "PRESSURE"
    assert rr_reject.status == MATCHED_REJECTED
    assert rr_reject.reject_reasons == (REJECTED_RR,)


def _stop_reject_bars() -> list[dict[str, object]]:
    bars = _base_bars()
    for item in bars[:-1]:
        item["close"] = 8.2
        item["high"] = 8.4
        item["low"] = 7.8
    bars[-1]["low"] = 8.0
    return bars


def _overhang_reject_bars() -> list[dict[str, object]]:
    bars = _base_bars()
    for item in bars[-120:-61]:
        item["close"] = 11.7
        item["high"] = 11.8
        item["low"] = 11.6
        item["volume"] = 1000
    return bars


def _sector_independent_signal_identity(result):
    return {
        field_name: getattr(result, field_name)
        for field_name in (
            "symbol",
            "setup_id",
            "status",
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
            "level_plan",
        )
    }


@pytest.mark.parametrize(
    "bars_factory",
    [_base_bars, _rr_reject_bars, _stop_reject_bars, _overhang_reject_bars],
)
def test_sector_rank_and_change_do_not_change_a_gates_levels_or_qualified_identity(bars_factory):
    bars = bars_factory()
    baseline = evaluate_candidate(
        _manifest(
            deepcopy(bars),
            sector_evidence={SYMBOL: {"sector_name": "银行", "sector_rank": 5, "sector_chg": 1.5}},
        ),
        SYMBOL,
    )
    changed = evaluate_candidate(
        _manifest(
            deepcopy(bars),
            sector_evidence={SYMBOL: {"sector_name": "银行", "sector_rank": 50, "sector_chg": -1.0}},
        ),
        SYMBOL,
    )

    assert _sector_independent_signal_identity(changed) == _sector_independent_signal_identity(baseline)
    assert baseline.features is not None and changed.features is not None
    assert baseline.features.sector_rank == 5
    assert changed.features.sector_rank == 50
    assert baseline.features.sector_chg == 1.5
    assert changed.features.sector_chg == -1.0
    if baseline.status == QUALIFIED_LEGACY_BASELINE:
        assert changed.status == QUALIFIED_LEGACY_BASELINE
        assert baseline.score_total != changed.score_total
        assert baseline.score_breakdown is not None and changed.score_breakdown is not None
        assert baseline.score_breakdown.strong_sector != changed.score_breakdown.strong_sector
        assert baseline.score_breakdown.sector_linkage != changed.score_breakdown.sector_linkage
    else:
        assert baseline.score_breakdown is None
        assert changed.score_breakdown is None


def test_sector_name_changes_reported_sector_only_not_signal_or_score():
    bars = _base_bars()
    baseline = evaluate_candidate(
        _manifest(
            deepcopy(bars),
            sector_evidence={SYMBOL: {"sector_name": "银行", "sector_rank": 5, "sector_chg": 1.5}},
        ),
        SYMBOL,
    )
    changed = evaluate_candidate(
        _manifest(
            deepcopy(bars),
            sector_evidence={SYMBOL: {"sector_name": "医药", "sector_rank": 5, "sector_chg": 1.5}},
        ),
        SYMBOL,
    )

    assert _sector_independent_signal_identity(changed) == _sector_independent_signal_identity(baseline)
    assert baseline.features is not None and changed.features is not None
    assert baseline.features.sector_name == "银行"
    assert changed.features.sector_name == "医药"
    assert baseline.score_breakdown == changed.score_breakdown
    assert baseline.score_total == changed.score_total
    assert baseline.input_fingerprint != changed.input_fingerprint


def test_legacy_sector_provenance_is_exact_and_taxonomy_substitution_is_explicitly_forbidden():
    assert LEGACY_SECTOR_PROVENANCE == {
        "version": "V0",
        "getter": "get_sectors",
        "provider": "AKShare",
        "taxonomy": "新浪行业",
        "spot_method": "stock_sector_spot",
        "detail_method": "stock_sector_detail",
        "exact_legacy_taxonomy": True,
        "forbidden_substitutions": ["申万行业", "同花顺行业"],
    }
    result = evaluate_candidate(_manifest(_base_bars()), SYMBOL)
    assert result.provenance["legacy_sector_provenance"] == LEGACY_SECTOR_PROVENANCE


def test_acceleration_reject_records_all_prior_passed_gates():
    bars = _base_bars()
    bars[-11]["close"] = 10.0
    bars[-1] = _bar(date.fromisoformat(AS_OF), close=14.0, high=14.2, low=13.8, volume=200)
    result = evaluate_candidate(_manifest(bars), SYMBOL)
    assert result.matched_conditions == A_CONDITIONS + ("SECTOR_EVIDENCE_COMPLETE", "CLOSE_GT_2")
    assert result.failed_conditions == ("NO_ACCELERATION_OVEREXTENDED",)


def test_gain_exhausted_reject_records_acceleration_pass():
    bars = _base_bars()
    bars[-11]["close"] = 11.2
    bars[-1] = _bar(date.fromisoformat(AS_OF), close=15.0, high=15.2, low=14.8, volume=200)
    result = evaluate_candidate(_manifest(bars), SYMBOL)
    assert result.matched_conditions[-3:] == (
        "SECTOR_EVIDENCE_COMPLETE",
        "CLOSE_GT_2",
        "NO_ACCELERATION_OVEREXTENDED",
    )
    assert result.failed_conditions == ("NO_GAIN_EXHAUSTED",)


def test_stop_distance_reject_records_support_gate_pass():
    bars = _base_bars()
    for item in bars[:-1]:
        item["close"] = 8.2
        item["high"] = 8.4
        item["low"] = 7.8
    bars[-1]["low"] = 8.0
    result = evaluate_candidate(_manifest(bars), SYMBOL)
    assert result.reject_reasons == (REJECTED_STOP_DISTANCE,)
    assert result.matched_conditions[-1] == "VALID_SUPPORT_EXISTS"
    assert result.failed_conditions == ("RISK_IN_0_TO_9_PCT",)


def test_rr_reject_records_all_prior_hard_gate_passes():
    result = evaluate_candidate(_manifest(_rr_reject_bars()), SYMBOL)
    assert result.reject_reasons == (REJECTED_RR,)
    assert result.matched_conditions == A_CONDITIONS + (
        "SECTOR_EVIDENCE_COMPLETE",
        "CLOSE_GT_2",
        "NO_ACCELERATION_OVEREXTENDED",
        "NO_GAIN_EXHAUSTED",
        "VALID_SUPPORT_EXISTS",
        "RISK_IN_0_TO_9_PCT",
    )
    assert result.failed_conditions == ("RR_GE_2",)


def test_overhang_reject_records_rr_gate_pass():
    bars = _base_bars()
    for item in bars[-120:-61]:
        item["close"] = 11.7
        item["high"] = 11.8
        item["low"] = 11.6
        item["volume"] = 1000
    result = evaluate_candidate(_manifest(bars), SYMBOL)
    assert result.reject_reasons == (REJECTED_OVERHANG_RR,)
    assert result.matched_conditions[-1] == "RR_GE_2"
    assert result.failed_conditions == ("OVERHANG_RR_COMBINATION_ACCEPTED",)
