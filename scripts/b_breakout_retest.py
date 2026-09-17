"""Research-only reconstruction of the fixed V0 B breakout-retest rule.

This module consumes the existing Phase 2B ``GenerationInputManifest``.  It
does not change A's evaluator, production generation, frozen inputs, or any
promotion state.  The formula is reproduced from the fixed V0
``screen_system.py`` source and is intentionally versioned independently as a
candidate-bound research implementation.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from a_platform_breakout import (
    ACCELERATION_OVEREXTENDED,
    CandidateEvaluation,
    FeatureSnapshot,
    GAIN_EXHAUSTED,
    INSUFFICIENT_DATA,
    LEGACY_SECTOR_PROVENANCE,
    LevelPlan,
    MATCHED_REJECTED,
    MISSING_SECTOR_EVIDENCE,
    NOT_MATCHED,
    QUALIFIED_LEGACY_BASELINE,
    REJECTED_CLOSE_TOO_LOW,
    REJECTED_NO_SUPPORT,
    REJECTED_OVERHANG_RR,
    REJECTED_RR,
    REJECTED_STOP_DISTANCE,
    ScoreBreakdown,
    StrategyInputError,
    _bar_number,
    _canonical_json,
    _index_change,
    _optional_quote_number,
    _same_symbol,
    _sector_evidence,
    _sha256,
    _volume_distribution,
    LEGACY_SPEC as A_LEGACY_SPEC,
    semantic_spec_sha256,
)
from generation_contract import GenerationInputManifest, READY_FOR_STRATEGY_EVALUATION


STRATEGY_VERSION = "B_BREAKOUT_RETEST_LEGACY_V1"
B_BREAKOUT_RETEST_LEGACY_V1 = STRATEGY_VERSION
SETUP_ID = "B_BREAKOUT_RETEST"
V0_SOURCE_COMMIT = "c8406c393c0b135eafb0aec763576ae869fddcff"
V0_SOURCE_FILE_SHA256 = "6CAC746123E315199CBEEB1A612868EF77B50AF6C7C64B0D80EB387AE1D19F9"


# Start from the already audited common legacy levels and replace only the
# strategy identity and setup-specific rule.  The resulting object is the
# canonical semantic identity for this candidate, not a source-code hash.
LEGACY_SPEC: dict[str, Any] = copy.deepcopy(A_LEGACY_SPEC)
LEGACY_SPEC["identity"] = {
    "strategy_version": STRATEGY_VERSION,
    "setup_id": SETUP_ID,
    "role": "RESEARCH_ONLY_LEGACY_CANDIDATE_RECONSTRUCTION",
}
LEGACY_SPEC["legacy_source"] = {
    "repository": "EFSing/ashare_watchlist-V0",
    "commit": V0_SOURCE_COMMIT,
    "path": "ashare_watchlist/scripts/screen_system.py",
    "file_sha256": V0_SOURCE_FILE_SHA256.lower(),
    "rule_label": "B 突破回踩",
}
LEGACY_SPEC.pop("a_match", None)
LEGACY_SPEC["b_match"] = {
    "scan_window": "range(max(61,n-15),n-1)",
    "first_qualifying_breakout_only": True,
    "breakout": {
        "base_hi": "max(close[i-60:i])",
        "close_above_base": "close[i]>base_hi",
        "volume": "volume[i]>=1.8*mean(volume[i-20:i])",
        "one_day_change": "close[i]/close[i-1]-1>=0.03",
    },
    "pullback": {
        "pull_volume": "mean(volume[i+1:]) if n-1>i+1 else volume[-1]",
        "near_platform": "abs(close/base_hi-1)<=0.04 or base_hi*0.97<=close<=base_hi*1.04",
        "close_floor": "close>=base_hi*0.97",
        "volume_contraction": "pull_volume<volume[i]*0.7",
        "turn_strength": "close>=close[-2] or close>=ma5",
    },
    "output": "(B 突破回踩, base_hi)",
    "break_after_first_qualifying_breakout": True,
}
LEGACY_SPEC["score_85"] = copy.deepcopy(LEGACY_SPEC["score_85"])
LEGACY_SPEC["score_85"]["volume_price_health"]["rules"] = [
    "ud_ratio>=1.3:8",
    "ud_ratio>=1.1:5",
    "else:2",
    "1.5<=vol_ratio_k<=4:4",
    "vol_ratio_k>4:2",
    "else:1",
    "B_setup:+2",
    "cap:15",
]
LEGACY_SPEC["status_vocabulary"] = {
    NOT_MATCHED: "B breakout-retest conditions not all satisfied",
    INSUFFICIENT_DATA: "required coverage/numeric/sector evidence incomplete",
    MATCHED_REJECTED: "B matched but a legacy hard gate rejected",
    QUALIFIED_LEGACY_BASELINE: "B matched and all legacy hard gates passed",
}
STRATEGY_SPEC_SHA256 = semantic_spec_sha256(LEGACY_SPEC)
STRATEGY_SPEC_HASH = STRATEGY_SPEC_SHA256


def strategy_spec_sha256() -> str:
    return STRATEGY_SPEC_SHA256


def _provenance(manifest: GenerationInputManifest) -> dict[str, Any]:
    return {
        "strategy_version": STRATEGY_VERSION,
        "spec_sha256": STRATEGY_SPEC_SHA256,
        "input_fingerprint": manifest.input_fingerprint,
        "as_of_date": manifest.run_context.as_of_date,
        "signal_date": manifest.signal_date,
        "earliest_execution_date": manifest.earliest_execution_date,
        "mode": manifest.run_context.mode,
        "timezone": manifest.run_context.timezone,
        "calendar": manifest.run_context.calendar,
        "adjustment_modes": sorted({x.adjustment_mode for x in (*manifest.stock_klines, manifest.index)}),
        "input_sector_source": manifest.sector.source,
        "legacy_sector_provenance": copy.deepcopy(LEGACY_SECTOR_PROVENANCE),
        "legacy_source": {
            "repository": "EFSing/ashare_watchlist-V0",
            "commit": V0_SOURCE_COMMIT,
            "path": "ashare_watchlist/scripts/screen_system.py",
            "file_sha256": V0_SOURCE_FILE_SHA256.lower(),
            "rule_label": "B 突破回踩",
        },
    }


def _base_result(
    manifest: GenerationInputManifest,
    symbol: str,
    *,
    status: str,
    features: FeatureSnapshot | None = None,
    matched: Sequence[str] = (),
    failed: Sequence[str] = (),
    rejects: Sequence[str] = (),
    level_plan: LevelPlan | None = None,
    score: ScoreBreakdown | None = None,
    risk_flags: Sequence[str] = (),
) -> CandidateEvaluation:
    return CandidateEvaluation(
        strategy_version=STRATEGY_VERSION,
        input_fingerprint=manifest.input_fingerprint or "",
        as_of_date=manifest.run_context.as_of_date,
        signal_date=manifest.signal_date,
        earliest_execution_date=manifest.earliest_execution_date or "",
        symbol=symbol,
        setup_id=SETUP_ID,
        status=status,
        features=features,
        matched_conditions=tuple(matched),
        failed_conditions=tuple(failed),
        reject_reasons=tuple(rejects),
        support=None if level_plan is None else level_plan.support,
        trigger=None if level_plan is None else level_plan.trigger,
        stop=None if level_plan is None else level_plan.stop,
        target=None if level_plan is None else level_plan.target,
        target_type=None if level_plan is None else level_plan.target_type,
        risk=None if level_plan is None else level_plan.risk,
        rr=None if level_plan is None else level_plan.rr,
        score_breakdown=score,
        score_total=None if score is None else score.total,
        risk_flags=tuple(risk_flags),
        level_plan=level_plan,
        provenance=_provenance(manifest),
    )


def _require_manifest(manifest: GenerationInputManifest) -> None:
    if not isinstance(manifest, GenerationInputManifest):
        raise StrategyInputError("manifest must be a GenerationInputManifest")
    if manifest.status != READY_FOR_STRATEGY_EVALUATION:
        raise StrategyInputError("strategy evaluation requires status=READY_FOR_STRATEGY_EVALUATION")


def _b_match(
    c: np.ndarray,
    v: np.ndarray,
    ma5: float,
) -> tuple[float | None, list[str], list[str]]:
    """Return the first V0 B setup, preserving its unconditional break."""

    n = len(c)
    close = float(c[-1])
    for i in range(max(61, n - 15), n - 1):
        base_hi = float(np.max(c[i - 60:i]))
        breakout_pairs = (
            ("BREAKOUT_CLOSE_ABOVE_60D_HIGH", float(c[i]) > base_hi),
            ("BREAKOUT_VOLUME_GE_1_8_PREV_20_MEAN", float(v[i]) >= 1.8 * float(np.mean(v[i - 20:i]))),
            ("BREAKOUT_CHG1_GE_3_PCT", float(c[i] / c[i - 1] - 1) >= 0.03),
        )
        if not all(passed for _, passed in breakout_pairs):
            continue

        pull_v = float(np.mean(v[i + 1:])) if n - 1 > i + 1 else float(v[-1])
        pullback_pairs = (
            ("PULLBACK_CLOSE_GE_97_PCT_BASE", close >= base_hi * 0.97),
            ("PULLBACK_WITHIN_PLATFORM_4_PCT", abs(close / base_hi - 1) <= 0.04 or base_hi * 0.97 <= close <= base_hi * 1.04),
            ("PULLBACK_VOLUME_LT_70_PCT_BREAKOUT", pull_v < float(v[i]) * 0.7),
            ("PULLBACK_TURNED_STRONG", close >= float(c[-2]) or close >= ma5),
        )
        matched = [name for name, passed in (*breakout_pairs, *pullback_pairs) if passed]
        failed = [name for name, passed in (*breakout_pairs, *pullback_pairs) if not passed]
        if not failed:
            return base_hi, matched, failed
        # Fixed V0 behavior: the first qualifying breakout ends the scan even
        # when its later pullback test fails.
        return None, matched, failed
    return None, [], ["NO_QUALIFYING_BREAKOUT_WITHIN_15_SESSIONS"]


def _score_b(
    *,
    sector_rank: float,
    pos250: float,
    chg10: float,
    ud_ratio: float,
    vol_ratio_k: float,
    risk: float,
    close: float,
    ma5: float,
    prior_five_mean: float,
    sector_chg: float,
    rs: float,
    rr: float,
) -> ScoreBreakdown:
    strong_sector = 10 if sector_rank <= 10 else (6 if sector_rank <= 20 else 2)
    relative_low = 15 if pos250 < 0.35 and chg10 <= 30 else (10 if pos250 < 0.5 else (5 if pos250 < 0.65 else 0))
    volume_price_health = 8 if ud_ratio >= 1.3 else (5 if ud_ratio >= 1.1 else 2)
    volume_price_health += 4 if 1.5 <= vol_ratio_k <= 4 else (2 if vol_ratio_k > 4 else 1)
    volume_price_health = min(volume_price_health + 2, 15)
    clear_support = 10 if risk <= 0.04 else (6 if risk <= 0.06 else 3)
    five_day_strength = 5 if close > ma5 and ma5 >= prior_five_mean else (3 if close > ma5 else 0)
    sector_linkage = 10 if sector_chg >= 1 else (5 if sector_chg > 0 else 1)
    relative_strength = 10 if rs > 3 else (6 if rs > 0 else 2)
    risk_reward = 10 if rr >= 3 else (8 if rr >= 2.5 else 5)
    values = (strong_sector, relative_low, volume_price_health, clear_support, five_day_strength, sector_linkage, relative_strength, risk_reward)
    return ScoreBreakdown(strong_sector, relative_low, volume_price_health, clear_support, five_day_strength, sector_linkage, relative_strength, risk_reward, sum(values))


def _evaluate_arrays(
    *,
    manifest: GenerationInputManifest,
    symbol: str,
    bars: Sequence[Mapping[str, Any]],
    quote: Mapping[str, Any],
    sector_name: str,
    sector_rank: float,
    sector_chg: float,
) -> CandidateEvaluation:
    c = np.asarray([_bar_number(bar, "close") for bar in bars], dtype=float)
    v = np.asarray([_bar_number(bar, "volume") for bar in bars], dtype=float)
    hi = np.asarray([_bar_number(bar, "high") for bar in bars], dtype=float)
    lo = np.asarray([_bar_number(bar, "low") for bar in bars], dtype=float)
    if np.any(v < 0) or np.any(c <= 0) or np.any(hi <= 0) or np.any(lo <= 0):
        raise ValueError("kline prices must be positive and volumes non-negative")

    close = float(c[-1])
    ma5, ma20 = float(np.mean(c[-5:])), float(np.mean(c[-20:]))
    vma20_prev = float(np.mean(v[-21:-1]))
    vol_ratio_k = float(v[-1] / vma20_prev) if vma20_prev > 0 else 0.0
    chg1 = float((c[-1] / c[-2] - 1) * 100)
    chg5 = float((c[-1] / c[-6] - 1) * 100)
    chg10 = float((c[-1] / c[-11] - 1) * 100)
    chg20 = float((c[-1] / c[-21] - 1) * 100)
    bias20 = float((close / ma20 - 1) * 100)
    llv250, hhv250 = float(np.min(lo[-250:])), float(np.max(hi[-250:]))
    pos250 = float((close - llv250) / (hhv250 - llv250)) if hhv250 > llv250 else 0.5
    diff = np.diff(c[-21:])
    up_v, dn_v = v[-20:][diff > 0], v[-20:][diff < 0]
    ud_ratio = float(np.mean(up_v) / np.mean(dn_v)) if len(up_v) and len(dn_v) and np.mean(dn_v) > 0 else 1.0
    prev60_hi_c, prev60_lo = float(np.max(c[-61:-1])), float(np.min(lo[-61:-1]))
    plat_range = float((np.max(hi[-61:-1]) - prev60_lo) / prev60_lo)
    idx_chg5 = _index_change(manifest.index.bars)
    rs = float(chg5 - idx_chg5)
    bins, vol_by_price, _ = _volume_distribution(lo, hi, c, v)
    h60, hhv120 = float(np.max(hi[-60:])), float(np.max(hi[-120:]))
    total_vol = float(np.sum(vol_by_price))
    overhang = float(np.sum(vol_by_price[bins[:-1] > close * 1.02]) / total_vol) if total_vol > 0 else 0.0
    turnover = _optional_quote_number(quote, "turnover", "换手率")
    features = FeatureSnapshot(
        str(symbol).strip().lower(), close, ma5, ma20, vma20_prev, vol_ratio_k,
        chg1, chg5, chg10, chg20, bias20, llv250, hhv250, pos250,
        prev60_hi_c, prev60_lo, plat_range, ud_ratio,
        float(lo[-10:][int(np.argmax(v[-10:]))]), h60, hhv120, overhang,
        idx_chg5, rs, turnover, sector_name, sector_rank, sector_chg,
        tuple(float(x) for x in bins), tuple(float(x) for x in vol_by_price), (),
    )

    bp_price, matched, failed = _b_match(c, v, ma5)
    if bp_price is None:
        return _base_result(manifest, symbol, status=NOT_MATCHED, features=features, matched=matched, failed=failed)

    matched.append("SECTOR_EVIDENCE_COMPLETE")
    if close <= 2:
        return _base_result(manifest, symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("CLOSE_GT_2",), rejects=(REJECTED_CLOSE_TOO_LOW,))
    matched.append("CLOSE_GT_2")
    if chg10 > 35 and bias20 > 15:
        return _base_result(manifest, symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("NO_ACCELERATION_OVEREXTENDED",), rejects=(ACCELERATION_OVEREXTENDED,))
    matched.append("NO_ACCELERATION_OVEREXTENDED")
    if pos250 > 0.9 and chg20 > 40:
        return _base_result(manifest, symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("NO_GAIN_EXHAUSTED",), rejects=(GAIN_EXHAUSTED,))
    matched.append("NO_GAIN_EXHAUSTED")

    support_candidates = [ma20, bp_price, features.vol_bar_lo, float(np.min(lo[-20:]))]
    valid_supports = [value for value in support_candidates if value < close]
    if not valid_supports:
        return _base_result(manifest, symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("VALID_SUPPORT_EXISTS",), rejects=(REJECTED_NO_SUPPORT,))
    matched.append("VALID_SUPPORT_EXISTS")
    support = float(max(valid_supports))
    stop = round(support * 0.98, 2)
    risk = float((close - stop) / close)
    if risk <= 0 or risk > 0.09:
        return _base_result(manifest, symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("RISK_IN_0_TO_9_PCT",), rejects=(REJECTED_STOP_DISTANCE,))
    matched.append("RISK_IN_0_TO_9_PCT")

    target_candidates: list[float] = []
    if h60 > close * 1.03:
        target_candidates.append(h60)
    above_bin_indices = [index for index in range(20) if bins[index] > close * 1.03]
    if above_bin_indices:
        peak_index = max(above_bin_indices, key=lambda index: vol_by_price[index])
        target_candidates.append(float(bins[peak_index]))
    if hhv120 > close * 1.03:
        target_candidates.append(hhv120)
    if target_candidates:
        target, target_type = float(min(target_candidates)), "PRESSURE"
    else:
        target, target_type = float(close * (1 + 2.5 * risk)), "TREND_2_5R"
    rr = float((target - close) / (close - stop))
    features = FeatureSnapshot(**{**features.__dict__, "target_candidates": tuple(target_candidates)})
    level_plan = LevelPlan(support, round(max(bp_price, ma5), 2), stop, target, target_type, risk, rr, overhang)
    if rr < 2:
        return _base_result(manifest, symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("RR_GE_2",), rejects=(REJECTED_RR,), level_plan=level_plan)
    matched.append("RR_GE_2")
    if overhang > 0.5 and rr < 2.5:
        return _base_result(manifest, symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("OVERHANG_RR_COMBINATION_ACCEPTED",), rejects=(REJECTED_OVERHANG_RR,), level_plan=level_plan)
    matched.append("OVERHANG_RR_COMBINATION_ACCEPTED")
    score = _score_b(
        sector_rank=sector_rank, pos250=pos250, chg10=chg10, ud_ratio=ud_ratio,
        vol_ratio_k=vol_ratio_k, risk=risk, close=close, ma5=ma5,
        prior_five_mean=float(np.mean(c[-6:-1])), sector_chg=sector_chg, rs=rs, rr=rr,
    )
    risk_flags: list[str] = []
    if turnover is not None and turnover > 10:
        risk_flags.append("HIGH_TURNOVER")
    if overhang > 0.35:
        risk_flags.append("OVERHANG")
    if chg20 > 30:
        risk_flags.append("TWENTY_DAY_GAIN")
    return _base_result(manifest, symbol, status=QUALIFIED_LEGACY_BASELINE, features=features, matched=matched, score=score, risk_flags=risk_flags, level_plan=level_plan)


def evaluate_candidate(manifest: GenerationInputManifest, symbol: str) -> CandidateEvaluation:
    """Evaluate one symbol under the exact B rule from a ready manifest."""

    _require_manifest(manifest)
    normalized_symbol = str(symbol).strip().lower()
    kline_by_symbol = {item.symbol: item for item in manifest.stock_klines}
    if normalized_symbol not in kline_by_symbol:
        raise StrategyInputError(f"symbol is not present in manifest universe: {symbol}")
    item = kline_by_symbol[normalized_symbol]
    if item.bar_count < 120:
        return _base_result(manifest, normalized_symbol, status=INSUFFICIENT_DATA, failed=("MINIMUM_BARS_120",), rejects=(INSUFFICIENT_DATA,))
    quote = manifest.quote_snapshot.quotes.get(normalized_symbol)
    evidence = _sector_evidence(manifest, normalized_symbol)
    try:
        if quote is None:
            raise ValueError("quote is missing")
        if len(manifest.index.bars) < 6:
            raise ValueError("index has fewer than six bars")
        if evidence is None:
            return _base_result(manifest, normalized_symbol, status=INSUFFICIENT_DATA, failed=("SECTOR_EVIDENCE_COMPLETE",), rejects=(MISSING_SECTOR_EVIDENCE,))
        sector_name, sector_rank, sector_chg = evidence
        return _evaluate_arrays(
            manifest=manifest,
            symbol=normalized_symbol,
            bars=item.bars,
            quote=quote,
            sector_name=sector_name,
            sector_rank=sector_rank,
            sector_chg=sector_chg,
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return _base_result(manifest, normalized_symbol, status=INSUFFICIENT_DATA, failed=("NUMERIC_INPUT_COMPLETE",), rejects=(INSUFFICIENT_DATA,))


def evaluate_universe(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    _require_manifest(manifest)
    return tuple(evaluate_candidate(manifest, symbol) for symbol in manifest.universe.symbols)


def evaluate_numeric_projection(
    *,
    symbol: str,
    signal_date: str,
    earliest_execution_date: str,
    bars: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    index_bars: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Fast projection-equivalent path used only after manifest parity tests.

    This intentionally carries only the fields needed by the frozen replay
    and outcome validator.  The full public evaluator remains the immutable
    Phase 2B-manifest entry point.
    """

    c, v, hi, lo = bars
    close = float(c[-1])
    ma5, ma20 = float(np.mean(c[-5:])), float(np.mean(c[-20:]))
    vma20_prev = float(np.mean(v[-21:-1]))
    chg1 = float((c[-1] / c[-2] - 1) * 100)
    chg5 = float((c[-1] / c[-6] - 1) * 100)
    chg10 = float((c[-1] / c[-11] - 1) * 100)
    chg20 = float((c[-1] / c[-21] - 1) * 100)
    bias20 = float((close / ma20 - 1) * 100)
    llv250, hhv250 = float(np.min(lo[-250:])), float(np.max(hi[-250:]))
    pos250 = float((close - llv250) / (hhv250 - llv250)) if hhv250 > llv250 else 0.5
    bins, vol_by_price, _ = _volume_distribution(lo, hi, c, v)
    h60, hhv120 = float(np.max(hi[-60:])), float(np.max(hi[-120:]))
    total_vol = float(np.sum(vol_by_price))
    overhang = float(np.sum(vol_by_price[bins[:-1] > close * 1.02]) / total_vol) if total_vol > 0 else 0.0
    base_hi, matched, failed = _b_match(c, v, ma5)
    base = {
        "as_of_date": signal_date,
        "signal_date": signal_date,
        "earliest_execution_date": earliest_execution_date,
        "symbol": str(symbol).strip().lower(),
        "setup_id": SETUP_ID,
        "matched_conditions": matched,
        "failed_conditions": failed,
        "reject_reasons": [],
        "support": None,
        "trigger": None,
        "stop": None,
        "target": None,
        "target_type": None,
        "risk": None,
        "rr": None,
        "level_plan": None,
    }
    if base_hi is None:
        base["status"] = NOT_MATCHED
        return base
    base["matched_conditions"].append("SECTOR_EVIDENCE_COMPLETE")
    if close <= 2:
        base.update(status=MATCHED_REJECTED, failed_conditions=["CLOSE_GT_2"], reject_reasons=[REJECTED_CLOSE_TOO_LOW])
        return base
    base["matched_conditions"].append("CLOSE_GT_2")
    if chg10 > 35 and bias20 > 15:
        base.update(status=MATCHED_REJECTED, failed_conditions=["NO_ACCELERATION_OVEREXTENDED"], reject_reasons=[ACCELERATION_OVEREXTENDED])
        return base
    base["matched_conditions"].append("NO_ACCELERATION_OVEREXTENDED")
    if pos250 > 0.9 and chg20 > 40:
        base.update(status=MATCHED_REJECTED, failed_conditions=["NO_GAIN_EXHAUSTED"], reject_reasons=[GAIN_EXHAUSTED])
        return base
    base["matched_conditions"].append("NO_GAIN_EXHAUSTED")
    vol_bar_lo = float(lo[-10:][int(np.argmax(v[-10:]))])
    valid_supports = [value for value in (ma20, base_hi, vol_bar_lo, float(np.min(lo[-20:]))) if value < close]
    if not valid_supports:
        base.update(status=MATCHED_REJECTED, failed_conditions=["VALID_SUPPORT_EXISTS"], reject_reasons=[REJECTED_NO_SUPPORT])
        return base
    base["matched_conditions"].append("VALID_SUPPORT_EXISTS")
    support = float(max(valid_supports))
    stop = round(support * 0.98, 2)
    risk = float((close - stop) / close)
    if risk <= 0 or risk > 0.09:
        base.update(status=MATCHED_REJECTED, failed_conditions=["RISK_IN_0_TO_9_PCT"], reject_reasons=[REJECTED_STOP_DISTANCE])
        return base
    base["matched_conditions"].append("RISK_IN_0_TO_9_PCT")
    target_candidates = []
    if h60 > close * 1.03:
        target_candidates.append(h60)
    above_bins = [index for index in range(20) if bins[index] > close * 1.03]
    if above_bins:
        target_candidates.append(float(bins[max(above_bins, key=lambda index: vol_by_price[index])]))
    if hhv120 > close * 1.03:
        target_candidates.append(hhv120)
    target, target_type = (
        (float(min(target_candidates)), "PRESSURE")
        if target_candidates
        else (float(close * (1 + 2.5 * risk)), "TREND_2_5R")
    )
    rr = float((target - close) / (close - stop))
    level_plan = {
        "support": support,
        "trigger": round(max(base_hi, ma5), 2),
        "stop": stop,
        "target": target,
        "target_type": target_type,
        "risk": risk,
        "rr": rr,
        "overhang": overhang,
    }
    base.update(support=support, trigger=level_plan["trigger"], stop=stop, target=target, target_type=target_type, risk=risk, rr=rr, level_plan=level_plan)
    if rr < 2:
        base.update(status=MATCHED_REJECTED, failed_conditions=["RR_GE_2"], reject_reasons=[REJECTED_RR])
        return base
    base["matched_conditions"].append("RR_GE_2")
    if overhang > 0.5 and rr < 2.5:
        base.update(status=MATCHED_REJECTED, failed_conditions=["OVERHANG_RR_COMBINATION_ACCEPTED"], reject_reasons=[REJECTED_OVERHANG_RR])
        return base
    base["matched_conditions"].append("OVERHANG_RR_COMBINATION_ACCEPTED")
    base["status"] = QUALIFIED_LEGACY_BASELINE
    return base


def evaluate_batch(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    return evaluate_universe(manifest)


__all__ = [
    "B_BREAKOUT_RETEST_LEGACY_V1",
    "LEGACY_SPEC",
    "SETUP_ID",
    "STRATEGY_SPEC_HASH",
    "STRATEGY_SPEC_SHA256",
    "STRATEGY_VERSION",
    "V0_SOURCE_COMMIT",
    "V0_SOURCE_FILE_SHA256",
    "evaluate_batch",
    "evaluate_candidate",
    "evaluate_numeric_projection",
    "evaluate_universe",
    "semantic_spec_sha256",
    "strategy_spec_sha256",
]
